# Monitoring Model Redesign — Event-Sourced Architecture

**Data:** 2026-04-11
**Status:** Aprovado
**Escopo:** Modelo de monitoramento completo — pipeline, modelo de dados, API, frontend

---

## 1. Contexto e Motivação

### Problema

O evaluation report (2026-03-27) avaliou o produto como **3.8/10**. Problemas críticos:

1. **Scan inoperante** — tabela `similarity_scan_job` ausente em produção, 10/10 marcas com scan `queued` indefinidamente
2. **Enrichment inativo** — 8800+ matches, zero enriquecidos automaticamente
3. **Zero immediate_attention** — bucket mais importante vazio para todas as marcas
4. **Score puramente léxico** — `mycaixa.com.br` (legítimo, 0.699) > `caixagov.com.br` (phishing, 0.698)
5. **Falha silenciosa** — API aceita scans mas nunca processa, sem feedback ao usuário
6. **UX confusa** — duas páginas separadas (`/admin/brands` e `/admin/matches`), sem contexto unificado

### Objetivo

Transformar o sistema num produto **10/10** que:
- Monitora brands diariamente com confiança visível
- Mostra saúde dos domínios do cliente (postura defensiva)
- Detecta e prioriza ameaças reais com enrichment automático
- Explica cada ameaça via LLM com eficiência de custo
- Apresenta tudo numa interface unificada e acionável

---

## 2. Decisões de Design

| Decisão | Escolha | Alternativas Consideradas |
|---|---|---|
| Arquitetura | Event-sourced com materialização | Incremental (A), Ciclo unificado (B) |
| Ciclo de monitoramento | 4 workers independentes | Ciclo único sequencial |
| LLM reassessment | Fingerprint de estado + TTL 7 dias | Re-avaliação a cada ciclo |
| LLM escopo | Parecer geral apenas | Explicação por item individual |
| Health check | 10 ferramentas contra domínios oficiais | 5 ferramentas (escopo reduzido) |
| Enrichment budget | Top 50 matches/brand/ciclo | Enriquecer todos |
| Ruído | Auto-dismiss + auto-escalation | Apenas auto-dismiss |
| IA frontend | Tudo dentro de `/admin/brands/{id}` | Páginas separadas brands + matches |
| Layout brand list | Cards com status visual | Tabela com indicadores |
| Layout brand detail | Seções empilhadas (scroll) | Tabs |
| Match detail | Drawer lateral | Página dedicada |

---

## 3. Modelo de Dados

### 3.1 Tabelas Existentes — Ajustes

#### `similarity_match` — Novos campos

```sql
ALTER TABLE similarity_match ADD COLUMN state_fingerprint VARCHAR(64);
ALTER TABLE similarity_match ADD COLUMN last_fingerprint_at TIMESTAMPTZ;
ALTER TABLE similarity_match ADD COLUMN auto_disposition VARCHAR(32);  -- "auto_dismissed" | "auto_escalated" | NULL
ALTER TABLE similarity_match ADD COLUMN auto_disposition_reason TEXT;
ALTER TABLE similarity_match ADD COLUMN enrichment_budget_rank INTEGER;
```

### 3.2 Novas Tabelas

#### `monitoring_event` — Eventos imutáveis (coração do event-sourcing)

Cada execução de ferramenta, contra qualquer domínio (oficial ou match), gera um evento imutável.

