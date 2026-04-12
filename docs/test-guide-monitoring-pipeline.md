# Guia de Testes — Monitoring Pipeline (Plans 3 & 4)

> **Destinatário:** Testador que não participou da implementação.  
> **Escopo:** API layer (Plan 3) + Frontend UI (Plan 4).  
> **Pré-requisito:** Stack rodando em dev (`docker stack deploy -c infra/stack.dev.yml obs`).  
> **URL base da API:** `http://localhost:8000`  
> **Frontend:** `http://localhost:3000`  
> **Autenticação:** todas as chamadas precisam de `Authorization: Bearer <token>` obtido via `POST /v1/auth/token`.

---

## 1. Setup

```bash
# Obter token de admin
curl -s -X POST http://localhost:8000/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@observador.com","password":"<senha>"}' \
  | jq .access_token

# Guardar em variável para facilitar
TOKEN="<token acima>"
AUTH="Authorization: Bearer $TOKEN"
```

> **Nota:** Se não houver brands cadastrados, crie um antes de testar os endpoints de monitoring.

```bash
# Criar brand de teste (se necessário)
curl -s -X POST http://localhost:8000/v1/brands \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"brand_name":"Teste Brand","official_domains":["testebrand.com.br"],"tld_scope":["com","net","org"]}' \
  | jq .id
# Guardar o ID retornado
BRAND_ID="<id acima>"
```

---

## 2. API — `GET /v1/brands` (lista com monitoring_summary)

### O que foi adicionado

O endpoint já existia. Agora cada objeto `Brand` retornado inclui o campo `monitoring_summary` com dados agregados do pipeline de monitoramento.

### Verificar

```bash
curl -s "http://localhost:8000/v1/brands?active_only=false" \
  -H "$AUTH" | jq '.items[0].monitoring_summary'
```

### Comportamento esperado

```json
{
  "latest_cycle": {
    "id": "<uuid>",
    "status": "completed",
    "finished_at": "2026-04-12T15:00:00Z",
    "scan_job_id": "<uuid ou null>"
  },
  "threat_counts": {
    "immediate_attention": 3,
    "defensive_gap": 7,
    "watchlist": 12
  },
  "overall_health": "warning"
}
```

**Se o brand não tiver ciclos ainda:**
```json
{
  "latest_cycle": null,
  "threat_counts": { "immediate_attention": 0, "defensive_gap": 0, "watchlist": 0 },
  "overall_health": "unknown"
}
```

**Regras do `overall_health`:**
- `"critical"` → algum domínio oficial tem check crítico ou há ameaças imediatas
- `"warning"` → checks com problema não-crítico
- `"healthy"` → todos os checks OK
- `"unknown"` → sem dados de ciclo ainda

---

## 3. API — `GET /v1/brands/{id}` (detalhe com monitoring_summary)

```bash
curl -s "http://localhost:8000/v1/brands/$BRAND_ID" \
  -H "$AUTH" | jq '{brand_name: .brand_name, monitoring_summary: .monitoring_summary}'
```

**Comportamento esperado:** mesmo shape do `monitoring_summary` descrito acima. O campo não deve ser `null` mesmo sem dados — deve retornar `threat_counts` zerados e `overall_health: "unknown"`.

---

## 4. API — `GET /v1/brands/{id}/health`

Novo endpoint. Retorna resultados dos health checks de cada domínio oficial do brand.

```bash
curl -s "http://localhost:8000/v1/brands/$BRAND_ID/health" \
  -H "$AUTH" | jq .
```

### Comportamento esperado

```json
{
  "domains": [
    {
      "domain_id": "<uuid>",
      "domain_name": "testebrand.com.br",
      "is_primary": true,
      "overall_status": "healthy",
      "dns": { "ok": true },
      "ssl": { "ok": true, "details": { "days_remaining": 45 } },
      "email_security": { "ok": false, "details": { "spoofing_risk": "high" } },
      "headers": { "ok": true, "details": { "score": "good" } },
      "takeover": { "ok": true },
      "blacklist": { "ok": true },
      "safe_browsing": { "ok": true },
      "urlhaus": { "ok": true },
      "phishtank": { "ok": true },
      "suspicious_page": { "ok": false },
      "last_check_at": "2026-04-12T10:00:00Z"
    }
  ]
}
```

**Campos opcionais:** qualquer check pode ser `null` se o worker ainda não rodou para aquele domínio. O frontend trata isso exibindo `—`.

**Edge cases a verificar:**
- Brand sem domínios oficiais → `"domains": []`
- Domínio com `is_active: false` → não aparece na lista
- `last_check_at: null` → check ainda não realizado

---

## 5. API — `GET /v1/brands/{id}/cycles`

Histórico de ciclos de monitoramento.

