# 004 — Adicionar similarity_worker ao docker-stack-infra

## Contexto

O serviço `similarity_worker` foi adicionado ao `infra/stack.yml` deste repo (commit `394c65c`),
mas o stack real de produção vive no repositório separado `docker-stack-infra`.

Esta tarefa é para o agente que opera o `docker-stack-infra`.

## O que fazer

Adicionar o bloco abaixo ao `stack.yml` do `docker-stack-infra` (antes da seção `networks:`),
usando a imagem correta do GHCR (mesma usada pelos outros serviços do backend):

```yaml
  similarity_worker:
    image: ghcr.io/<GHCR_OWNER>/observador-backend:latest
    command: ["python", "-m", "app.worker.similarity_worker"]
    environment:
      - ENVIRONMENT=production
      - DATABASE_URL=postgresql://obs:obs@postgres:5432/obs
      - SIMILARITY_SCAN_CRON=0 9 * * *
    networks:
      - app-network
    depends_on:
      - postgres
    deploy:
      replicas: 1
      restart_policy:
        condition: on-failure
```

**Nota:** Substituir `<GHCR_OWNER>` pelo valor real usado nos outros serviços do stack.

## Por que isso importa

O `similarity_worker` é a causa raiz de nenhum scan automático rodar em produção.
Sem ele:
- Nenhum scan diário executa (cron `0 9 * * *`)
- Scan jobs manuais via API nunca são processados
- 11 de 12 marcas têm 0 matches

O código do worker está completo e testado. Só falta o serviço ser deployado.

## Validação pós-deploy

```bash
# Verificar que o serviço subiu
docker service ls | grep similarity

# Verificar logs de startup
docker service logs observador_similarity_worker --tail 50
```

Esperado nos logs:
```
Similarity Worker starting...
Cron schedule: 0 9 * * *
Running initial scan cycle...
Starting similarity scan cycle for N brands
Scanning brand=itau (label=itau)
...
```

## Referência

- Commit de referência: `394c65c` em `observadordedominios` (main)
- Arquivo de referência: `infra/stack.yml` deste repo
- Plano completo: `docs/superpowers/plans/2026-03-25-tier1-operacional.md`
- Plano estratégico: `.specs/features/domain_similarity/strategic_improvement_plan.md`