```sql
CREATE TABLE monitoring_event (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id     UUID NOT NULL,
    event_type          VARCHAR(48) NOT NULL,    -- "tool_execution" | "llm_assessment" | "state_change" | "auto_disposition"
    event_source        VARCHAR(32) NOT NULL,    -- "health_check" | "enrichment" | "manual" | "scan"

    -- Polimorfismo: liga a um match OU brand_domain, nunca ambos
    match_id            UUID REFERENCES similarity_match(id) ON DELETE CASCADE,
    brand_domain_id     UUID REFERENCES monitored_brand_domain(id) ON DELETE CASCADE,
    brand_id            UUID NOT NULL REFERENCES monitored_brand(id) ON DELETE CASCADE,

    -- Dados do evento
    tool_name           VARCHAR(48),             -- "dns_lookup", "whois", "ssl_check", etc.
    tool_version        VARCHAR(16),
    result_data         JSONB NOT NULL,           -- payload completo (imutável)
    signals             JSONB,                    -- [{code, severity, score_adjustment, description}]
    score_snapshot      JSONB,                    -- snapshot do score no momento

    -- Metadados
    cycle_id            UUID REFERENCES monitoring_cycle(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    ttl_expires_at      TIMESTAMPTZ,

    -- Constraint: exatamente um target
    CONSTRAINT chk_event_target CHECK (
        (match_id IS NOT NULL AND brand_domain_id IS NULL) OR
        (match_id IS NULL AND brand_domain_id IS NOT NULL)
    )
);

CREATE INDEX ix_event_match ON monitoring_event (match_id, created_at DESC);
CREATE INDEX ix_event_brand_domain ON monitoring_event (brand_domain_id, created_at DESC);
CREATE INDEX ix_event_brand_cycle ON monitoring_event (brand_id, cycle_id);
CREATE INDEX ix_event_tool_latest ON monitoring_event (match_id, tool_name, created_at DESC);
```

#### `monitoring_cycle` — Ciclo de monitoramento diário

Um cycle por brand por dia. Agrega progresso de todas as etapas.

```sql
CREATE TABLE monitoring_cycle (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id                UUID NOT NULL REFERENCES monitored_brand(id) ON DELETE CASCADE,
    organization_id         UUID NOT NULL,
    cycle_date              DATE NOT NULL,
    cycle_type              VARCHAR(16) NOT NULL DEFAULT 'scheduled',  -- "scheduled" | "manual"

    -- Etapas
    health_status           VARCHAR(16) NOT NULL DEFAULT 'pending',
    health_started_at       TIMESTAMPTZ,
    health_finished_at      TIMESTAMPTZ,

    scan_status             VARCHAR(16) NOT NULL DEFAULT 'pending',
    scan_started_at         TIMESTAMPTZ,
    scan_finished_at        TIMESTAMPTZ,
    scan_job_id             UUID REFERENCES similarity_scan_job(id) ON DELETE SET NULL,

    enrichment_status       VARCHAR(16) NOT NULL DEFAULT 'pending',
    enrichment_started_at   TIMESTAMPTZ,
    enrichment_finished_at  TIMESTAMPTZ,
    enrichment_budget       INTEGER DEFAULT 0,
    enrichment_total        INTEGER DEFAULT 0,

    -- Resumo
    new_matches_count       INTEGER DEFAULT 0,
    escalated_count         INTEGER DEFAULT 0,
    dismissed_count         INTEGER DEFAULT 0,
    threats_detected        INTEGER DEFAULT 0,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (brand_id, cycle_date)
);

CREATE INDEX ix_cycle_brand_date ON monitoring_cycle (brand_id, cycle_date DESC);
```

#### `brand_domain_health` — Estado derivado dos domínios oficiais

Materialização do último health check. Atualizada a cada ciclo.

```sql
CREATE TABLE brand_domain_health (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_domain_id     UUID NOT NULL UNIQUE REFERENCES monitored_brand_domain(id) ON DELETE CASCADE,
    brand_id            UUID NOT NULL REFERENCES monitored_brand(id) ON DELETE CASCADE,
    organization_id     UUID NOT NULL,

    -- Estado derivado
    overall_status      VARCHAR(16) NOT NULL DEFAULT 'unknown',  -- "healthy" | "warning" | "critical" | "unknown"
    dns_ok              BOOLEAN,
    ssl_ok              BOOLEAN,
    ssl_days_remaining  INTEGER,
    email_security_ok   BOOLEAN,
    spoofing_risk       VARCHAR(16),
    headers_score       VARCHAR(16),         -- "good" | "partial" | "poor"
    takeover_risk       BOOLEAN,
    blacklisted         BOOLEAN,
    safe_browsing_hit   BOOLEAN,
    urlhaus_hit         BOOLEAN,
    phishtank_hit       BOOLEAN,
    suspicious_content  BOOLEAN,

    -- Fingerprint e cache
    state_fingerprint   VARCHAR(64),
    last_check_at       TIMESTAMPTZ,
    last_event_ids      JSONB,               -- [event_id, ...]

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_health_brand ON brand_domain_health (brand_id);
```

