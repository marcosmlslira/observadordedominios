# Runbook de Validação — TODO 011

> Checklist sequencial para validar que os ajustes do TODO 011 (resiliência da ingestão, stack isolado, cycle tracking, watchdog, métricas) estão funcionando corretamente em produção.
>
> **Modo de uso:** todo o checklist parte do pressuposto de que o operador está com um terminal local apontando para a máquina de produção via SSH (`ssh ubuntu@158.69.211.109`) e dispara a validação em sequência. Cada item tem três blocos: o que **deve acontecer**, **ponto crítico**, e **referência de validação** (comando terminal).
>
> **Convenções de variáveis usadas abaixo:**
> ```bash
> SSH_HOST="ubuntu@158.69.211.109"
> API_BASE="https://api.observadordedominios.com.br"
> TRIGGER_TOKEN="<valor de OBSERVADOR_INGESTION_TRIGGER_TOKEN>"
> ADMIN_JWT="<JWT obtido via /v1/auth/login>"
> ```

---

## Fase 0 — Sanidade pré-trigger (linha de base)

Antes de disparar qualquer trigger, confirme que o estado base está íntegro. Se algum item desta fase falhar, **não** prossiga.

### 0.1 Os dois stacks estão deployados e separados

**Deve acontecer:** `docker stack ls` lista exatamente dois stacks com prefixo `observador*`: `observador` (sem ingestion_worker) e `observador-ingestion` (apenas ingestion_worker).

**Ponto crítico:** Se aparecer `ingestion_worker` dentro do stack `observador`, o deploy ficou inconsistente — a remoção de `observador.yml` não foi aplicada. Reverter e investigar.

```bash
ssh $SSH_HOST 'docker stack ls | grep observador'
# Esperado:
#   observador             8        Swarm
#   observador-ingestion   1        Swarm

ssh $SSH_HOST 'docker stack services observador | grep -i ingestion'
# Esperado: vazio (sem saída)

ssh $SSH_HOST 'docker stack services observador-ingestion'
# Esperado: 1/1 ingestion_worker
```

### 0.2 Network alias `ingestion_worker` existe na rede compartilhada

**Deve acontecer:** O serviço do stack isolado tem alias `ingestion_worker` na rede `observador_internal`, garantindo que `INGESTION_TRIGGER_URLS=http://ingestion_worker:8080` ainda resolva mesmo com o worker em outro stack.

**Ponto crítico:** Sem o alias, o backend recebe `Name or service not known` e o trigger via API falha silenciosamente.

```bash
ssh $SSH_HOST 'docker service inspect observador-ingestion_ingestion_worker \
  --format "{{json .Spec.TaskTemplate.Networks}}" | jq'
# Esperado: array com Aliases contendo "ingestion_worker"

# Validar resolução DNS de dentro do backend:
BACKEND_ID=$(ssh $SSH_HOST "docker ps -qf name=observador_backend" | head -1)
ssh $SSH_HOST "docker exec $BACKEND_ID getent hosts ingestion_worker"
# Esperado: linha com IP 10.0.x.x  ingestion_worker
```

### 0.3 Secret do trigger registrado e propagado

**Deve acontecer:** Secret `OBSERVADOR_INGESTION_TRIGGER_TOKEN` está no GitHub e foi propagado para os env vars de backend (variável `INGESTION_TRIGGER_TOKEN`) e ingestion_worker.

**Ponto crítico:** Se backend e worker tiverem tokens diferentes (ou um deles vazio), todo trigger via API retorna 401 do worker.

```bash
gh secret list --repo marcosmlslira/docker-stack-infra | grep OBSERVADOR_INGESTION_TRIGGER_TOKEN

# Confirmar que o env var chegou nos containers (sem expor o valor):
ssh $SSH_HOST 'docker exec $(docker ps -qf name=observador_backend | head -1) \
  printenv INGESTION_TRIGGER_TOKEN | wc -c'
ssh $SSH_HOST 'docker exec $(docker ps -qf name=observador-ingestion_ingestion_worker | head -1) \
  printenv INGESTION_TRIGGER_TOKEN | wc -c'
# Esperado: mesmo número de caracteres (>1) nos dois lados
```

### 0.4 Migrations 036 e 037 aplicadas

**Deve acontecer:** A versão do Alembic em produção é `037_tld_health_view` (head). Tabela `ingestion_cycle` e view `tld_health_v` existem.

