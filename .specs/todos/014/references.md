# 014 — Referências

## Logs PostgreSQL (Evidência Principal)

**Erro de Corrupção (pg_catalog.pg_class):**
```
2026-04-27 19:52:15.517 UTC [144] ERROR:  found xmin 690691 from before relfrozenxid 762739
CONTEXT:  while scanning block 163 offset 13 of relation "pg_catalog.pg_class"
automatic vacuum of table "obs.pg_catalog.pg_class"
```
Padrão: a cada ~60 segundos, ininterruptamente desde 27/04 até pelo menos 02/05.

**Queda de conexão:**
```
could not receive data from client: Connection reset by peer
unexpected EOF on client connection with an open transaction
```

## Stack Trace da Ingestão (delta_loader.py)

```
ERROR: tld=xyz source=czds phase=full_run error: server closed the connection unexpectedly
  This probably means the server terminated abnormally before or while processing the request.
  [...]
  psycopg2.OperationalError: server closed the connection unexpectedly
```

## API de Ingestão

- `GET /v1/ingestion/runs?limit=200&status=failed&date=2026-05-01`
- `GET /v1/ingestion/cycles?date=2026-05-01`

## Arquivos de Código

- `ingestion/ingestion/loader/delta_loader.py` — linhas 36–37 (constantes de retry), 92–196 (`_load_shard_worker`), 199–240 (`_parallel_load_shards`)
- `ingestion/ingestion/orchestrator/pipeline.py` — linhas 310–318 (chamada `load_delta`), 374–380 (tratamento de exceção)

## Servidor de Produção

- Host: `158.69.211.109`
- PostgreSQL container: `e41fef3d8211` (imagem: `postgres:16-alpine`)
- Ingestion worker container: `aeba6cecace1`
- Stack Docker: `observador-ingestion`

## Tabelas com Bloat (01/05/2026)

| Tabela | Live | Dead | % Dead |
|--------|------|------|--------|
| domain_org | 12.1M | 495k | 4.0% |
| domain_top | 12.6M | 309k | 2.4% |
| domain_net | 13.0M | 206k | 1.6% |

## Comandos para Fix

```bash
# Verificar se corrupção está ativa
docker logs e41fef3d8211 2>&1 | grep "xmin.*relfrozenxid" | tail -3

# Acessar PostgreSQL
docker exec -it e41fef3d8211 psql -U obs -d obs

# Corrigir corrupção (dentro do psql)
SET zero_damaged_pages = on;
VACUUM FREEZE VERBOSE pg_catalog.pg_class;
RESET zero_damaged_pages;

# Verificar que o erro parou (aguardar 2 minutos após o fix)
docker logs e41fef3d8211 --since $(date -u -d '2 minutes ago' +%Y-%m-%dT%H:%M:%S) 2>&1 | grep xmin
```

## Documentação Relacionada

- PostgreSQL: [Vacuum Freeze e Transaction ID Wraparound](https://www.postgresql.org/docs/current/routine-vacuuming.html#VACUUM-FOR-WRAPAROUND)
- Issue relacionada: `.specs/todos/009/plan.md` (Correções de Confiabilidade no Monitoramento de Ingestão)
- Issue relacionada: `.specs/todos/010/plan.md` (Catálogo de Problemas: Ciclo de Ingestão)
- Issue relacionada: `.specs/todos/012/plan.md` (Incidente 29/04: 16 TLDs com falha)