#### `match_state_snapshot` — Estado derivado dos matches

Projeção materializada recalculada a cada novo evento.

```sql
CREATE TABLE match_state_snapshot (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    match_id                UUID NOT NULL UNIQUE REFERENCES similarity_match(id) ON DELETE CASCADE,
    brand_id                UUID NOT NULL REFERENCES monitored_brand(id) ON DELETE CASCADE,

    -- Score derivado
    derived_score           FLOAT NOT NULL,
    derived_bucket          VARCHAR(32) NOT NULL,
    derived_risk            VARCHAR(16) NOT NULL,
    derived_disposition     VARCHAR(32),

    -- Sinais agregados
    active_signals          JSONB NOT NULL,      -- [{code, severity, source_tool, source_event_id}]
    signal_codes            TEXT[],               -- array flat para queries

    -- LLM Assessment
    llm_assessment          JSONB,
    llm_event_id            UUID,
    llm_source_fingerprint  VARCHAR(64),

    -- Fingerprint
    state_fingerprint       VARCHAR(64) NOT NULL,
    events_hash             VARCHAR(64),
    last_derived_at         TIMESTAMPTZ NOT NULL,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_snapshot_brand_bucket ON match_state_snapshot (brand_id, derived_bucket, derived_score DESC);
CREATE INDEX ix_snapshot_brand_risk ON match_state_snapshot (brand_id, derived_risk, derived_score DESC);
CREATE INDEX ix_snapshot_needs_llm ON match_state_snapshot (brand_id)
    WHERE llm_source_fingerprint IS DISTINCT FROM state_fingerprint;
```

### 3.3 Relação entre Tabelas

```
monitored_brand
  ├── monitored_brand_domain
  │     └── brand_domain_health (1:1, materialização)
  │           └── monitoring_event (1:N, health check events)
  │
  ├── similarity_match
  │     └── match_state_snapshot (1:1, materialização)
  │           └── monitoring_event (1:N, enrichment events)
  │
  └── monitoring_cycle (1:N, um por dia)
        └── monitoring_event (1:N, todos eventos do ciclo)
```

---

## 4. Pipeline de Workers

### 4.1 Visão Geral

```
06:00  health_worker      → Health check dos domínios oficiais (10 ferramentas)
09:00  scan_worker         → Similarity scan — busca novos matches
12:00  enrichment_worker   → Enriquecimento top 50 + auto-dismiss
*/15   assessment_worker   → LLM assessment sob demanda (fingerprint change)
```

Todos registram progresso no `monitoring_cycle` da brand para o dia corrente.

### 4.2 Health Worker (06:00)

Para cada brand ativa:
1. Buscar ou criar `monitoring_cycle(brand, hoje)`
2. Atualizar `cycle.health_status = "running"`
3. Para cada `brand_domain` ativa:
   - Rodar 10 ferramentas em paralelo (respeitando rate limits):
     - `dns_lookup`, `ssl_check`, `http_headers`, `email_security`
     - `subdomain_takeover`, `blacklist_check`, `safe_browsing`
     - `urlhaus`, `phishtank`, `suspicious_page`
   - Criar `monitoring_event(event_source="health_check", brand_domain_id=X)` por ferramenta
   - Extrair sinais de cada resultado
   - Recalcular `brand_domain_health`:
     - Derivar `overall_status` dos sinais
     - Calcular `state_fingerprint`
     - Se fingerprint mudou → logar `state_change` event
4. Atualizar `cycle.health_status = "completed"`