**Ponto crítico:** O cycle tracking depende destas migrations. Se faltarem, o scheduler vai logar erro ao tentar chamar `open_cycle()`.

```bash
ssh $SSH_HOST 'docker exec $(docker ps -qf name=observador_backend | head -1) \
  alembic current'
# Esperado: 037_tld_health_view (head)

ssh $SSH_HOST 'docker exec $(docker ps -qf name=observador_postgres | head -1) \
  psql -U obs -d obs -c "\d ingestion_cycle" | head -5'
ssh $SSH_HOST 'docker exec $(docker ps -qf name=observador_postgres | head -1) \
  psql -U obs -d obs -c "\dv tld_health_v"'
```

### 0.5 Health endpoint do backend lê do banco

**Deve acontecer:** `GET /health` retorna 200 e o payload inclui `last_cycle` (mesmo que `null` se nunca houve ciclo).

**Ponto crítico:** Se o campo não existir na resposta, o backend está rodando código antigo — verificar se a imagem foi atualizada.

```bash
curl -s "$API_BASE/health" | jq '.last_cycle'
# Esperado: objeto {cycle_id, status, ...} OU null
```

### 0.6 Health endpoint do worker responde (porta 8080 só na rede interna)

**Deve acontecer:** Endpoint `/health` do worker responde 200 quando consultado de dentro da rede `observador_internal`.

**Ponto crítico:** O worker NÃO deve estar exposto via Traefik. Se `curl https://api...:8080` funciona externamente, há vazamento.

```bash
# De dentro do backend (rede interna):
ssh $SSH_HOST 'docker exec $(docker ps -qf name=observador_backend | head -1) \
  curl -s -o /dev/null -w "%{http_code}\n" http://ingestion_worker:8080/health'
# Esperado: 200

# Externamente (deve falhar):
curl -s -o /dev/null -w "%{http_code}\n" https://api.observadordedominios.com.br:8080/health
# Esperado: timeout ou erro de conexão (NÃO 200)
```

---

## Fase 1 — Disparar o trigger (T0)

A partir daqui o tempo é o que importa. Marque T0 como o instante do trigger.

### 1.1 Disparo do trigger via API pública (autenticado como admin)

**Deve acontecer:** `POST /v1/ingestion/run-now` retorna 202 Accepted com `cycle_id` e `started_at`.

**Ponto crítico:** Códigos diferentes mapeiam problemas distintos:
- `401`: JWT do admin inválido/expirado
- `409`: já existe ciclo `running` no banco — backend recusa segundo trigger paralelo
- `502/503`: backend não conseguiu falar com o worker (DNS, alias quebrado, worker fora do ar)
- `504`: worker recebeu mas não respondeu em tempo

```bash
T0=$(date -u +%FT%TZ)
echo "T0=$T0"

curl -i -X POST "$API_BASE/v1/ingestion/run-now" \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{"trigger":"manual_validation"}'
# Esperado: HTTP/2 202 + body com cycle_id
```

### 1.2 Backend chamou o worker com o token correto

**Deve acontecer:** Logs do backend mostram `POST http://ingestion_worker:8080/run-now` com header `X-Ingestion-Token: <token>` e resposta 202.

**Ponto crítico:** Se aparecer `401 Unauthorized` na resposta do worker, o token do worker e do backend divergiram. Isto **só** acontece se um dos dois containers foi reiniciado com env var antigo.

```bash
ssh $SSH_HOST 'docker service logs observador_backend --since 2m 2>&1 \
  | grep -i "ingestion_worker\|run-now" | tail -10'
# Esperado: linha "calling worker run-now ... status=202"
```

### 1.3 Worker abriu o ciclo no banco

**Deve acontecer:** Em <5s após o trigger, `ingestion_cycle` tem nova linha com `status='running'`, `triggered_by='manual_validation'`, `started_at >= T0`.

**Ponto crítico:** Sem essa linha, o cycle tracking quebrou (provavelmente exception silenciada no `open_cycle()`). O resto do checklist depende desta linha existir.

```bash
ssh $SSH_HOST "docker exec \$(docker ps -qf name=observador_postgres | head -1) \
  psql -U obs -d obs -c \"SELECT cycle_id, status, triggered_by, started_at, last_heartbeat_at \
                          FROM ingestion_cycle ORDER BY started_at DESC LIMIT 1;\""
# Esperado: 1 linha com status=running e triggered_by=manual_validation
```

