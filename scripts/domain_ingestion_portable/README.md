# Domain Ingestion Portable (Current Method)

Pipeline portavel para CZDS + OpenINTEL com Polars, gravando direto no R2.

Metodo atual:
- CZDS em modo sharded (hash estavel por dominio).
- OpenINTEL incremental (modular existente).
- Persistencia em parquet no R2.

## Estrutura
- `config.py`: configuracao central.
- `storage.py`: adaptador de storage S3-compativel (R2).
- `sources/czds.py`: autenticacao e discovery CZDS.
- `sources/openintel.py`: discovery/parsing OpenINTEL.
- `state_engine.py`: regra de diff e estado (`domains_current`).
- `runner_sharded.py`: orquestrador atual (CZDS sharded + OpenINTEL incremental).
- `runner.py`: legado (mantido apenas para fallback).
- `../run_domain_ingestion_portable.py`: entrypoint com variaveis simples.

## Como rodar
```bash
pip install requests boto3 botocore polars pyarrow
python scripts/run_domain_ingestion_portable.py
```

No entrypoint:
- `PIPELINE_METHOD = "sharded"` usa o metodo atual.
- `PIPELINE_METHOD = "legacy"` usa o fluxo antigo.

## Parametros chave do metodo atual
- `use_sharded_czds`
- `shard_count`
- `ingest_chunk_rows`
- `cleanup_stage_after_success`
- `enforce_all_tlds_success` (falha ao final se qualquer TLD esperado nao tiver marker de sucesso)
- `snapshot_date_override` (CZDS/OpenINTEL, aceita data fixa ou `today` via entrypoint)

## Modelo de dados
- `domains_current`: estado atual por `source/tld/shard`.
- `new_domains`: adicionados por snapshot.
- `removed_domains`: removidos por snapshot.
- `ingestion_runs`: auditoria por run.
- `markers`: idempotencia por `source+tld+date`.
- `snapshot_stage`: stage temporario por shard (removivel ao final).

## Preservacao de dado bruto
- `domain_raw` preserva texto lido.
- `domain_raw_b64` preserva bytes originais em base64.
- `domain_norm` e usado para comparacao/diff.
