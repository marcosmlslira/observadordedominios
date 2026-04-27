# 009 — Referências

## Arquivos principais
- `frontend/app/admin/ingestion/page.tsx`
- `backend/app/api/v1/routers/ingestion.py`
- `backend/app/repositories/ingestion_run_repository.py`
- `backend/app/repositories/openintel_tld_status_repository.py`
- `ingestion/ingestion/orchestrator/pipeline.py`

## Pontos observados
- `GET /v1/ingestion/tld-status` usa recorte por dia atual para último status.
- `GET /v1/ingestion/openintel/status` usa `openintel_tld_status` para status visual.
- Heatmap consome ambos (`runs`, `tld-status`, `openintel/status`) com refresh de 60s.
- `GET /v1/ingestion/summary` conta `running_now` diretamente de `ingestion_run.status='running'`, sem filtrar stale.
- Caso real em produção (2026-04-26): `openintel/ch` ficou `running` órfão desde 2026-04-25 05:35:43+00 e elevou o card "Executando agora" para 1 com worker ocioso.
- O heatmap histórico usa `/v1/ingestion/runs` por janela (`started_from`/`started_to`) e agrupa por dia local do navegador.
- O status atual por TLD usa `/v1/ingestion/tld-status`, onde `today_run` depende de `started_at::date = today` em UTC.
- Isso permite um caso visualmente contraditório: existir célula preenchida em `23/04` e, ainda assim, o estado principal aparecer como `Sem execução`.
- A visibilidade de artefatos R2 no `/admin/ingestion` hoje e parcial:
  - OpenINTEL possui `last_available_snapshot_date` e `last_ingested_snapshot_date` via `/v1/ingestion/openintel/status`
  - `czds` nao possui equivalente visual de marker
  - `/v1/ingestion/tld-status` nao expõe `marker_present` nem `marker_snapshot_date`
- Como resultado, a pagina nao responde de forma auditavel a pergunta:
  - "para `source + tld + snapshot_date`, existe marker no R2?"
  - "se existe marker, ele ja foi carregado no PostgreSQL ou estamos em `LOAD_ONLY`?"

## Risco principal
- Confundir "não executou hoje" com "TLD não funcional", gerando diagnóstico incorreto.
- Exibir execução ativa falsa por conta de runs órfãos em `running`.
- Confundir "sem execução hoje" com "nunca foi tentado", ocultando tentativas recentes e enfraquecendo a auditoria operacional.
- Nao conseguir distinguir falha de processamento remoto de falha de carga local quando o artefato intermediario ja existe no R2.

## Resultado esperado
- Painel com semântica explícita e fonte de verdade confiável para saúde funcional por TLD.
- Quando houver histórico recente, a UI deve deixar claro se:
  - houve tentativa recente,
  - houve execução no dia selecionado/atual,
  - e qual foi o último resultado conhecido.
- O painel tambem deve deixar claro, para `CZDS` e `OpenINTEL`, se existe marker no R2 para um determinado `source + tld + snapshot_date`, e se esse marker ja foi efetivamente consumido pelo PostgreSQL.

## Incidentes Databricks — 2026-04-26

### 1. OpenINTEL batch grande falhou por memória

- Run Databricks: `167790765356821`
- Nome do run: `ingestion-openintel-batch-302tlds-2026-04-26`
- Link do run: `https://dbc-3ba5a2e9-3491.cloud.databricks.com/?o=1275599411701381#job/33741097426535/run/167790765356821`
- Estado final: `life_cycle_state=INTERNAL_ERROR`, `result_state=FAILED`
- Mensagem exata do Databricks:
  - `Task main failed with message: Execution ran out of memory.`
  - `Please contact Databricks support and provide the trace ID: 1275599411701381/33741097426535/167790765356821/593626927417117.`

Contexto:
- Esse run foi disparado em modo `databricks_only` para um batch com `302` TLDs de OpenINTEL.
- Existe evidência de que batches muito pequenos funcionam no mesmo fluxo:
  - `ingestion-openintel-batch-2tlds-2026-04-26` terminou `SUCCESS`.
- Também houve um run individual OpenINTEL com falha de memória:
  - `492672290441424` (`ingestion-openintel-ch-2026-04-26`)
  - mensagem de estado: `Execution ran out of memory`

Leitura atual do problema:
- O pipeline está concentrando volume demais em um único run do OpenINTEL no Databricks.
- O erro parece ser estrutural de consumo de memória e não de autenticação, rede ou ausência de snapshot.
- Precisamos de ajuda para decidir a estratégia correta de mitigação sem voltar para processamento local.

Tipos de ajuda desejados:
- Recomendar uma política segura de particionamento do batch OpenINTEL:
  - por quantidade fixa de TLDs
  - por estimativa de volume/tamanho
  - por famílias de TLDs grandes vs pequenos
- Avaliar se o notebook atual está materializando dados em memória em excesso e onde quebrar o fluxo.
- Sugerir se devemos:
  - manter `serverless` e só quebrar lotes
  - trocar perfil/compute
  - serializar partes do processamento
