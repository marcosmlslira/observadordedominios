# 014 — Incidente 01/05: Falha total de ingestão + Corrupção pg_catalog.pg_class

## Resumo do Incidente

Em 01/05/2026 (UTC), **4 de 5 runs de ingestão falharam**. A única run bem-sucedida (`.net`, 406k domínios inseridos em ~16 min) completou antes que a instabilidade acumulada causasse a queda de conexões de longa duração.

A causa-raiz é a **corrupção contínua de `pg_catalog.pg_class`**, ativa desde pelo menos 27/04/2026 e ainda presente em 02/05/2026. O autovacuum falha com o mesmo erro a cada ~60 segundos ininterruptamente há 5+ dias.

---

## Causa-Raiz: Corrupção de pg_catalog.pg_class

### Evidência

```
ERROR:  found xmin 690691 from before relfrozenxid 762739
CONTEXT:  while scanning block 163 offset 13 of relation "pg_catalog.pg_class"
automatic vacuum of table "obs.pg_catalog.pg_class"
```

Primeira ocorrência confirmada: `2026-04-27 19:52:15 UTC`  
Última ocorrência confirmada: `2026-05-02 01:07:18 UTC` (ainda ativa)

### Explicação Técnica

A tabela `pg_catalog.pg_class` registra `relfrozenxid = 762739`, indicando que todos os tuples até o XID 762739 foram congelados. Porém, o tuple no bloco 163, offset 13 ainda tem `xmin = 690691` (um XID menor, portanto mais antigo), sem o bit de congelamento marcado.

O PostgreSQL considera isso uma violação de integridade de dados: o VACUUM declarou ter congelado além de 690691, mas o tuple permanece "vivo" e não congelado. Todo worker de autovacuum que tenta processar `pg_class` falha imediatamente e é eliminado.

### Cadeia de Impacto

```
pg_class corrompe
    → autovacuum falha a cada 60s (loop infinito desde 27/04)
    → instabilidade no cache de catálogo compartilhado
    → PostgreSQL derruba conexões longas ativas
    → psycopg2.OperationalError: "server closed the connection unexpectedly"
    → run de ingestão falha após horas de operação
```

### Por que .net completou mas xyz/info/org/ch falharam

`.net` processou 128 shards em ~16 minutos via delta_loader. Operações curtas completam antes que a instabilidade accumule. As runs `xyz` (367 min), `info` (366 min) e `org`/`ch` (60–68 min pelo watchdog) são suficientemente longas para serem interceptadas pela queda de conexão.

---

## Mapa de Falhas de 01/05/2026

| TLD | Source | Duração | Status | Reason Code | Causa Imediata |
|-----|--------|---------|--------|-------------|----------------|
| xyz | czds | 367 min | failed | unexpected_error | psycopg2.OperationalError: server closed the connection |
| info | czds | 366 min | failed | unexpected_error | psycopg2.OperationalError: server closed the connection |
| org | czds | 68 min | failed | stale_recovered | Stale watchdog terminou a run após 60 min sem heartbeat |
| ch | openintel | 61 min | failed | stale_recovered | Stale watchdog terminou a run após 60 min sem heartbeat |
| **net** | czds | ~16 min | **success** | success | 406k domínios inseridos antes da queda |

---

## Problemas Identificados (Além da Corrupção)

### P1: Retry inadequado em delta_loader.py

```python
# Estado atual
_SHARD_MAX_RETRIES = 3
_SHARD_RETRY_BACKOFF = (2.0, 5.0, 15.0)  # máx 22 segundos total
```

3 tentativas com delays de 2s/5s/15s são inúteis quando o problema subjacente é instabilidade de PostgreSQL que persiste por horas. As 3 tentativas se esgotam em 22 segundos — a instabilidade continua.

**Melhoria**: Exponential backoff com jitter, mais tentativas, delays maiores.

### P2: Stale Watchdog com timeout fixo de 60 min

O watchdog marca runs como "stale" após 60 minutos sem heartbeat. TLDs grandes (org, xyz, info) legitimamente levam mais de 60 minutos. O `org` foi morto com 68 min — estava processando normalmente.

**Melhoria**: Timeout configurável por TLD ou por source (czds vs openintel).

### P3: Sem checkpoint/resume por shard

Se 1 shard de 128 falha, toda a run reinicia do zero. Uma run de 5 horas que falha no shard 120 de 128 perde 5 horas de progresso. `_parallel_load_shards` usa `fut.result()` que propaga a primeira exceção imediatamente.

**Melhoria**: Rastrear quais shards foram carregados com sucesso e retomar de onde parou.

### P4: Sem SWAP no servidor de produção

O servidor não tem swap configurado. Picos de memória durante inserção bulk de TLDs grandes (xyz = ~7M domínios) vão direto ao OOM killer. Atualmente 2.7GB de 11GB usados, mas inserções paralelas de 4 workers cada com datasets grandes podem estressar a memória.

**Melhoria**: Configurar 4–8 GB de SWAP no servidor.

### P5: Sem alerta para falhas repetidas do autovacuum

O loop de crash do autovacuum iniciou em 27/04 e passou 5 dias sem ser detectado/alertado. Não existe monitoramento que detecte quando autovacuum falha repetidamente no mesmo objeto.

**Melhoria**: Alerta quando o mesmo erro de autovacuum ocorre mais de N vezes em X minutos.