### 1.4 Heartbeat avança a cada N segundos

**Deve acontecer:** O campo `last_heartbeat_at` se atualiza periodicamente (intervalo definido no scheduler, normalmente 30–60s).

**Ponto crítico:** Heartbeat parado por >5min com `status=running` é o sinal de "ciclo travado". O watchdog deve recuperar isso na Fase 4. Por enquanto, só observar.

```bash
# Rodar duas vezes com 60s de espaço e comparar:
for i in 1 2; do
  ssh $SSH_HOST "docker exec \$(docker ps -qf name=observador_postgres | head -1) \
    psql -U obs -d obs -At -c \"SELECT last_heartbeat_at FROM ingestion_cycle \
                                ORDER BY started_at DESC LIMIT 1;\""
  [ $i -eq 1 ] && sleep 60
done
# Esperado: timestamp da 2ª chamada > 1ª
```

---

## Fase 2 — Execução por TLD (T0+0s … T0+Nmin)

### 2.1 Worker começa a iterar TLDs e cria `ingestion_run` por TLD/fase

**Deve acontecer:** Para cada TLD ativado em `OPENINTEL_ENABLED_TLDS` ou `CZDS_ENABLED_TLDS`, surge linha em `ingestion_run` com `status='running'`.

**Ponto crítico:** Se nenhum run aparecer dentro de 30s, o worker recebeu o trigger mas não conseguiu iniciar (tipicamente porque o `provision_tld.py` está travado em advisory lock).

```bash
ssh $SSH_HOST "docker exec \$(docker ps -qf name=observador_postgres | head -1) \
  psql -U obs -d obs -c \"SELECT source, tld, phase, status, started_at \
                          FROM ingestion_run \
                          WHERE started_at >= NOW() - INTERVAL '5 minutes' \
                          ORDER BY started_at DESC;\""
```

### 2.2 Provisioning idempotente (tabelas staging existem antes do load)

**Deve acontecer:** Para cada TLD novo, `staging_<tld>` e partição `domain_<tld>` existem antes da fase de load. Para TLDs já provisionados, **nenhum DDL é executado**.

**Ponto crítico:** Se logs mostrarem `CREATE TABLE staging_*` ou `ATTACH PARTITION` durante o ciclo, é regressão da Sprint 2 — o DDL voltou ao hot path.

```bash
ssh $SSH_HOST 'docker service logs observador-ingestion_ingestion_worker --since 5m 2>&1 \
  | grep -iE "CREATE TABLE|ATTACH PARTITION|DETACH PARTITION|REINDEX" | head -20'
# Esperado: vazio durante o ciclo (ou só linhas do _boot_ do scheduler)
```

### 2.3 Logs de memória por TLD (Sprint 5.1)

**Deve acontecer:** Para cada TLD processado, dois logs em DEBUG: `mem[start] tld=... rss_kb=...` e `mem[end] tld=... rss_kb=... delta_kb=±...`.

**Ponto crítico:** Se `delta_kb` ficar consistentemente acima de 500MB para um único TLD, é candidato a OOM em corrida futura → considerar streaming chunks (Sprint 2.7, postergada).

```bash
ssh $SSH_HOST 'docker service logs observador-ingestion_ingestion_worker --since 10m 2>&1 \
  | grep "^.*mem\[" | tail -40'
# Inspecionar manualmente os deltas
```

### 2.4 Estatísticas agregadas no ciclo evoluem

**Deve acontecer:** À medida que TLDs concluem, `ingestion_cycle.tld_success` e/ou `tld_failed`/`tld_skipped`/`tld_load_only` incrementam.

**Ponto crítico:** Se a soma `tld_success + tld_failed + tld_skipped + tld_load_only > tld_total`, há double-count no `close_cycle()` — bug.

```bash
ssh $SSH_HOST "docker exec \$(docker ps -qf name=observador_postgres | head -1) \
  psql -U obs -d obs -c \"SELECT tld_total, tld_success, tld_failed, tld_skipped, tld_load_only \
                          FROM ingestion_cycle ORDER BY started_at DESC LIMIT 1;\""
```

### 2.5 Endpoint `/v1/ingestion/cycles` reflete em tempo real

