# Tier 1 — Fundacao Operacional: Deploy do Worker e Limpeza de Dados

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tornar o pipeline de monitoramento de marcas operacional em producao — deploy do similarity_worker (causa raiz), correcao de configuracao, e limpeza de dados de perfis de marca.

**Architecture:** Tres mudancas independentes: (1) adicionar servico similarity_worker ao stack.yml de producao; (2) adicionar SIMILARITY_SCAN_CRON ao Settings para configuracao explicita via env var; (3) script de limpeza de dados para consolidar perfis duplicados e corrigir brand_label/alias_normalized incorretos via repair run.

**Tech Stack:** Docker Swarm (stack.yml), Python/FastAPI (config.py), PostgreSQL (via script de debug), APScheduler (similarity_worker.py ja implementado)

---

## Contexto do Problema

O `similarity_worker` existe em `stack.dev.yml` (linha 160-176) mas esta **ausente** do `stack.yml` (producao). Isso significa:
- Nenhum scan automatico executa em producao
- Scan jobs manuais via API nunca sao processados
- 11 de 12 marcas tem 0 matches

Adicionalmente, dados de marcas existentes tem inconsistencias:
- Alias "Tenda" normalizado como "enda" (sera corrigido automaticamente quando o worker rodar, pois chama `ensure_monitoring_profile_integrity`)
- Perfis duplicados: comgas, gsuplementos, listenx (versoes com e sem .com.br)
- brand_label incorreto: "comgas.com.br" ao inves de "comgas"

---

## Arquivos a Modificar

| Arquivo | Tipo | O que muda |
|---------|------|------------|
| `infra/stack.yml` | Modify | Adicionar servico `similarity_worker` |
| `backend/app/core/config.py` | Modify | Adicionar campo `SIMILARITY_SCAN_CRON` ao Settings |
| `backend/app/debug_scripts/repair_brand_profiles.py` | Create | Script de reparo e limpeza de perfis |

---

## Task 1: Adicionar SIMILARITY_SCAN_CRON ao Settings

**Arquivos:**
- Modify: `backend/app/core/config.py`

O worker ja lê com `getattr(settings, "SIMILARITY_SCAN_CRON", "0 9 * * *")` mas a config nao tem o campo. Adicionar explicitamente para que seja configuravel via env var sem cair no fallback silencioso.

- [ ] **Step 1: Adicionar o campo ao Settings**

Em `backend/app/core/config.py`, apos a secao `# ── CT Logs` (linha ~82), adicionar na secao de similarity:

```python
    # ── Similarity Worker ──────────────────────────────────────
    SIMILARITY_SCAN_CRON: str = "0 9 * * *"
    SIMILARITY_SCAN_ENABLED: bool = True
```

A adicao deve ficar entre as secoes `CT Logs` e `Free Tools`. O campo `SIMILARITY_SCAN_CRON` controla o horario do cron diario (padrao: 09:00 UTC, apos CZDS sync em 07:00).

- [ ] **Step 2: Verificar que o worker usa o campo via settings**

Em `backend/app/worker/similarity_worker.py` linha 31:
```python
SIMILARITY_CRON = getattr(settings, "SIMILARITY_SCAN_CRON", "0 9 * * *")
```

Atualizar para usar diretamente do settings sem fallback:
```python
SIMILARITY_CRON = settings.SIMILARITY_SCAN_CRON
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/config.py backend/app/worker/similarity_worker.py
git commit -m "feat: add SIMILARITY_SCAN_CRON to Settings for explicit env var config"
```

---

## Task 2: Adicionar similarity_worker ao stack.yml de producao

**Arquivos:**
- Modify: `infra/stack.yml`

Esta e a **mudanca de maior impacto** — uma adicao de ~18 linhas que habilita todo o monitoramento continuo.

- [ ] **Step 1: Adicionar o servico similarity_worker ao final de infra/stack.yml**

Adicionar ANTES da secao `networks:`, espelhando o bloco do `stack.dev.yml`:

```yaml
  similarity_worker:
    image: observadordedominios-backend:latest
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

**Nota:** Nao adicionar volume mount (nao e necessario em producao). Nao adicionar S3 vars (worker nao usa S3).

- [ ] **Step 2: Verificar que o arquivo esta correto**

```bash
cat infra/stack.yml | grep -A 20 "similarity_worker"
```

Esperado: ver o bloco completo do servico.

- [ ] **Step 3: Commit**

```bash
git add infra/stack.yml
git commit -m "fix: add similarity_worker to production stack — enables continuous monitoring"
```

---

## Task 3: Script de Reparo de Perfis de Marca

**Arquivos:**
- Create: `backend/app/debug_scripts/repair_brand_profiles.py`

Script para:
1. Listar todos os perfis com problemas (brand_label incorreto, aliases incorretos)
2. Chamar `ensure_monitoring_profile_integrity` em todos os perfis
3. Identificar perfis duplicados (mesma marca com e sem .com.br)
4. Reportar o estado antes e depois

O objetivo e preparar os dados antes do primeiro scan.

- [ ] **Step 1: Criar o script**

```python
"""Repair brand profiles — fix normalized labels and report duplicates.

Usage: docker exec -it <backend_container> python app/debug_scripts/repair_brand_profiles.py
"""
from __future__ import annotations