**Tolerância a falha:** Ferramenta individual que falha gera evento com `result_data: {error: ...}`. Campo correspondente em `brand_domain_health` fica `NULL`. Cycle marca `completed` (falha parcial ≠ falha total).

### 4.3 Scan Worker (09:00)

Refatoração do `similarity_worker.run_scan_cycle()` existente.

**Mudanças vs. atual:**
1. Registra no `monitoring_cycle` (`scan_status`, timestamps)
2. Cada novo match gera `monitoring_event(event_type="state_change", event_source="scan")` com scores iniciais
3. Calcula `enrichment_budget_rank` ao final do scan:
   - Rank 1: `attention_bucket = "immediate_attention"` (sempre)
   - Rank 2: Matches novos deste ciclo (`first_detected_at = hoje`)
   - Rank 3: `defensive_gap` com `actionability_score DESC`
   - Rank 4: `watchlist` com `score_final > 0.55`
   - Rank 5: Matches existentes com último enrichment > 7 dias
4. **Não enriquece inline** — apenas descobre e rankeia. Budget: top 50 por brand.

### 4.4 Enrichment Worker (12:00)

Para cada brand ativa:
1. Buscar `monitoring_cycle(brand, hoje)`
2. Atualizar `cycle.enrichment_status = "running"`
3. Buscar matches onde `enrichment_budget_rank IS NOT NULL`, ordenados por rank
4. Para cada match (até budget de 50):
   - Verificar cache (TTL por ferramenta)
   - Rodar ferramentas em sequência:
     - **Onda 1:** `dns_lookup`, `whois`, `ssl_check`, `http_headers`, `screenshot`, `suspicious_page`
     - **Onda 2:** `email_security`, `ip_geolocation`, `blacklist_check`, `safe_browsing`, `urlhaus`, `phishtank`
     - **Condicional:** `website_clone` (só se bucket = `immediate_attention` + marca tem domínio primário)
   - Criar `monitoring_event(event_source="enrichment", match_id=X)` por ferramenta
   - Recalcular `match_state_snapshot`:
     - Agregar sinais de todos os eventos ativos
     - Recalcular `derived_score`, `derived_bucket`, `derived_risk`
     - Calcular `state_fingerprint`
     - Se fingerprint mudou vs. último LLM → marcar para reassessment
5. **Auto-dismiss pass** (ver seção 6)
6. Atualizar contadores do cycle (`enrichment_budget`, `dismissed_count`, `escalated_count`)
7. Atualizar `cycle.enrichment_status = "completed"`

### 4.5 Assessment Worker (a cada 15 minutos)

Loop contínuo:
1. Buscar `match_state_snapshot` onde:
   - `llm_source_fingerprint != state_fingerprint` (estado mudou)
   - OU `llm_assessment IS NULL` E `derived_bucket IN ("immediate_attention", "defensive_gap")`
   - OU `last_derived_at > llm_event.created_at + 7 dias` (TTL expirado)
2. Para cada match (batch de 10 por ciclo):
   - Montar prompt com dados do snapshot + sinais + tool results dos últimos eventos
   - Chamar LLM via OpenRouter
   - Criar `monitoring_event(event_type="llm_assessment", match_id=X, result_data={parecer})`
   - Atualizar `match_state_snapshot.llm_assessment` e `llm_source_fingerprint`

**Gate:** Matches em `watchlist` com `derived_risk = low` não recebem assessment.

### 4.6 Resiliência

- **Idempotência:** Workers verificam se já rodaram para o cycle do dia. Re-run não duplica eventos (check por `cycle_id + tool_name + target`).
- **Retry:** Falha em ferramenta individual não bloqueia o worker. Evento com erro, worker continua.
- **Heartbeat:** Workers atualizam `monitoring_cycle.updated_at` periodicamente. Stuck se >10min sem update.
- **Dead letter:** Matches com 3 enrichments consecutivos falhados são marcados para revisão manual.
- **Alertas:** ≥2 dias consecutivos com cycle incompleto para uma brand → alerta ao admin.