**Deve acontecer:** Em <2s, a UI ou um curl direto ao endpoint mostra o ciclo atual com contadores atualizados.

**Ponto crítico:** Se `/cycles` retorna lista vazia ou ciclo antigo, a query do repository não está pegando rows novos (cache de conexão? transação fora do snapshot?).

```bash
curl -s "$API_BASE/v1/ingestion/cycles?limit=3" \
  -H "Authorization: Bearer $ADMIN_JWT" | jq '.items[0]'
# Esperado: status=running e cycle_id batendo com o do banco
```

### 2.6 View `tld_health_v` reflete último status por TLD

**Deve acontecer:** Conforme TLDs concluem, `last_status` na view passa de `running` para `succeeded`/`failed`.

```bash
curl -s "$API_BASE/v1/ingestion/tlds/health?limit=20" \
  -H "Authorization: Bearer $ADMIN_JWT" | jq '.items[] | {tld, last_status, last_reason_code}'
```

---

## Fase 3 — Encerramento normal

### 3.1 Ciclo fecha com `status=succeeded` e métrica é emitida

**Deve acontecer:** Quando o último TLD termina:
1. `ingestion_cycle.status='succeeded'` (ou `'failed'` se houver falha crítica)
2. `finished_at` preenchido
3. Log estruturado: `metric ingestion_cycle_duration_seconds=<n.n> status=succeeded trigger=manual_validation tld_success=N tld_failed=N ...`

**Ponto crítico:** Sem o log da métrica, dashboards externos (se houver) não recebem o sinal de fim. A regex de monitoramento espera exatamente esse prefixo `metric ingestion_cycle_duration_seconds=`.

```bash
ssh $SSH_HOST 'docker service logs observador-ingestion_ingestion_worker --since 30m 2>&1 \
  | grep "metric ingestion_cycle_duration_seconds" | tail -3'
# Esperado: linha com a métrica e os contadores
```

### 3.2 Health do backend agora retorna `last_cycle` populado

**Deve acontecer:** `GET /health` mostra `last_cycle.status='succeeded'` e `last_cycle.finished_at` recente.

```bash
curl -s "$API_BASE/health" | jq '.last_cycle'
```

### 3.3 UI `/admin/ingestion` mostra o ciclo na seção "Ciclos recentes"

**Deve acontecer:** Card aparece no topo da lista com badge "Sucesso" (verde), `tld_success`/`tld_failed` corretos, e duração.

**Ponto crítico:** Se a UI continuar mostrando ciclo antigo, é cache do React Query — recarregar página força refetch.

```bash
# Verificação manual: abrir https://observadordedominios.com.br/admin/ingestion
# (logado como admin) e conferir o card "Ciclos recentes"
```

---

## Fase 4 — Validação dos cenários de resiliência

Estes testes **não rodam todos no mesmo ciclo** — são experimentos isolados, executados em ciclos dedicados de validação. Faça um por vez, registre o resultado, depois execute o próximo.

### 4.1 Graceful shutdown durante ingestão (SIGTERM)

**Deve acontecer:** Disparar trigger; durante a execução, fazer `docker service update --force` no worker. O scheduler captura SIGTERM, marca `status='interrupted'` no ciclo, fecha runs em andamento como `interrupted`, e o container sai dentro do `stop_grace_period` (6h, mas na prática <30s para um shutdown limpo). Após restart, novo container assume; ciclo antigo permanece como `interrupted` no histórico.

**Ponto crítico:** Se o container demorar 6h para parar, o handler de SIGTERM travou em alguma operação síncrona. Investigar com `py-spy dump` no PID antes de matar via SIGKILL.

```bash
# Em uma janela: dispara trigger
curl -X POST "$API_BASE/v1/ingestion/run-now" \
  -H "Authorization: Bearer $ADMIN_JWT" -d '{"trigger":"validation_sigterm"}'

# Em outra janela: aguarda 30s e força redeploy
sleep 30
ssh $SSH_HOST 'docker service update --force observador-ingestion_ingestion_worker'

# Validar: ciclo ficou interrupted
ssh $SSH_HOST "docker exec \$(docker ps -qf name=observador_postgres | head -1) \
  psql -U obs -d obs -c \"SELECT cycle_id, status, finished_at \
                          FROM ingestion_cycle WHERE triggered_by='validation_sigterm';\""
# Esperado: status=interrupted
```