### P6: Dead tuples acumulando sem vacuum manual

Tabelas com alto volume de updates acumulam dead tuples. Exemplos de 01/05:
- `domain_org`: 12.1M live, **495k dead** (~4% bloat) — último autovacuum 29/04
- `domain_top`: 12.6M live, **309k dead** (~2.4% bloat) — último autovacuum 28/04
- `domain_net`: 13M live, **206k dead** (~1.6% bloat) — último autovacuum 29/04

Autovacuum está rodando nestas tabelas, mas a corrupção de `pg_class` pode interferir com o agendamento.

---

## Correção Imediata (Hotfix Obrigatório)

### Passo 1: Corrigir corrupção de pg_catalog.pg_class

```sql
-- Executar dentro do container PostgreSQL:
SET zero_damaged_pages = on;
VACUUM FREEZE VERBOSE pg_catalog.pg_class;
RESET zero_damaged_pages;
```

Se o `VACUUM FREEZE` falhar mesmo com `zero_damaged_pages`:
```bash
# Opção nuclear (exige downtime breve):
docker exec -it <postgres_container> pg_dumpall -U obs > /tmp/obs_dump.sql
# Recriar o banco e restaurar
```

### Passo 2: Verificar se a corrupção foi resolvida

```sql
-- Após o VACUUM FREEZE, deve retornar 0 erros:
SELECT oid, relname, relfrozenxid, age(relfrozenxid)
FROM pg_catalog.pg_class
WHERE relname = 'pg_class';
```

O autovacuum deve parar de crashar. Monitorar os logs por 5 minutos após o fix.

### Passo 3: Re-executar as runs que falharam

Via API admin:
```bash
# Re-trigger czds/xyz, czds/info (que falharam com unexpected_error)
# czds/org e openintel/ch foram marcados como stale_recovered e precisam de novo ciclo
```

---

## Melhorias de Código Recomendadas

### M1: Aumentar retry com exponential backoff (delta_loader.py)

```python
_SHARD_MAX_RETRIES = 6
_SHARD_RETRY_BACKOFF = (5.0, 30.0, 60.0, 120.0, 300.0, 600.0)
```

Adicionar jitter para evitar thundering herd quando múltiplos shards falham simultaneamente.

### M2: Timeout configurável no stale watchdog

Adicionar `stale_timeout_override` por TLD/source na tabela `ingestion_tld_policy`. TLDs grandes (xyz, info, org) devem ter timeout de 6–8 horas.

### M3: Checkpoint por shard

Registrar shards concluídos em tabela `ingestion_shard_checkpoint(run_id, shard_key, loaded_at)`. Na retentativa, pular shards já carregados.

### M4: Configurar SWAP no servidor de produção

```bash
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### M5: Alerta de autovacuum repetido

Adicionar job de monitoramento que consulta `pg_stat_bgwriter` e logs do PostgreSQL. Alertar via notificação quando o mesmo erro de autovacuum ocorre mais de 5 vezes em 10 minutos.

### M6: Cancelar futures pendentes em caso de falha (delta_loader.py)

Em `_parallel_load_shards`, quando `fut.result()` levanta exceção, os futures pendentes devem ser cancelados explicitamente para liberar recursos imediatamente.

---

## Timeline do Incidente (01/05/2026 UTC)

```
~00:00  Início do ciclo de ingestão
~00:00  Runs czds/xyz e czds/info iniciam (TLDs grandes, ~1 shard cada)
~04:00  openintel/ch inicia
~05:02  openintel/ch marcado como stale_recovered (61 min sem heartbeat)
~20:34  czds/org inicia
~21:42  czds/org marcado como stale_recovered (68 min)
~06:07  czds/xyz falha com psycopg2.OperationalError (6h 7min total)
~06:07  czds/info falha com psycopg2.OperationalError (6h 6min total)
XX:XX   czds/net completa com sucesso (~16 min, 406k domínios)

Contexto paralelo:
04:03→02/05  pg_class corruption crash loop: 1 crash/min, ininterrupto por 5+ dias
```

---

## Arquivos Relevantes

| Arquivo | Relevância |
|---------|-----------|
| `ingestion/ingestion/loader/delta_loader.py` | Retry logic (`_SHARD_MAX_RETRIES`, `_SHARD_RETRY_BACKOFF`), shard worker |
| `ingestion/ingestion/orchestrator/pipeline.py` | `_process_tld_local`, chamada a `load_delta` |
| `ingestion/ingestion/observability/run_recorder.py` | `touch_run`, `finish_run` — heartbeat do watchdog |
| `backend/app/models/ingestion_tld_policy.py` | `priority` column — local para adicionar `stale_timeout_seconds` |
| PostgreSQL container `e41fef3d8211` | `pg_catalog.pg_class` bloco 163 offset 13 corrompido |

---

## Critérios de Conclusão

- [ ] `VACUUM FREEZE pg_catalog.pg_class` executado com sucesso em produção
- [ ] Logs confirmam que autovacuum parou de crashar
- [ ] Runs de 01/05 re-executadas (xyz, info, org, ch)
- [ ] `_SHARD_MAX_RETRIES` e `_SHARD_RETRY_BACKOFF` atualizados
- [ ] SWAP configurado no servidor de produção
- [ ] Alerta de autovacuum adicionado ao stack de monitoramento