---

## 5. Score Derivado

### 5.1 Fórmula

```
derived_score = clamp(0, 1,
    base_lexical_score                                      // score_final existente
  + sum(signal.score_adjustment for each active signal)     // ajustes do catálogo de ferramentas
  + temporal_bonus                                          // bônus/penalidade temporal
)
```

**Temporal bonus:**
- Domínio registrado ≤7 dias: `+0.05` (além do `+0.18` do WHOIS)
- Domínio registrado >1 ano sem sinais negativos: `-0.10`
- Domínio registrado >3 anos: `-0.15`

### 5.2 Bucket Reclassificação

| Condição | Bucket |
|---|---|
| `derived_score ≥ 0.80` OU clone detectado OU (credential + brand impersonation) | `immediate_attention` |
| `derived_score ≥ 0.48` OU exact label match em TLD estratégico | `defensive_gap` |
| Restante | `watchlist` |

### 5.3 Tabela de Pesos por Ferramenta

| Ferramenta | Sinal | Peso |
|---|---|---|
| WHOIS | Registro ≤30 dias | `+0.18` |
| WHOIS | Registro 31-90 dias | `+0.10` |
| DNS | Não resolve | `-0.08` |
| DNS | Mail-only (MX sem A/AAAA) | `+0.12` |
| HTTP | Status 200 | `+0.05` |
| HTTP | Status 401/403/429/503 | `+0.06` |
| HTTP | HTTPS ativo | `+0.03` |
| Suspicious Page | Parked/for sale | `-0.22` |
| Suspicious Page | Formulário de login | `+0.26` |
| Suspicious Page | risk_level critical | `+0.22` |
| Suspicious Page | risk_level high | `+0.14` |
| Suspicious Page | risk_level medium | `+0.06` |
| Suspicious Page | Brand impersonation | `+0.18` |
| Suspicious Page | Social engineering | `+0.10` |
| Suspicious Page | PhaaS/phishing kit | `+0.15` |
| Suspicious Page | Challenge/bloqueio | `+0.05` |
| Suspicious Page | Infraestrutura mascarada | `+0.08` |
| Email Security | Spoofing critical | `+0.16` |
| Email Security | Spoofing high | `+0.09` |
| IP Geolocation | País alto risco (RU/BY/KP/IR) | `+0.12` |
| IP Geolocation | DDoS-Guard | `+0.08` |
| SSL | Certificado revogado (OCSP) | `+0.25` |
| Safe Browsing | Listado | `+0.30` |
| URLhaus | Listado | `+0.20` |
| PhishTank | Verificado e ativo | `+0.28` |
| PhishTank | Na base, não verificado | `+0.12` |
| Website Clone | Clone detectado | → `immediate_attention` direto |

---

## 6. Auto-Dismiss e Auto-Escalation

### 6.1 Regras de Auto-Dismiss

Um match é auto-dismissed se **todas** as condições de pelo menos uma regra forem verdadeiras:

**Regra 1 — Domínio morto:**
- DNS não resolve (sem A, AAAA, CNAME)
- Sem registros MX
- WHOIS `creation_date` > 1 ano
- Nenhum sinal `critical` ou `high`

**Regra 2 — Score baixo pós-enrichment:**
- `derived_score < 0.35`
- Nenhum sinal severity `critical` ou `high`
- Não é `exact_label_match`

**Regra 3 — Parked/For Sale:**
- `suspicious_page` retornou `parked_or_for_sale_page`
- Sem MX ativo
- Safe Browsing, PhishTank, URLhaus limpos

Cada auto-dismiss gera `monitoring_event(event_type="auto_disposition")` com regra que disparou.

### 6.2 Auto-Escalation

Se um match previamente dismissed ganha novos sinais:
1. Remove `auto_disposition`
2. Recalcula `derived_score` e `derived_bucket`
3. Gera evento `state_change` com razão `"escalated_from_dismissed"`

---