### 4.2 Stale watchdog recupera ciclo com heartbeat parado

**Deve acontecer:** Simular travamento (matar container com SIGKILL para impedir SIGTERM cleanup). O watchdog (`_start_stale_watchdog`, intervalo 600s, threshold 60min) eventualmente vê `last_heartbeat_at < NOW() - 60min` e marca o ciclo como `interrupted` com `reason_code='stale_heartbeat'`.

**Ponto crítico:** O threshold é 60 minutos por design (evita falso-positivo em TLDs grandes). Para validar manualmente em tempo razoável, **temporariamente** reduzir `stale_minutes=2` no chamador de `_start_stale_watchdog` em ambiente de teste — **nunca em produção**.

```bash
# Forçar SIGKILL no worker para deixar ciclo running sem cleanup:
WID=$(ssh $SSH_HOST 'docker ps -qf name=observador-ingestion_ingestion_worker | head -1')
ssh $SSH_HOST "docker kill --signal=KILL $WID"

# Aguardar restart + 1 ciclo do watchdog (em produção: até 70min)
# Em ambiente de teste com threshold reduzido, ~3-5min

ssh $SSH_HOST "docker exec \$(docker ps -qf name=observador_postgres | head -1) \
  psql -U obs -d obs -c \"SELECT cycle_id, status, last_heartbeat_at \
                          FROM ingestion_cycle WHERE status IN ('running','interrupted') \
                          ORDER BY started_at DESC LIMIT 5;\""
# Esperado eventualmente: ciclo travado vira 'interrupted'

ssh $SSH_HOST 'docker service logs observador-ingestion_ingestion_worker --since 70m 2>&1 \
  | grep "stale watchdog: recovered"'
```

### 4.3 Deploy do backend NÃO interrompe a ingestão

**Deve acontecer:** Disparar ciclo de ingestão; durante a execução, push em `observadordedominios:main` (ou trigger manual de `Deploy Swarm`). O backend é redeployado, mas o stack `observador-ingestion` é ignorado pelo workflow (skip explícito em `deploy.yml`). O ingestion_worker continua rodando sem reiniciar; o ciclo conclui normalmente.

**Ponto crítico:** Esta é **a** validação central da Sprint 1.7/1.8. Se o ingestion_worker reiniciar, o desacoplamento falhou.

```bash
# Em uma janela: dispara ingestão
curl -X POST "$API_BASE/v1/ingestion/run-now" \
  -H "Authorization: Bearer $ADMIN_JWT" -d '{"trigger":"validation_deploy_isolation"}'

# Em outra: força redeploy do stack principal
gh workflow run deploy.yml --repo marcosmlslira/docker-stack-infra
gh run watch --repo marcosmlslira/docker-stack-infra --exit-status

# Logs do workflow devem conter:
#   "Skipping stack observador-ingestion (managed by deploy-ingestion.yml)"

# Validar: uptime do worker NÃO foi resetado
ssh $SSH_HOST 'docker ps --filter name=observador-ingestion_ingestion_worker \
  --format "{{.Status}}"'
# Esperado: "Up X minutes" — onde X >= tempo desde o trigger inicial

# Validar: ciclo concluiu sem ser interrompido
ssh $SSH_HOST "docker exec \$(docker ps -qf name=observador_postgres | head -1) \
  psql -U obs -d obs -c \"SELECT status FROM ingestion_cycle \
                          WHERE triggered_by='validation_deploy_isolation';\""
# Esperado: succeeded (NUNCA interrupted)
```

### 4.4 Deploy manual do stack de ingestão respeita ciclo em curso

**Deve acontecer:** Com ciclo em `running`, executar `gh workflow run deploy-ingestion.yml -f force=false`. O workflow detecta o ciclo ativo via SQL, aborta o deploy com mensagem clara, e o ciclo continua intacto.

**Ponto crítico:** Se `force=false` deployar mesmo assim, a guarda do workflow está quebrada — investigar a step de pré-check.

```bash
# Disparar ingestão e, sem esperar, tentar deploy
curl -X POST "$API_BASE/v1/ingestion/run-now" \
  -H "Authorization: Bearer $ADMIN_JWT" -d '{"trigger":"validation_deploy_guard"}'

gh workflow run deploy-ingestion.yml --repo marcosmlslira/docker-stack-infra -f force=false
RUN_ID=$(gh run list --repo marcosmlslira/docker-stack-infra --workflow=deploy-ingestion.yml \
  --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch $RUN_ID --repo marcosmlslira/docker-stack-infra --exit-status
# Esperado: workflow termina com FALHA controlada e mensagem
#           "Ingestion cycle is running — aborting. Use force=true to override."
```

