# Referências — 015

## Incidente e Operação

- Produção: `ubuntu@158.69.211.109`
- Worker ativo: `observador-ingestion_ingestion_worker`
- Modo testado: `INGESTION_EXECUTION_MODE_OPENINTEL=databricks_only`

## Evidências Coletadas

### Falha `ch` no Databricks

Erro observado:

- `Fatal error: The Python kernel is unresponsive`
- `exit code 137 (SIGKILL: Killed)`
- indicação explícita de `OOM`

Últimas mensagens relevantes:

- `openintel tld=ch mode=zonefile`
- `openintel tld=ch parsing snapshot_date=2026-05-01 mode=zonefile`

### Sucessos pontuais confirmados

- `jp` Databricks: `SUCCESS`
- `ee` Databricks: `SUCCESS`
- `info` Databricks: `SUCCESS`
- `org` Databricks: `SUCCESS`

### Evidencias de CZDS grande bem-sucedido

- `info`
  - `run_id`: `178581582640754`
  - URL: `https://dbc-3ba5a2e9-3491.cloud.databricks.com/?o=1275599411701381#job/809956233333153/run/178581582640754`
  - resultado: `SUCCESS`
  - metricas principais:
    - `snapshot`: `5643641`
    - `download_bytes`: `191595057`
    - `total_seconds`: `48.789`
    - `strategy`: `in_memory`

- `org`
  - `run_id`: `637963716577159`
  - URL: `https://dbc-3ba5a2e9-3491.cloud.databricks.com/?o=1275599411701381#job/218778008028792/run/637963716577159`
  - resultado: `SUCCESS`
  - metricas principais:
    - `snapshot`: `12810347`
    - `download_bytes`: `456693425`
    - `total_seconds`: `221.961`
    - `strategy`: `sharded`
    - `num_shards`: `128`

### Tamanhos de snapshots `zonefile`

- `ch`: 3 arquivos, 2.58 GB total
- `ee`: 1 arquivo, 92.5 MB total
- `fr`: 3 arquivos, 3.69 GB total
- `li`: 1 arquivo, 47.7 MB total
- `se`: 3 arquivos, 2.44 GB total
- `sk`: 1 arquivo, 585.9 MB total

## Arquivos Técnicos Relevantes

- `ingestion/ingestion/sources/openintel/client.py`
- `ingestion/ingestion/runners/openintel_runner.py`
- `ingestion/ingestion/databricks/submitter.py`
- `ingestion/ingestion/databricks/client.py`
- `ingestion/ingestion/orchestrator/pipeline.py`
- `backend/app/api/v1/routers/ingestion.py`
- `backend/app/schemas/czds_ingestion.py`
- `scripts/watch_ingestion.ps1`
- `scripts/watch_ingestion.sh`

## Observações de Arquitetura

- `hybrid`: só TLDs classificados como grandes vão para Databricks
- `databricks_only`: todos os TLDs da fonte vão para Databricks
- `ch` não está em `LARGE_TLDS`; por isso originalmente rodava localmente
- `CZDS` e `OpenINTEL` usam caminhos de ingestao distintos; sucesso em `CZDS` grande nao absolve o parser de `OpenINTEL`, mas prova que o ambiente suporta ao menos parte das cargas grandes

## Decisões Parciais

- Falha do `ch` não caracteriza falha global do Databricks
- Sucesso de `CZDS:info` e `CZDS:org` indica que o problema nao e "qualquer ingestao grande"
- `zonefile` grande precisa de tratamento próprio
- observabilidade Databricks deve ser persistida e exposta durante a execução
- não há opção operacional de aumentar memória/capacidade do ambiente atual
- a solução precisa respeitar as limitações de `serverless` e `community`