```bash
curl -s "http://localhost:8000/v1/brands/$BRAND_ID/cycles?limit=10&offset=0" \
  -H "$AUTH" | jq .
```

### Comportamento esperado

```json
{
  "items": [
    {
      "id": "<uuid>",
      "brand_id": "<uuid>",
      "cycle_date": "2026-04-12",
      "status": "completed",
      "domains_checked": 1500,
      "threats_found": 5,
      "finished_at": "2026-04-12T15:30:00Z",
      "scan_job_id": "<uuid ou null>",
      "created_at": "2026-04-12T14:00:00Z"
    }
  ],
  "total": 1
}
```

**Edge cases:**
- Brand sem ciclos → `"items": [], "total": 0`
- Paginação: testar `?limit=5&offset=5` quando `total > 5`

---

## 6. API — `GET /v1/brands/{id}/matches?include_llm=true`

### Diferença do comportamento anterior

Sem `include_llm` (ou `include_llm=false`): retorna `MatchListResponse` clássico com campos raw da `similarity_match`.

**Com `include_llm=true`**: retorna `MatchSnapshotListResponse` — dados derivados do pipeline de scoring, ordenados por `derived_score` DESC.

```bash
# Legado (sem include_llm)
curl -s "http://localhost:8000/v1/brands/$BRAND_ID/matches?limit=5" \
  -H "$AUTH" | jq '{total: .total, first_item_keys: (.items[0] | keys)}'

# Novo (com include_llm)
curl -s "http://localhost:8000/v1/brands/$BRAND_ID/matches?include_llm=true&limit=5" \
  -H "$AUTH" | jq '{total: .total, first_item_keys: (.items[0] | keys)}'
```

### Campos exclusivos do `include_llm=true`

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `derived_score` | `float \| null` | Score composto pelo pipeline de scoring |
| `derived_bucket` | `string \| null` | `immediate_attention`, `defensive_gap`, `watchlist` |
| `derived_risk` | `string \| null` | `low`, `medium`, `high`, `critical` |
| `derived_disposition` | `string \| null` | Disposição sugerida pelo pipeline |
| `active_signals` | `array` | Sinais ativos com `code`, `severity`, `label`, `description` |
| `signal_codes` | `string[]` | Lista de códigos dos sinais ativos |
| `llm_assessment` | `object \| null` | Parecer do LLM |
| `state_fingerprint` | `string \| null` | Hash do estado para detectar mudanças |
| `last_derived_at` | `datetime \| null` | Quando o pipeline rodou pela última vez |

### Filtros disponíveis com `include_llm=true`

```bash
# Filtrar por bucket
curl -s "http://localhost:8000/v1/brands/$BRAND_ID/matches?include_llm=true&bucket=immediate_attention" \
  -H "$AUTH" | jq .total

# Excluir auto-dismissed (padrão: true)
curl -s "http://localhost:8000/v1/brands/$BRAND_ID/matches?include_llm=true&exclude_auto_dismissed=false" \
  -H "$AUTH" | jq .total
```

**Verificar que:** `total` com `exclude_auto_dismissed=true` ≤ `total` com `exclude_auto_dismissed=false`.

---

## 7. API — `GET /v1/matches/{id}/events`

```bash
# Pegar um match_id qualquer
MATCH_ID=$(curl -s "http://localhost:8000/v1/brands/$BRAND_ID/matches?limit=1" \
  -H "$AUTH" | jq -r '.items[0].id')

curl -s "http://localhost:8000/v1/matches/$MATCH_ID/events?limit=20" \
  -H "$AUTH" | jq .
```

### Comportamento esperado

```json
{
  "items": [
    {
      "id": "<uuid>",
      "match_id": "<uuid>",
      "event_type": "signal_detected",
      "severity": "high",
      "summary": "DNS apontando para IP suspeito",
      "detail": { "ip": "1.2.3.4", "tool": "dns_lookup" },
      "tool_name": "dns_lookup",
      "signal_code": "INFRA_SUSPICIOUS_IP",
      "created_at": "2026-04-12T10:00:00Z"
    }
  ],
  "total": 1
}
```

**Edge cases:**
- Match sem eventos → `"items": [], "total": 0`
- `match_id` inexistente → `HTTP 404` com `{"detail": "Match not found"}`

---

## 8. Frontend — `/admin/brands` (card grid)

Abrir `http://localhost:3000/admin/brands`.

### Verificações visuais