import sys
from app.infra.db.session import SessionLocal
from app.repositories.monitored_brand_repository import MonitoredBrandRepository
from app.services.use_cases.sync_monitoring_profile import ensure_monitoring_profile_integrity


def main() -> None:
    db = SessionLocal()
    try:
        repo = MonitoredBrandRepository(db)
        brands = repo.list_active()

        print(f"\n=== Brand Profile Repair Report ===")
        print(f"Total brands: {len(brands)}\n")

        for brand in brands:
            old_label = brand.brand_label
            old_aliases = [(a.alias_value, a.alias_normalized) for a in brand.aliases]

            print(f"[{brand.brand_name}] label={old_label}")
            for alias in brand.aliases:
                flag = " ← WRONG" if alias.alias_normalized != alias.alias_value.lower().replace(" ", "") else ""
                print(f"  alias: {alias.alias_value!r} → {alias.alias_normalized!r}{flag}")

            ensure_monitoring_profile_integrity(repo, brand)
            db.commit()
            db.refresh(brand)

            new_label = brand.brand_label
            if new_label != old_label:
                print(f"  ✓ brand_label: {old_label!r} → {new_label!r}")

            new_aliases = [(a.alias_value, a.alias_normalized) for a in brand.aliases]
            for (ov, on_), (nv, nn) in zip(old_aliases, new_aliases):
                if on_ != nn:
                    print(f"  ✓ alias {ov!r}: {on_!r} → {nn!r}")

            seed_count = len(brand.seeds)
            print(f"  Seeds: {seed_count}")
            print()

        # Report duplicates
        print("=== Potential Duplicate Profiles ===")
        labels: dict[str, list] = {}
        for brand in brands:
            # Normalize to base label for comparison
            base = brand.brand_label.replace(".com.br", "").replace(".com", "")
            labels.setdefault(base, []).append(brand)

        for base, group in labels.items():
            if len(group) > 1:
                print(f"\nDuplicate group '{base}':")
                for b in group:
                    has_official = bool(b.domains)
                    print(f"  ID={b.id} name={b.brand_name!r} label={b.brand_label!r} official_domains={has_official} seeds={len(b.seeds)}")
                print(f"  → RECOMMENDATION: Keep the one with official_domains=True, delete the other")

        print("\nRepair complete.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/debug_scripts/repair_brand_profiles.py
git commit -m "chore: add repair_brand_profiles script for data cleanup"
```

---

## Task 4: Deploy em Producao

- [ ] **Step 1: Build da imagem backend de producao**

Na maquina de producao (ou via CI):
```bash
docker build -t observadordedominios-backend:latest -f backend/Dockerfile backend/
```

Esperado: build completo sem erros.

- [ ] **Step 2: Push ao registry (se houver ECR)**

Se usando AWS ECR:
```bash
# Verificar tag atual e fazer push com nova imagem
docker tag observadordedominios-backend:latest <ECR_URI>/observadordedominios-backend:latest
docker push <ECR_URI>/observadordedominios-backend:latest
```

Se usando imagem local no servidor (stack sem registry remoto):
```bash
# Apenas garantir que a imagem esta disponivel no servidor
docker images | grep observadordedominios-backend
```

- [ ] **Step 3: Deploy da stack atualizada**

```bash
docker stack deploy -c infra/stack.yml obs
```

Esperado:
```
Creating service obs_similarity_worker
Updating service obs_frontend (id: ...)
Updating service obs_backend (id: ...)
```

- [ ] **Step 4: Verificar que o worker esta rodando**

```bash
docker service ls | grep similarity
```

Esperado: `obs_similarity_worker   1/1    Running`

```bash
docker service logs obs_similarity_worker --tail 50
```

Esperado: logs mostrando "Similarity Worker starting...", "Running initial scan cycle...", e para cada marca: "Scanning brand=X (label=Y)".

- [ ] **Step 5: Verificar que scans estao executando**

Aguardar ~2-5 minutos (scan inicial roda na startup do worker), depois:

```bash
docker service logs obs_similarity_worker --tail 100 | grep -E "(Scanning brand|complete:|matches)"
```

Esperado: mensagens de conclusao por marca com contagem de matches.

---

## Task 5: Executar Script de Reparo de Dados

- [ ] **Step 1: Encontrar o container do worker ou backend**

```bash
docker ps | grep obs_backend
# ou
docker ps | grep obs_similarity_worker
```

- [ ] **Step 2: Executar o script de reparo**

```bash
docker exec -it <CONTAINER_ID> python app/debug_scripts/repair_brand_profiles.py
```

Esperado: output mostrando correncoes de alias_normalized e lista de perfis duplicados.

- [ ] **Step 3: Revisar output e deletar perfis duplicados manualmente via API**

Para cada perfil duplicado identificado (ex: "comgas" sem official_domains):
```bash
# Via API — usar o ID do perfil SEM official_domains
curl -X DELETE "https://api.observadordedominios.com.br/v1/brands/<ID_DO_DUPLICADO>" \
  -H "Authorization: Bearer <TOKEN>"
```

Manter apenas o perfil com `official_domains=True`.

**Perfis a deletar (baseado em auditoria de 25/03/2026):**
- `1057e14f-...` comgas (sem dominio oficial) → deletar, manter `5142d941-...` comgas.com.br
- `1d99e8a9-...` gsuplementos (sem dominio oficial) → deletar, manter `f4dfffe0-...` gsuplementos.com.br
- `cb671950-...` listenx (sem dominio oficial) → deletar, manter `2270e52a-...` listenx.com.br

**ATENCAO:** Confirmar IDs via GET /v1/brands antes de deletar.

---

## Task 6: Validar Pipeline Completo Ponta-a-Ponta

- [ ] **Step 1: Verificar matches sendo criados**

```bash
# Login
TOKEN=$(curl -s -X POST "https://api.observadordedominios.com.br/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@observador.com","password":"mls1509ti"}' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Verificar matches para Tenda (deve ter 2000+)
curl -s "https://api.observadordedominios.com.br/v1/brands/857708a8-26eb-450f-806d-c9c2e77d5ad8/matches?limit=1" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

Esperado: `"total": 2629` (ou mais, se novos matches foram adicionados).

- [ ] **Step 2: Verificar matches para marcas que tinham 0 (Itau, Caixa)**

```bash
# Itau
curl -s "https://api.observadordedominios.com.br/v1/brands/ffe0e18d-<ID>/matches?limit=5" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

Esperado: `"total"` maior que 0 (pode levar ate 1h para scan inicial completar).

- [ ] **Step 3: Verificar que paginas do frontend funcionam**

Acessar no browser:
- https://observadordedominios.com.br/admin/matches → deve mostrar tabela de matches
- https://observadordedominios.com.br/admin/tools → deve mostrar ferramentas livres

Se ainda retornar 404, investigar build do frontend (pode ser problema de deploy separado).

- [ ] **Step 4: Verificar que Tenda nao aparece nos matches de Tenda**

```bash
# Verificar se aliases de Tenda estao corretos apos repair
curl -s "https://api.observadordedominios.com.br/v1/brands/857708a8-26eb-450f-806d-c9c2e77d5ad8" \
  -H "Authorization: Bearer $TOKEN" | python -c "
import sys, json
b = json.load(sys.stdin)
for a in b.get('aliases', []):
    print(f\"{a['alias_type']}: value={a['alias_value']!r} normalized={a['alias_normalized']!r}\")
"
```

Esperado: alias "Tenda" com `alias_normalized="tenda"` (nao "enda").

- [ ] **Step 5: Commit final de validacao**

```bash
git tag -a "tier1-complete" -m "Tier 1 operational foundation complete"
git push && git push --tags
```

---

## Criterios de Sucesso

| Criterio | Como Verificar |
|----------|---------------|
| Worker rodando em producao | `docker service ls` mostra 1/1 replicas |
| Scans iniciando automaticamente | Logs do worker mostram "Scanning brand=..." |
| Alias "Tenda" normalizado corretamente | API mostra alias_normalized="tenda" |
| Itau/Caixa com matches > 0 | GET /v1/brands/{id}/matches retorna total > 0 |
| Sem perfis duplicados | GET /v1/brands retorna 1 perfil por marca |
| Frontend acessivel | /admin/matches e /admin/tools abrem sem 404 |

---

## Rollback

Se o worker causar problemas de carga no banco:

```bash
# Remover o servico similarity_worker sem afetar outros servicos
docker service rm obs_similarity_worker
```

O resto da stack continua funcionando. O worker pode ser re-adicionado com SIMILARITY_SCAN_CRON ajustado para horario de menor carga.
