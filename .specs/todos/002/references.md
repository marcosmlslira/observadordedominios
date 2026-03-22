# 002 — Referências e Decisões

## Refinamentos base

- Documento principal NSEC: `docs/nsec-zone-walking-refinement.md`
- Documento complementar CZDS: `docs/czds-zone-ingestion-refinement.md`

## Decisões aprovadas

- N1: NSEC em worker dedicado, separado de CZDS.
- N2: execução longa fora de Lambda (Swarm/Fargate/ECS task).
- N3: processar apenas TLDs elegíveis com NSEC.
- N4: iniciar com `.br`.
- N5: remoção por soft delete (`deleted_at`).
- N6: snapshot raw obrigatório antes do delta.
- N7: rate limit DNS obrigatório e configurável.

## Objetivo técnico

Implementar ingestão complementar via NSEC com:

1. zone walking resiliente por TLD,
2. armazenamento raw versionado em S3/MinIO,
3. delta transacional no PostgreSQL,
4. rastreabilidade por run (`source='nsec'`),
5. convivência operacional com a pipeline CZDS.