| Elemento | O que verificar |
|----------|-----------------|
| Layout | Deve ser um **grid de cards** (não tabela). Em telas largas: 3 colunas; em médias: 2 colunas; em pequenas: 1 coluna |
| Card — header | Nome do brand + label em fonte mono menor |
| Card — health badge | Badge colorido: `destructive` para critical, `secondary` para warning, `outline` para healthy/unknown |
| Card — inactive badge | Brands com `is_active: false` mostram badge extra "inactive" |
| Card — contadores | 3 caixinhas: Immediate (fundo vermelho translúcido), Defensive (fundo secondary), Watchlist (fundo muted) |
| Card — domínios | Até 3 domínios como badges; se houver mais, mostra `+N` |
| Card — ações | Botão "Scan" (chama `POST /v1/brands/{id}/scan`) e botão de lixeira (abre confirm dialog) |
| Card — link | Clicar no card navega para `/admin/brands/{id}` |
| Card hover | Seta "View →" fica mais visível ao passar o mouse |
| Skeleton | Durante carregamento, mostra 3 skeletons no lugar dos cards |
| Empty state | Se não houver brands, mostra mensagem centrada no lugar do grid |

### Verificar que o botão Scan não navega

Clicar em "Scan" **não deve navegar** para a página do brand. O `e.preventDefault()` intercepta o clique do `<Link>` pai.

### Criar e deletar brand

O modal de criação e o confirm de deleção devem funcionar igual antes (comportamento não mudou).

---

## 9. Frontend — `/admin/brands/{id}` (página de detalhe)

Navegar para `http://localhost:3000/admin/brands/<brand-id>`.

### Seção: Header

| Elemento | Comportamento esperado |
|----------|----------------------|
| Botão voltar | `← Monitoring Profiles` — navega para `/admin/brands` |
| Nome + label | Nome do brand em destaque, label em mono menor |
| Health badge | Mesmo mapeamento de cores do card grid |
| Badge "inactive" | Aparece só se `is_active: false` |
| Contadores | 3 números grandes: Immediate/Defensive/Watchlist |
| Botão "Trigger Scan" | Chama `POST /v1/brands/{id}/scan`; exibe "Queuing..." durante a chamada; não navega |

### Seção: Latest Monitoring Cycle

Só aparece se `monitoring_summary.latest_cycle !== null`.

| Elemento | Comportamento esperado |
|----------|----------------------|
| Status badge | `outline` para `completed`, `secondary` para outros |
| Finished at | Formatado como data/hora local |
| Ausência de ciclo | Seção não renderizada |

### Seção: Domain Health

Só aparece se o brand tiver domínios oficiais com dados de health.

| Elemento | Comportamento esperado |
|----------|----------------------|
| Tabela | Uma linha por domínio ativo |
| Coluna DNS/SSL/Email/Headers/Blacklist | `✓` verde se `ok: true`, `✗` vermelho se `ok: false`, `—` se campo ausente (check não realizado) |
| Badge "primary" | Aparece inline no nome do domínio primário |
| Last Check | Data local; `—` se `last_check_at: null` |

### Seção: Threats

| Elemento | Comportamento esperado |
|----------|----------------------|
| Filtros de bucket | Botões: All / Immediate / Defensive Gap / Watchlist — o selecionado fica com variante `default` (escuro) |
| Tabela | Colunas: Domain, Bucket, Score, Risk, Signals, Detected |
| Score | Mostra `derived_score` em %; `—` se nulo |
| Risk | Badge colorido; só aparece se `derived_risk` não for null |
| Signals | Até 3 códigos como badge mono; `+N` se houver mais |
| Clicar linha | Abre `MatchDrawer` |
| Paginação | Aparece só quando `total > 50`; Previous desabilitado na primeira página; Next desabilitado na última |
| Empty state | "No threats found" — quando filtro de bucket está ativo, exibe o nome do bucket |
| Skeleton | Durante carregamento de snapshots |

### Seção: Brand Configuration (collapsible)

| Elemento | Comportamento esperado |
|----------|----------------------|
| Estado inicial | **Fechado** — só o título e seta para baixo aparecem |
| Clicar no header | Abre/fecha a seção |
| Conteúdo | Official domains, Keywords, Aliases, TLD scope (scrollável se muitos), Notes |
| TLD scope | Max-height com overflow-y; todos os TLDs em badge mono com ponto prefix |

### Seção: Cycle History (collapsible)

| Elemento | Comportamento esperado |
|----------|----------------------|
| Estado inicial | **Fechado** |
| Título | Mostra total entre parênteses, ex: `Cycle History (12)` |
| Só aparece quando | `cycles.items.length > 0` |
| Conteúdo | Tabela com Date, Status, Domains Checked, Threats Found, Finished |

---

## 10. Frontend — MatchDrawer

Clicar em qualquer linha de ameaça na seção Threats.

### Abertura

| Elemento | Comportamento esperado |
|----------|----------------------|
| Dialog | Abre um Dialog `max-w-2xl` centralizado |
| Título | `domain_name.tld` em fonte mono |
| Subtítulo | Badges: `derived_bucket` (colorido), `derived_risk` (se não null), auto_disposition (se não null) |
| Fechar | Clicar fora do dialog ou no X fecha sem salvar |