## 7. Fingerprint e LLM Assessment

### 7.1 Cálculo do Fingerprint

SHA-256 de propriedades-chave normalizadas:

```python
def compute_state_fingerprint(snapshot: MatchStateSnapshot, latest_events: list) -> str:
    payload = {
        "derived_risk": snapshot.derived_risk,
        "derived_bucket": snapshot.derived_bucket,
        "signal_codes": sorted(snapshot.signal_codes),
        "dns_resolves": "live_http_surface" in snapshot.signal_codes
                     or "restricted_live_surface" in snapshot.signal_codes,
        "http_active": any(c in snapshot.signal_codes for c in [
            "live_http_surface", "restricted_live_surface"
        ]),
        "ssl_revoked": "certificate_revoked" in snapshot.signal_codes,
        "threat_intel_hits": sorted([
            c for c in snapshot.signal_codes
            if c in ("safe_browsing_hit", "phishtank_verified_phish",
                     "phishtank_in_database", "urlhaus_malware_listed")
        ]),
        "spoofing_risk": next(
            (c for c in snapshot.signal_codes if "spoofing" in c), None
        ),
        "suspicious_page_risk": next(
            (e.result_data.get("risk_level")
             for e in latest_events if e.tool_name == "suspicious_page"),
            None
        ),
    }
    return sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
```

### 7.2 Gatilhos de Reavaliação LLM

1. `state_fingerprint != llm_source_fingerprint` → reavaliar
2. `llm_assessment IS NULL` E bucket ∈ {immediate_attention, defensive_gap} → primeira avaliação
3. Último assessment > 7 dias → reavaliar por TTL

### 7.3 O que NÃO gera reavaliação

- Mudança apenas no `derived_score` sem mudança de sinais
- Re-execução de ferramenta com mesmo resultado (cache hit)
- Mudança de `enrichment_budget_rank`

---

## 8. API

### 8.1 Endpoints Existentes — Mantidos

| Método | Endpoint | Mudança |
|---|---|---|
| `POST` | `/v1/brands` | Sem mudança |
| `GET` | `/v1/brands` | Sem mudança |
| `PATCH` | `/v1/brands/{id}` | Sem mudança |
| `DELETE` | `/v1/brands/{id}` | Sem mudança |
| `POST` | `/v1/brands/{id}/scan` | Sem mudança |

### 8.2 Endpoints Modificados

#### `GET /v1/brands/{id}` — Expandido com `monitoring_summary`

Resposta adiciona:

```json
{
  "monitoring_summary": {
    "latest_cycle": {
      "cycle_date": "2026-04-11",
      "health_status": "completed",
      "scan_status": "completed",
      "enrichment_status": "completed",
      "new_matches_count": 7,
      "threats_detected": 1,
      "dismissed_count": 12
    },
    "threat_counts": {
      "immediate_attention": 3,
      "defensive_gap": 12,
      "watchlist": 45
    },
    "overall_health": "healthy"
  }
}
```

#### `GET /v1/brands/{id}/matches` — Consome `match_state_snapshot`

Filtros adicionais:
- `exclude_auto_dismissed=true` (default)
- `include_llm=true` — inclui LLM assessment inline

Resposta de cada match inclui campos derivados:
- `derived_score`, `derived_bucket`, `derived_risk`
- `active_signals[]` com code, severity, source_tool
- `llm_assessment` (quando `include_llm=true`)
- `state_fingerprint`, `auto_disposition`

### 8.3 Novos Endpoints

#### `GET /v1/brands/{id}/health` — Saúde dos domínios oficiais

Retorna array de domínios com resultado de cada ferramenta:

```json
{
  "domains": [
    {
      "domain_name": "nubank.com.br",
      "is_primary": true,
      "overall_status": "healthy",
      "checks": {
        "dns": {"ok": true, "details": {...}},
        "ssl": {"ok": true, "details": {"days_remaining": 245, "ocsp": "good"}},
        "email_security": {"ok": true, "details": {"spf": true, "dmarc": true, "dkim": true}},
        "headers": {"ok": true, "details": {"hsts": true, "csp": true}},
        "takeover": {"ok": true, "details": {"vulnerable_subdomains": 0}},
        "blacklist": {"ok": true, "details": {"listed_count": 0}},
        "safe_browsing": {"ok": true, "details": {"threats": []}},
        "urlhaus": {"ok": true, "details": {"listed": false}},
        "phishtank": {"ok": true, "details": {"listed": false}},
        "suspicious_page": {"ok": true, "details": {"risk_level": "safe"}}
      },
      "last_check_at": "2026-04-11T06:12:00Z"
    }
  ]
}
```

#### `GET /v1/brands/{id}/cycles` — Histórico de ciclos

Paginado, ordenado por data DESC. Default: últimos 30 dias.

#### `GET /v1/matches/{id}/events` — Timeline de eventos de um match

Retorna todos os `monitoring_event` do match, ordenados por `created_at DESC`. Usado na página de detalhes completos do match.

### 8.4 Frontend → API Mapping

| View | Requests |
|---|---|
| Lista de marcas (cards) | `GET /v1/brands` (inclui `monitoring_summary`) |
| Brand detail page | `GET /v1/brands/{id}` + `GET /v1/brands/{id}/health` + `GET /v1/brands/{id}/matches?include_llm=true` |
| Match drawer | Dados já vêm no match list |
| Match detail completo | `GET /v1/matches/{id}/events` |
| Histórico | `GET /v1/brands/{id}/cycles` |

### 8.5 Página Removida

`/admin/matches` deixa de existir. Matches vivem dentro de `/admin/brands/{id}`.

---

## 9. Frontend

### 9.1 Lista de Marcas — `/admin/brands`

**Layout:** Grid de cards com status visual.

Cada card mostra:
- Nome da marca + domínio primário
- Badge de saúde geral (verde `Saudável` / amarelo `Alerta` / vermelho `Crítico`)
- Contadores por bucket: urgentes (vermelho), defesa (amarelo), watchlist (cinza)
- Status do último ciclo com timestamps e indicadores (✓/⚠)

### 9.2 Detalhe da Marca — `/admin/brands/{id}`

**Layout:** Seções empilhadas em scroll vertical.

**Header fixo:**
- Nome da marca, domínio primário, último monitoramento
- Badges: saúde geral + contagem de ameaças urgentes

**Seção: Ciclo de Hoje**
- Barra compacta mostrando status de cada etapa (Health, Scan, Enrichment) com timestamps
- Contadores: novos matches, ameaças escaladas, dismissed

**Seção: Saúde dos Seus Domínios** (collapsível)
- Card por domínio oficial com indicadores inline por ferramenta (DNS ✓, SSL ✓, Email ✓, etc.)
- Alerta visual se qualquer domínio está em blacklist, Safe Browsing, etc.

**Seção: Ameaças Detectadas** (principal)
- Filtros por bucket (Urgentes / Defesa / Watchlist) como pills
- Lista de matches com: domínio, idade, categoria LLM, score visual
- Click abre drawer lateral

**Seção: Configuração** (collapsível)
- TLDs monitorados, aliases, keywords, noise mode
- Edição inline

**Seção: Histórico** (collapsível)
- Tabela de ciclos recentes com status de cada etapa

### 9.3 Drawer de Match

Abre ao clicar em um match na lista de ameaças.

**Cabeçalho:** Domínio, score gauge, badge de urgência, idade do registro

**Parecer LLM:** Bloco com borda colorida, resumo em linguagem acessível, recomendação de ação em destaque

**5 Cards de Evidência:**
1. **Identidade (WHOIS)** — data registro, registrador, país, registrante
2. **Infraestrutura (DNS/HTTP/SSL/IP)** — resolução, status HTTP, SSL, geolocalização
3. **Conteúdo (Suspicious Page/Screenshot/Clone)** — sinais de phishing, screenshot link
4. **Email (SPF/DMARC/DKIM)** — proteções, spoofing risk
5. **Reputação (Threat Intel)** — Safe Browsing, PhishTank, URLhaus, Blacklists