### 4.5 Override `force=true` deploya mesmo com ciclo em curso

**Deve acontecer:** `gh workflow run deploy-ingestion.yml -f force=true` ignora a guarda, faz `stop-first` no worker, ciclo em curso vira `interrupted`, novo container sobe.

**Ponto crítico:** Use **só** quando intencional (rollback de bug crítico). Documentar no canal de operações antes.

```bash
gh workflow run deploy-ingestion.yml --repo marcosmlslira/docker-stack-infra -f force=true
# Validar que o ciclo em curso virou interrupted após o deploy
```

### 4.6 Triggers concorrentes são rejeitados

**Deve acontecer:** Dois `POST /run-now` simultâneos: o primeiro retorna 202; o segundo retorna 409 com mensagem `cycle_already_running`.

**Ponto crítico:** Se ambos retornarem 202, o lock no `open_cycle()` falhou — risco de double-execution e corrupção de dados.

```bash
# Disparar dois em paralelo:
( curl -s -o /tmp/r1.json -w "%{http_code}\n" -X POST "$API_BASE/v1/ingestion/run-now" \
    -H "Authorization: Bearer $ADMIN_JWT" -d '{"trigger":"concurrent_a"}' &
  curl -s -o /tmp/r2.json -w "%{http_code}\n" -X POST "$API_BASE/v1/ingestion/run-now" \
    -H "Authorization: Bearer $ADMIN_JWT" -d '{"trigger":"concurrent_b"}' &
  wait )
# Esperado: um 202 e um 409
```

### 4.7 Token inválido é recusado pelo worker

**Deve acontecer:** Chamada direta ao worker com token errado retorna 401.

**Ponto crítico:** Esta validação prova que o endpoint `/run-now` do worker NÃO é acessível a qualquer container da rede interna sem autenticação.

```bash
ssh $SSH_HOST 'docker exec $(docker ps -qf name=observador_backend | head -1) \
  curl -s -o /dev/null -w "%{http_code}\n" \
       -X POST http://ingestion_worker:8080/run-now \
       -H "X-Ingestion-Token: TOKEN_ERRADO" \
       -H "Content-Type: application/json" -d "{}"'
# Esperado: 401
```

### 4.8 Postgres OOM-resistente (memory limit aplicado)

**Deve acontecer:** Container do postgres tem limite de 8G e reservation de 4G (Sprint 1.4). Se um TLD enorme estourar, o postgres é morto pelo Docker em vez de causar WAL LSN corruption.

**Ponto crítico:** Não tente reproduzir OOM intencionalmente em produção. Apenas confirme que o limite **está aplicado**.

```bash
ssh $SSH_HOST 'docker service inspect observador_postgres \
  --format "{{json .Spec.TaskTemplate.Resources}}" | jq'
# Esperado: Limits.MemoryBytes=8589934592 ; Reservations.MemoryBytes=4294967296
```

---

## Fase 5 — Smoke tests de regressão

Após cada deploy, rodar essa lista curta como sanity check rápido (~5min total).

| # | O que testar | Comando | Esperado |
|---|---|---|---|
| 5.1 | API pública responde | `curl -s -o /dev/null -w "%{http_code}\n" $API_BASE/health` | 200 |
| 5.2 | Front responde | `curl -s -o /dev/null -w "%{http_code}\n" https://observadordedominios.com.br` | 200 |
| 5.3 | Worker responde internamente | `ssh $SSH_HOST 'docker exec $(docker ps -qf name=observador_backend\|head -1) curl -s -o /dev/null -w "%{http_code}" http://ingestion_worker:8080/health'` | 200 |
| 5.4 | DB reachable | `ssh $SSH_HOST 'docker exec $(docker ps -qf name=observador_postgres\|head -1) pg_isready -U obs'` | accepting connections |
| 5.5 | Cycles endpoint | `curl -s "$API_BASE/v1/ingestion/cycles?limit=1" -H "Authorization: Bearer $ADMIN_JWT" \| jq '.items \| length'` | ≥1 |
| 5.6 | Sem runs travados | Query abaixo | 0 linhas |