### Scores

Grid 2 colunas com: Derived Score, Similarity Score, First Detected, Domain Registered.

### Active Signals

| Elemento | Comportamento esperado |
|----------|----------------------|
| Só aparece quando | `active_signals.length > 0` |
| Por sinal | Badge de severity + código mono + label à direita; descrição em texto menor abaixo |
| Cores de severity | `critical`/`high` → destructive; `medium` → secondary; resto → outline |

### LLM Assessment

| Elemento | Comportamento esperado |
|----------|----------------------|
| Só aparece quando | `llm_assessment !== null` |
| Header | Risk X/100 (colorido por threshold: ≥70 red, ≥40 yellow, <40 outline) + categoria |
| Corpo | `parecer_resumido` em texto; lista de `principais_motivos` (bullet list); `recomendacao_acao` em caixa destacada |

### Event Timeline

| Elemento | Comportamento esperado |
|----------|----------------------|
| Carregamento | Skeleton enquanto `GET /v1/matches/{id}/events` está em andamento |
| Com eventos | Lista scrollável (max-h-48): data + badge de severity + event_type + summary |
| Sem eventos | "No events recorded yet." |
| Ordem | Mais recente primeiro (como retornado pela API) |

### Review / Status Update

| Elemento | Comportamento esperado |
|----------|----------------------|
| Select de status | `new`, `reviewing`, `dismissed`, `confirmed_threat` |
| Estado inicial | `"new"` (reset a cada abertura do drawer) |
| Notes | Input texto livre |
| Botão Save | Chama `PATCH /v1/matches/{id}` com `{status, notes}`; exibe "Saving..." durante a chamada |
| Após salvar | Drawer fecha; lista de snapshots re-carrega (reflete mudança de status) |

---

## 11. Frontend — Navegação

### Verificar que "Similarity Matches" sumiu do nav

O item de navegação lateral **não deve mais existir**. A barra lateral deve ter apenas:

1. Dashboard
2. Ingestion Runs
3. Monitored Brands
4. Free Tools

### Verificar que `/admin/matches` não existe mais

Acessar `http://localhost:3000/admin/matches` deve retornar **404** (Next.js page not found), não a página antiga de matches.

---

## 12. Edge Cases Gerais

### Brand sem matches

Em `/admin/brands/{id}`, seção Threats deve mostrar "No threats found." sem erro.

### Brand sem domínios oficiais

Seção "Domain Health" não deve aparecer (array vazio).

### Token expirado

A API deve retornar `401`. O frontend deve redirecionar para `/login` automaticamente.

### Paginação em `/v1/brands/{id}/matches?include_llm=true`

```bash
# Criar cenário com muitos matches (se disponível) ou testar com limit=2
curl -s "http://localhost:8000/v1/brands/$BRAND_ID/matches?include_llm=true&limit=2&offset=0" \
  -H "$AUTH" | jq '{total, count: (.items | length)}'

# O count deve ser 2 (ou menos se total < 2)
# Navegar para próxima página
curl -s "http://localhost:8000/v1/brands/$BRAND_ID/matches?include_llm=true&limit=2&offset=2" \
  -H "$AUTH" | jq '{total, count: (.items | length)}'
```

**Verificar que:** `total` é igual nas duas chamadas (o count total não muda com o offset).

---

## 13. Checklist Rápido

Use este checklist para uma passagem rápida de fumaça:

- [ ] `GET /v1/brands` retorna `monitoring_summary` em cada item
- [ ] `GET /v1/brands/{id}` retorna `monitoring_summary`
- [ ] `GET /v1/brands/{id}/health` retorna `{ domains: [...] }`
- [ ] `GET /v1/brands/{id}/cycles` retorna `{ items: [...], total: N }`
- [ ] `GET /v1/brands/{id}/matches?include_llm=true` retorna campos derivados (`derived_score`, `active_signals`, etc.)
- [ ] `GET /v1/matches/{id}/events` retorna `{ items: [...], total: N }`
- [ ] `GET /v1/matches/uuid-invalido/events` retorna `HTTP 404`
- [ ] `/admin/brands` exibe cards (não tabela)
- [ ] Cards mostram health badge e contadores de ameaça
- [ ] Clicar no card navega para `/admin/brands/{id}`
- [ ] Botão Scan no card não navega (fica na mesma página)
- [ ] `/admin/brands/{id}` carrega sem erros
- [ ] Seção Config começa fechada; abre ao clicar
- [ ] Clicar em linha da tabela de Threats abre o MatchDrawer
- [ ] MatchDrawer carrega eventos da API
- [ ] Salvar status no drawer fecha o drawer e recarrega a lista
- [ ] Nav lateral não tem "Similarity Matches"
- [ ] `/admin/matches` retorna 404
