# 001 — Referências e Decisões

## Refinamento base

- Documento principal: `docs/czds-zone-ingestion-refinement.md`

## Decisões aprovadas

- P1: fase 1 com TLDs leves: `net`, `org`, `info`.
- P2: estratégia de remoção com **soft delete** (`deleted_at`).
- P3: execução em **worker dedicado** no Swarm.
- P4: ambiente de desenvolvimento com **MinIO** (S3 compatível).

## Objetivo técnico

Implementar ingestão CZDS fim-a-fim com:

1. download de zone file por TLD autorizado,
2. persistência raw em storage S3/MinIO,
3. parsing em stream,
4. delta real no PostgreSQL (novos, reativados, deletados),
5. rastreabilidade operacional por run.