Cada card com indicador de severidade no header (verde/amarelo/vermelho).

**Rodapé de Ações:** Confirmar Ameaça, Dismiss, Adicionar Nota, Ver Detalhes Completos →

**Link "Detalhes Completos"** abre página full com timeline de eventos do match.

---

## 10. Integração das 16 Ferramentas

| Ferramenta | Health Check | Enrichment | Score | Fingerprint |
|---|---|---|---|---|
| `dns_lookup` | ✓ | ✓ | ✓ | ✓ |
| `whois` | - | ✓ | ✓ | ✓ |
| `ssl_check` | ✓ | ✓ | ✓ | ✓ |
| `http_headers` | ✓ | ✓ | ✓ | ✓ |
| `screenshot` | - | ✓ | - | - |
| `suspicious_page` | ✓ | ✓ | ✓ | ✓ |
| `email_security` | ✓ | ✓ | ✓ | ✓ |
| `ip_geolocation` | - | ✓ | ✓ | ✓ |
| `blacklist_check` | ✓ | ✓ | futuro | ✓ |
| `safe_browsing` | ✓ | ✓ | ✓ | ✓ |
| `urlhaus` | ✓ | ✓ | ✓ | ✓ |
| `phishtank` | ✓ | ✓ | ✓ | ✓ |
| `domain_similarity` | - | - (gerador) | - | - |
| `website_clone` | - | condicional | ✓ (escalação) | ✓ |
| `subdomain_takeover` | ✓ | - | - | - |
| `reverse_ip` | - | futuro | futuro | - |
| LLM Assessment | - | pós-enrichment | - (separado) | - (consumidor) |

---

## 11. Migração e Faseamento

### Estratégia: Aditivo primeiro, destrutivo nunca.

Nenhuma tabela ou coluna existente é removida. Novas tabelas são criadas ao lado. Workers novos rodam em paralelo até validação.

### Fases

**Fase 1 — Fundação (semana 1-2)**
- Migrations Alembic: 4 novas tabelas + campos em `similarity_match`
- `monitoring_event` repository + service
- Aggregator (recalcula snapshots a partir de eventos)
- `monitoring_cycle` lifecycle service

**Fase 2 — Workers (semana 2-3)**
- `health_worker` (novo)
- `scan_worker` (refatoração do existente — registra no cycle, emite eventos, não enriquece inline)
- `enrichment_worker` (extraído do scan — budget, auto-dismiss)
- `assessment_worker` (extraído do enrichment — fingerprint check)

**Fase 3 — API (semana 3-4)**
- Expandir `GET /v1/brands/{id}` com `monitoring_summary`
- Novos endpoints: `/health`, `/cycles`, `/matches/{id}/events`
- Modificar `/matches` para ler de `match_state_snapshot`

**Fase 4 — Frontend (semana 4-5)**
- Lista de marcas (cards)
- Brand detail page (seções empilhadas)
- Match drawer (5 cards de evidência)
- Remover `/admin/matches`

**Fase 5 — Refinamento (semana 5-6)**
- Backfill: enrichment para matches existentes, popular snapshots retroativamente
- Tuning: thresholds de auto-dismiss com dados reais
- Observabilidade: dashboard de workers + alertas

### Compatibilidade durante migração

| Componente | Fases 1-2 | Fases 3-4 | Fase 5+ |
|---|---|---|---|
| Worker antigo | Continua | Desativado após validação | Removido |
| `tool_execution` | Escrita ativa | Paralelo com `monitoring_event` | Depreciada |
| `enrichment_summary` | Populado | Paralelo com snapshot | Depreciado |
| `/admin/matches` | Funciona | Redirect para brand detail | Removido |

### Rollback

- Workers novos podem ser parados sem afetar antigos
- Novas tabelas são aditivas (ignoráveis)
- Feature flag no frontend para reverter views