```sql
-- Smoke 5.6: nenhum run > 6h em status=running
SELECT source, tld, phase, started_at
FROM ingestion_run
WHERE status = 'running'
  AND started_at < NOW() - INTERVAL '6 hours';
```

---

## Critérios de aceite final

O TODO 011 só é considerado **integralmente validado em produção** quando todos abaixo forem checados em sequência, no mesmo dia, sem rollback intermediário:

- [ ] Fase 0: todos os 6 itens passam
- [ ] Fase 1: trigger 1.1 retorna 202 e ciclo aparece no banco em <5s (1.3)
- [ ] Fase 2: pelo menos um TLD conclui com `mem[end]` logado e `tld_success` incrementa (2.3, 2.4)
- [ ] Fase 3: ciclo fecha com `status=succeeded`, métrica emitida no log, UI mostra card (3.1, 3.3)
- [ ] Fase 4: cenários 4.3 (deploy isolation) e 4.6 (concorrência) passam — críticos
- [ ] Fase 4: cenários 4.1, 4.2, 4.4, 4.5, 4.7, 4.8 passam — desejáveis
- [ ] Fase 5: smoke tests todos passam após cada deploy subsequente

Cenários **opcionais** (validar caso o tempo permita): 4.2 (stale watchdog em produção real, requer 70min), 4.5 (force=true, requer ciclo de validação).

---

## Anexo — Como obter credenciais

> **Os valores em claro NÃO ficam neste arquivo.** Este runbook é versionado em git e qualquer secret aqui seria considerado vazado no instante do commit.
>
> Os valores reais (e instruções de onde achar cada um) ficam em **`docs/runbooks/todo-011-validation.credentials.local.md`**, que é ignorado pelo git via regra `*.credentials.local.md` no `.gitignore`. Esse arquivo deve ser distribuído entre operadores por canal cifrado (1Password shared vault, Bitwarden Send, Signal) — nunca por e-mail ou chat sem cifragem.

### Setup mínimo na máquina do operador

1. **Solicite o arquivo local de credenciais** ao owner do projeto (marcosmlslira@gmail.com) via canal cifrado. Salve como:
   ```
   <repo>/docs/runbooks/todo-011-validation.credentials.local.md
   ```
   Confirme com `git status` que o arquivo aparece como **untracked e ignorado** (`git check-ignore -v <path>` deve responder com a regra de match).

2. **Cole o bloco de exports** do arquivo local no shell antes de executar a Fase 0 do checklist. O bloco define `SSH_HOST`, `API_BASE`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `TRIGGER_TOKEN` e gera `ADMIN_JWT` via `/v1/auth/login`.

3. **Valide** rodando os três checks de sanidade da seção "Sanidade após colar" do arquivo local (status 200 no endpoint, SSH respondendo, hash do `TRIGGER_TOKEN` igual nos dois containers).

### Onde mora o valor real (resumo — detalhe completo no arquivo local)

| Variável         | Onde está o valor em claro                          | GitHub Secret correspondente               |
|------------------|------------------------------------------------------|---------------------------------------------|
| `ADMIN_EMAIL`    | 1Password "Observador — Produção" → "admin login"    | `OBSERVADOR_ADMIN_EMAIL`                    |
| `ADMIN_PASSWORD` | 1Password "Observador — Produção" → "admin login"    | `OBSERVADOR_ADMIN_PASSWORD_HASH` (hash apenas) |
| `TRIGGER_TOKEN`  | 1Password "Observador — Produção" → "ingestion-trigger-token" | `OBSERVADOR_INGESTION_TRIGGER_TOKEN` (em `marcosmlslira/docker-stack-infra`) |
| `ADMIN_JWT`      | gerado em runtime via `POST /v1/auth/login`          | n/a (efêmero, ~60min)                       |

**Importante sobre `gh secret`:** o GitHub não devolve o valor de um secret após criação — `gh secret list` retorna só nome e data de atualização. Sempre que o operador precisar do valor real, a fonte da verdade é o 1Password; se lá tiver desincronizado, gerar novo valor via `openssl rand -hex 32` e propagar (procedimento completo no arquivo local).

### Em caso de vazamento

Veja a seção "Em caso de vazamento" no arquivo local. Premissa: **secret commitado em git é secret comprometido** — não tente apagar do histórico, rotacione.