- Definir critério objetivo para evitar novo `OOM` antes de subir em produção.

### 2. CZDS batch grande falhou por rate limit/autenticação ICANN

- Run Databricks: `346005775360656`
- Nome do run: `ingestion-czds-batch-1101tlds-2026-04-26`
- Link do run: `https://dbc-3ba5a2e9-3491.cloud.databricks.com/?o=1275599411701381#job/853576786088948/run/346005775360656`
- Estado final: `life_cycle_state=INTERNAL_ERROR`, `result_state=FAILED`
- Mensagem de estado do Databricks:
  - `Task main failed with message: Workload failed, see run output for details.`

Erro identificado no output da task:
- múltiplas ocorrências de:
  - `429 Client Error`
  - URL: `https://account-api.icann.org/api/authenticate`
- O erro se repetiu para muitos TLDs do batch CZDS.

Contexto:
- O `.com` em run separado funcionou no Databricks:
  - run `935176740101302`
  - nome: `ingestion-czds-com-2026-04-26`
  - estado: `TERMINATED/SUCCESS`
- Isso indica que a falha do batch grande de CZDS não foi indisponibilidade total do Databricks.
- A evidência aponta para saturação/limite de autenticação ICANN dentro do próprio notebook ou do cliente usado no batch.

Leitura atual do problema:
- O batch CZDS grande parece disparar autenticações demais, ou em cadência agressiva demais, contra a ICANN.
- O erro dominante não é `pg_load_error`, não é ausência de marker R2 e não é falha de submit no Databricks.
- Precisamos de ajuda para desenhar um padrão robusto de autenticação/retry/backoff para esse fluxo.

Tipos de ajuda desejados:
- Revisar se o client CZDS está autenticando por TLD quando deveria reutilizar sessão/token.
- Sugerir estratégia de backoff para `429`:
  - exponencial com jitter
  - limite de concorrência
  - cooldown entre blocos
- Avaliar se o batch deve ser quebrado também para CZDS, ou se basta corrigir reuso de autenticação.
- Definir como classificar esses casos no pipeline:
  - erro transitório recuperável
  - falha final do batch
  - retry automático parcial

### 3. `.com` do CZDS processou no Databricks, mas falhou depois no load PostgreSQL

- Run Databricks: `935176740101302`
- Nome do run: `ingestion-czds-com-2026-04-26`
- Link do run: `https://dbc-3ba5a2e9-3491.cloud.databricks.com/?o=1275599411701381#job/772609844891660/run/935176740101302`
- Estado do Databricks: `TERMINATED/SUCCESS`

Falha posterior no pipeline:
- etapa: `load_delta` para PostgreSQL
- tabela afetada: `domain_removed_com`
- erro:
  - `null value in column "removed_day" of relation "domain_removed_com" violates not-null constraint`
  - exemplo de linha: `cleanthewrightway.com	com	\N`

Leitura atual do problema:
- O processamento remoto terminou com sucesso e os artefatos foram gravados no R2.
- A falha foi no carregamento do `delta_removed`, não no `delta` de domínios adicionados.
- Esse caso precisa virar recuperação automática sem intervenção manual e sem rerun Databricks.

Tipos de ajuda desejados:
- Propor sanitização segura para `removed_day` nulo no loader.
- Definir um fluxo de retry `removed-only` quando `added` já entrou com sucesso.
- Garantir reason codes e auditoria adequados para esse tipo de recuperação parcial.

### 4. Rerun do mesmo snapshot falha por violação de chave única no loader

- Caso real local: `openintel/at`
- Run de teste: `4bbdaaa9-099e-4f3b-a395-b0549df94b93`
- Estado final: `failed`
- `reason_code`: `unexpected_error`
- Erro exato:
  - `duplicate key value violates unique constraint "domain_at_pkey"`
  - `Key (name, tld)=(0-1.at, at) already exists.`
  - `CONTEXT: COPY domain_at, line 1`

Contexto:
- O TLD `at` ja tinha carga previa bem-sucedida.
- O teste de TLD unico foi disparado para validar se um ciclo isolado apareceria corretamente no `/admin/ingestion`.
- A execucao criou `ingestion_run`, apareceu no painel, mas falhou no momento da carga do `delta_added`.
- Em contraste, `openintel/ae` concluiu com sucesso no mesmo ambiente:
  - run `33fa4fee-86e8-45ab-832a-e13de79f31b4`
  - `status=success`
  - `snapshot_date=2026-04-20`
  - `domains_inserted=140830`

Leitura atual do problema:
- O modelo arquitetural assume semântica append-only e rerun seguro do mesmo snapshot.
- Na pratica, o `load_delta` ainda usa um caminho de `COPY` que nao tolera reaplicacao quando o dado ja existe na particao.
- Isso quebra a promessa de idempotencia de `LOAD_ONLY` e tambem dificulta recuperacoes apos falha parcial.

Tipos de ajuda desejados:
- Definir a estrategia correta para tornar o loader idempotente sem perder performance:
  - `COPY` para staging + `INSERT ... ON CONFLICT DO NOTHING`
  - deduplicacao previa por shard
  - deduplicacao via tabela temporaria por execucao
- Garantir que o rerun do mesmo `source + tld + snapshot_date` nunca falhe por PK duplicada.
- Preservar throughput alto para TLDs grandes, sem regredir o ganho do modelo por particao.

### 5. Sucesso real de ingestao nao reconcilia `openintel_tld_status`

- Caso real local: `openintel/ae`
- Run bem-sucedido: `33fa4fee-86e8-45ab-832a-e13de79f31b4`
- Estado do run:
  - `status=success`
  - `reason_code=success`
  - `snapshot_date=2026-04-20`
  - `domains_inserted=140830`

Estado observado apos o sucesso:
- `domain_ae` populado com `140830` rows
- `max(added_day)=20260420`
- porem `openintel_tld_status` permaneceu com:
  - `last_available_snapshot_date=2026-04-20`
  - `last_ingested_snapshot_date=NULL`
  - `last_probe_outcome=new_snapshot_pending_or_failed`
  - `last_error_message='DomainRepository' object has no attribute 'bulk_upsert'`

Leitura atual do problema:
- O pipeline canonico de ingestao conseguiu concluir com sucesso.
- A camada derivada usada pela UI para OpenINTEL nao foi reconciliada com esse sucesso.
- Como o `/admin/ingestion` mistura `ingestion_run` com `openintel_tld_status`, o TLD pode continuar visualmente incorreto mesmo depois de carregar no banco.

Tipos de ajuda desejados:
- Definir o ponto correto do pipeline para atualizar `openintel_tld_status` apos `success`.
- Decidir se `openintel_tld_status` deve ser:
  - atualizado inline no fluxo canonico
  - ou recalculado a partir de `ingestion_run` + disponibilidade de snapshot
- Garantir que a UI nunca mostre `new_snapshot_pending_or_failed` quando ja existe `ingestion_run success` para o mesmo snapshot.

### 6. Databricks `SUCCESS` no OpenINTEL sem marker R2 consumivel

- Caso real local: `openintel/ag`
- Databricks run: `217457305683193`
- Run local de auditoria: `568396cf-f88e-4151-bd40-fa8e8db61e8c`
- Estado final do pipeline: `failed`
- `reason_code`: `r2_marker_missing`
- Erro:
  - `R2 marker missing after Databricks run — TLD likely failed in notebook`

Contexto:
- O teste foi feito pelo caminho do Databricks, usando o mesmo helper do orquestrador que:
  - cria `ingestion_run`
  - espera o job remoto
  - valida marker no R2
  - executa o load no PostgreSQL
- O Databricks terminou com `TERMINATED/SUCCESS`, mas o marker esperado nao foi encontrado na etapa seguinte.
- Como resultado, `domain_ag` permaneceu vazio.

Leitura atual do problema:
- O estado `SUCCESS` do Databricks nao esta garantindo o contrato minimo esperado pelo loader.
- Pode haver falha de notebook ao gravar marker, diferenca de `snapshot_date`, ou falso positivo no criterio de sucesso remoto.

Tipos de ajuda desejados:
- Verificar no notebook/submitter qual arquivo/marker precisa ser persistido para OpenINTEL.
- Validar se o run remoto escreveu parquet sem escrever marker, ou se nao escreveu nenhum artefato.
- Confirmar se a validacao local de marker esta procurando no prefixo e `snapshot_date` corretos.

### 7. Databricks `SUCCESS` no CZDS com carga parcial e falha em `domain_removed`

- Caso real local: `czds/blog`
- Databricks run: `763318525078691`
- Run local de auditoria: `91ceff47-b990-4ffa-ba64-d5a9af39d1bd`
- Estado final do pipeline: `failed`
- `reason_code`: `pg_load_error`
- Erro:
  - `null value in column "removed_day" of relation "domain_removed_blog" violates not-null constraint`
  - exemplo: `00142.blog	blog	\N`

Contexto:
- O run remoto terminou `SUCCESS`.
- A carga do `delta_added` aconteceu parcialmente com sucesso:
  - `domain_blog` ficou com `490` rows
  - `max(added_day)=20260427`
- A falha ocorreu na etapa `delta_removed`, exatamente como no caso anterior de `.com`.

Leitura atual do problema:
- O problema de `removed_day` nulo nao esta restrito a TLDs gigantes.
- O fluxo atual consegue deixar o banco em estado parcialmente aplicado:
  - `domain_<tld>` carregado
  - `domain_removed_<tld>` falhou
  - `ingestion_run` termina `failed`

Tipos de ajuda desejados:
- Generalizar a correcao de `removed_day` nulo para qualquer TLD/fonte.
- Implementar recuperacao automatica de carga parcial sem rerun Databricks.
- Definir como a UI deve exibir explicitamente esse estado de "carga parcial aplicada".
