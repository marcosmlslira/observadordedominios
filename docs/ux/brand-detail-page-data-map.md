# Brand Detail Page — Mapa de Dados
**Rota:** `/admin/brands/[brand_id]`  
**Objetivo deste documento:** Catalogar todas as informações disponíveis no sistema para a página de detalhe de uma marca — o que já é exibido hoje, o que existe no banco mas não é exibido, e como os dados se parecem em formato raw. Base para o trabalho de layout e storytelling.

---

## 1. Visão Geral: APIs chamadas na página hoje

| Chamada | Endpoint | Frequência |
|---------|----------|------------|
| Perfil da marca | `GET /v1/brands/{brand_id}` | Ao carregar |
| Health dos domínios oficiais | `GET /v1/brands/{brand_id}/health` | Ao carregar |
| Histórico de ciclos | `GET /v1/brands/{brand_id}/cycles?limit=30` | Ao carregar |
| Lista de ameaças (snapshots) | `GET /v1/brands/{brand_id}/matches?include_llm=true&bucket=...` | Ao carregar + filtros |
| Timeline de eventos de um match | `GET /v1/matches/{match_id}/events` | Ao abrir o drawer |

---

## 2. Bloco: Perfil da Marca (`GET /v1/brands/{brand_id}`)

### O que é exibido hoje
- Nome da marca (`brand_name`)
- Badge de saúde geral (`overall_health`)
- Badge `inactive` se desativada
- Contadores de ameaças (immediate, defensive, watchlist)
- Último ciclo: data, status health/scan/enrichment, threats, new matches
- Domínios oficiais (collapsible), Keywords, Aliases, TLD scope, Notes

### Dados disponíveis mas NÃO exibidos hoje

| Campo | Tipo | Onde fica |
|-------|------|-----------|
| `primary_brand_name` | string | Marca primária normalizada |
| `brand_label` | string | Label de busca de similaridade |
| `noise_mode` | `conservative\|standard\|broad` | Sensibilidade de detecção |
| `tld_scope` (quantidade) | lista | Scope de monitoramento |
| `seeds` | lista | Seeds derivadas para busca |
| `alert_webhook_url` | string | Webhook de alertas configurado |
| `created_at` | datetime | Data de início do monitoramento |
| `aliases[].alias_type` | string | Tipo de alias (brand_alias, brand_phrase, support_keyword) |
| `aliases[].weight_override` | float | Peso customizado do alias |
| `seeds[].seed_type` | string | Tipo de seed (exact, fuzzy, brand_hit…) |
| `seeds[].base_weight` | float | Peso base na busca de similaridade |
| `domains[].registrable_label` | string | Label sem TLD |
| `domains[].hostname_stem` | string | Stem do hostname |

### Exemplo de payload completo

```json
{
  "id": "a1b2c3d4-0000-0000-0000-000000000001",
  "organization_id": "00000000-0000-0000-0000-000000000001",
  "brand_name": "Nubank",
  "primary_brand_name": "nubank",
  "brand_label": "nubank",
  "keywords": ["nu", "roxinho", "banco nubank", "financeira nu"],
  "tld_scope": ["com", "com.br", "net", "io", "app", "bank"],
  "noise_mode": "standard",
  "notes": "Monitorar typos com nu e bank. Alta prioridade.",
  "is_active": true,
  "alert_webhook_url": null,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-09-10T08:00:00Z",

  "official_domains": [
    {
      "id": "d1000000-0000-0000-0000-000000000001",
      "domain_name": "nubank.com.br",
      "registrable_domain": "nubank.com.br",
      "registrable_label": "nubank",
      "public_suffix": "com.br",
      "hostname_stem": "nubank",
      "is_primary": true,
      "is_active": true
    },
    {
      "id": "d1000000-0000-0000-0000-000000000002",
      "domain_name": "nu.com.br",
      "registrable_domain": "nu.com.br",
      "registrable_label": "nu",
      "public_suffix": "com.br",
      "hostname_stem": "nu",
      "is_primary": false,
      "is_active": true
    }
  ],

  "aliases": [
    {
      "id": "aa000000-0000-0000-0000-000000000001",
      "alias_value": "Nubank",
      "alias_normalized": "nubank",
      "alias_type": "brand_alias",
      "weight_override": null,
      "is_active": true
    },
    {
      "id": "aa000000-0000-0000-0000-000000000002",
      "alias_value": "Nu Pagamentos",
      "alias_normalized": "nu pagamentos",
      "alias_type": "brand_phrase",
      "weight_override": 0.8,
      "is_active": true
    },
    {
      "id": "aa000000-0000-0000-0000-000000000003",
      "alias_value": "Nu Financeira",
      "alias_normalized": "nu financeira",
      "alias_type": "brand_phrase",
      "weight_override": null,
      "is_active": true
    }
  ],

  "seeds": [
    {
      "id": "ss000000-0000-0000-0000-000000000001",
      "source_ref_type": "domain",
      "source_ref_id": "d1000000-0000-0000-0000-000000000001",
      "seed_value": "nubank",
      "seed_type": "exact_label_match",
      "channel_scope": "all",
      "base_weight": 1.0,
      "is_manual": false,
      "is_active": true
    },
    {
      "id": "ss000000-0000-0000-0000-000000000002",
      "source_ref_type": "alias",
      "source_ref_id": "aa000000-0000-0000-0000-000000000001",
      "seed_value": "nubank",
      "seed_type": "brand_hit",
      "channel_scope": "all",
      "base_weight": 0.9,
      "is_manual": false,
      "is_active": true
    },
    {
      "id": "ss000000-0000-0000-0000-000000000003",
      "source_ref_type": "keyword",
      "source_ref_id": null,
      "seed_value": "nu",
      "seed_type": "keyword",
      "channel_scope": "fuzzy",
      "base_weight": 0.5,
      "is_manual": false,
      "is_active": true
    }
  ],

  "monitoring_summary": {
    "overall_health": "warning",
    "latest_cycle": {
      "cycle_date": "2025-04-12",
      "health_status": "completed",
      "scan_status": "completed",
      "enrichment_status": "completed",
      "new_matches_count": 3,
      "threats_detected": 14,
      "dismissed_count": 2
    },
    "threat_counts": {
      "immediate_attention": 4,
      "defensive_gap": 7,
      "watchlist": 23
    }
  }
}
```

---

## 3. Bloco: Saúde dos Domínios Oficiais (`GET /v1/brands/{brand_id}/health`)

### O que é exibido hoje
Tabela com: domain_name, overall_status, DNS ✓/✗, SSL ✓/✗, Email ✓/✗, Headers ✓/✗, Blacklist ✓/✗, last_check_at

### Dados disponíveis mas NÃO exibidos hoje

| Campo | Dado escondido |
|-------|----------------|
| `ssl.details.days_remaining` | Dias restantes do certificado (ex: 23 dias) |
| `email_security.details.spoofing_risk` | Nível de risco de spoofing: `none\|low\|medium\|high\|critical` |
| `headers.details.score` | Score: `good\|partial\|poor` |
| `takeover` | Risco de subdomain takeover |
| `safe_browsing` | Status Google Safe Browsing |
| `urlhaus` | Status URLhaus (malware/phishing) |
| `phishtank` | Status PhishTank |
| `suspicious_page` | Conteúdo suspeito detectado na página |

### Exemplo de payload completo

```json
{
  "domains": [
    {
      "domain_id": "d1000000-0000-0000-0000-000000000001",
      "domain_name": "nubank.com.br",
      "is_primary": true,
      "overall_status": "warning",
      "dns": { "ok": true },
      "ssl": {
        "ok": true,
        "details": { "days_remaining": 23 }
      },
      "email_security": {
        "ok": false,
        "details": { "spoofing_risk": "medium" }
      },
      "headers": {
        "ok": false,
        "details": { "score": "partial" }
      },
      "takeover": { "ok": true },
      "blacklist": { "ok": true },
      "safe_browsing": { "ok": true },
      "urlhaus": { "ok": true },
      "phishtank": { "ok": true },
      "suspicious_page": { "ok": true },
      "last_check_at": "2025-04-12T06:45:00Z"
    },
    {
      "domain_id": "d1000000-0000-0000-0000-000000000002",
      "domain_name": "nu.com.br",
      "is_primary": false,
      "overall_status": "critical",
      "dns": { "ok": true },
      "ssl": {
        "ok": false,
        "details": { "days_remaining": 2 }
      },
      "email_security": {
        "ok": false,
        "details": { "spoofing_risk": "high" }
      },
      "headers": {
        "ok": false,
        "details": { "score": "poor" }
      },
      "takeover": { "ok": true },
      "blacklist": { "ok": true },
      "safe_browsing": { "ok": true },
      "urlhaus": { "ok": true },
      "phishtank": { "ok": true },
      "suspicious_page": { "ok": true },
      "last_check_at": "2025-04-12T06:50:00Z"
    }
  ]
}
```

---

## 4. Bloco: Histórico de Ciclos (`GET /v1/brands/{brand_id}/cycles`)

### O que é exibido hoje
Tabela: date, health_status, scan_status, enrichment_status, threats_detected, new_matches_count

### Dados disponíveis mas NÃO exibidos hoje

| Campo | Significado |
|-------|-------------|
| `cycle_type` | `scheduled` ou `manual` |
| `health_started_at` / `health_finished_at` | Tempo de execução do health check |
| `scan_started_at` / `scan_finished_at` | Tempo de execução do scan |
| `enrichment_started_at` / `enrichment_finished_at` | Tempo de execução do enrichment |
| `enrichment_budget` | Quantas ameaças foram orçadas para enriquecimento |
| `enrichment_total` | Quantas foram efetivamente enriquecidas |
| `escalated_count` | Quantas foram escaladas |
| `dismissed_count` | Quantas foram descartadas automaticamente |

### Exemplo de payload completo

```json
{
  "items": [
    {
      "id": "cc000000-0000-0000-0000-000000000001",
      "brand_id": "a1b2c3d4-0000-0000-0000-000000000001",
      "organization_id": "00000000-0000-0000-0000-000000000001",
      "cycle_date": "2025-04-12",
      "cycle_type": "scheduled",
      "health_status": "completed",
      "health_started_at": "2025-04-12T06:00:01Z",
      "health_finished_at": "2025-04-12T06:04:37Z",
      "scan_status": "completed",
      "scan_started_at": "2025-04-12T09:00:02Z",
      "scan_finished_at": "2025-04-12T09:22:15Z",
      "scan_job_id": "jj000000-0000-0000-0000-000000000001",
      "enrichment_status": "completed",
      "enrichment_started_at": "2025-04-12T12:00:03Z",
      "enrichment_finished_at": "2025-04-12T12:38:44Z",
      "enrichment_budget": 500,
      "enrichment_total": 487,
      "new_matches_count": 3,
      "escalated_count": 2,
      "dismissed_count": 4,
      "threats_detected": 14,
      "created_at": "2025-04-12T06:00:00Z",
      "updated_at": "2025-04-12T12:39:00Z"
    },
    {
      "id": "cc000000-0000-0000-0000-000000000002",
      "cycle_date": "2025-04-11",
      "cycle_type": "scheduled",
      "health_status": "completed",
      "scan_status": "completed",
      "enrichment_status": "completed",
      "enrichment_budget": 500,
      "enrichment_total": 500,
      "new_matches_count": 1,
      "escalated_count": 0,
      "dismissed_count": 1,
      "threats_detected": 11,
      "health_started_at": "2025-04-11T06:00:01Z",
      "health_finished_at": "2025-04-11T06:04:12Z",
      "scan_started_at": "2025-04-11T09:00:01Z",
      "scan_finished_at": "2025-04-11T09:18:00Z",
      "enrichment_started_at": "2025-04-11T12:00:02Z",
      "enrichment_finished_at": "2025-04-11T12:30:22Z"
    }
  ],
  "total": 87
}
```

---

## 5. Bloco: Ameaças / Match Snapshots (`GET /v1/brands/{brand_id}/matches?include_llm=true`)

### O que é exibido hoje
Tabela: domain_name, derived_bucket badge, derived_score %, derived_risk badge, signal_codes (3 primeiros), first_detected_at

### Dados disponíveis mas NÃO exibidos na tabela hoje

| Campo | Significado |
|-------|-------------|
| `tld` | TLD do domínio suspeito |
| `label` | Label sem TLD (ex: `nubankk`) |
| `score_final` | Score léxico bruto (sem enriquecimento) |
| `domain_first_seen` | Quando o domínio foi descoberto no CT log / zone file |
| `matched_rule` | Regra que gerou o match (ex: `exact_label_match`, `brand_containment`) |
| `matched_seed_value` | Seed que capturou o match |
| `matched_seed_type` | Tipo da seed |
| `matched_channel` | Canal de detecção |
| `source_stream` | Fonte: `certstream`, `czds`, `crtsh`, `openintel` |
| `enrichment_status` | Se foi enriquecido: `pending\|enriched\|skipped` |
| `auto_disposition_reason` | Motivo do auto-descarte |
| `status` | Status humano: `new\|reviewing\|dismissed\|confirmed_threat` |
| `ownership_classification` | `official\|associated\|third_party` |
| `delivery_risk` | Risco de entrega de e-mail malicioso |
| `state_fingerprint` | Hash do estado atual (para detectar mudanças) |
| `last_derived_at` | Quando o snapshot foi recalculado pela última vez |
| `active_signals` (completo) | Lista completa de sinais com severidade, descrição e score_adjustment |
| `llm_assessment` (completo) | Parecer detalhado do LLM |

### Exemplo de payload completo — match de alto risco

```json
{
  "id": "mm000000-0000-0000-0000-000000000001",
  "brand_id": "a1b2c3d4-0000-0000-0000-000000000001",
  "domain_name": "nubankk.com",
  "tld": "com",
  "label": "nubankk",
  "score_final": 0.87,
  "attention_bucket": "immediate_attention",
  "matched_rule": "exact_label_match",
  "matched_seed_value": "nubank",
  "matched_seed_type": "exact_label_match",
  "matched_channel": "czds",
  "source_stream": "czds",
  "auto_disposition": null,
  "auto_disposition_reason": null,
  "first_detected_at": "2025-04-10T09:12:00Z",
  "domain_first_seen": "2025-04-09T22:47:00Z",
  "enrichment_status": "enriched",
  "ownership_classification": "third_party",
  "self_owned": false,
  "delivery_risk": "high",
  "status": "new",
  "reviewed_by": null,
  "reviewed_at": null,
  "notes": null,

  "derived_score": 0.92,
  "derived_bucket": "immediate_attention",
  "derived_risk": "critical",
  "derived_disposition": null,
  "state_fingerprint": "a3f9c2b1d4e85f70",
  "last_derived_at": "2025-04-12T12:45:00Z",

  "signal_codes": [
    "phishing_page_detected",
    "blacklisted_spamhaus",
    "mx_active",
    "ssl_issued_recently",
    "exact_label_match"
  ],

  "active_signals": [
    {
      "code": "phishing_page_detected",
      "severity": "critical",
      "score_adjustment": 0.35,
      "description": "Página com formulário de login clonado detectada.",
      "source_tool": "suspicious_page"
    },
    {
      "code": "blacklisted_spamhaus",
      "severity": "high",
      "score_adjustment": 0.20,
      "description": "Domínio encontrado na lista negra Spamhaus DBL.",
      "source_tool": "blacklist_check"
    },
    {
      "code": "mx_active",
      "severity": "medium",
      "score_adjustment": 0.15,
      "description": "Registros MX ativos indicam capacidade de envio de e-mail.",
      "source_tool": "dns_lookup"
    },
    {
      "code": "ssl_issued_recently",
      "severity": "medium",
      "score_adjustment": 0.12,
      "description": "Certificado SSL emitido há menos de 7 dias.",
      "source_tool": "ssl_check"
    },
    {
      "code": "exact_label_match",
      "severity": "high",
      "score_adjustment": 0.16,
      "description": "Label exato da marca encontrado no domínio.",
      "source_tool": "similarity_scan"
    }
  ],

  "llm_assessment": {
    "risco_score": 91,
    "categoria": "phishing_ativo",
    "parecer_resumido": "Domínio nubankk.com apresenta múltiplos indicadores de campanha de phishing ativa: página clonada com formulário de login, certificado recém-emitido, registro MX ativo e presença em lista negra. Alta probabilidade de uso para roubo de credenciais.",
    "principais_motivos": [
      "Página com formulário de login idêntico ao Nubank detectada",
      "Certificado SSL emitido há 3 dias via Let's Encrypt",
      "MX ativo: domínio pode enviar/receber e-mails",
      "Presente na lista Spamhaus DBL",
      "Registrado 1 dia antes da detecção — padrão de domínio de ataque"
    ],
    "recomendacao_acao": "Acionar equipe jurídica imediatamente para takedown. Registrar abuso no registrar e na lista Spamhaus.",
    "confianca": 0.95
  }
}
```

### Exemplo de payload — match de baixo risco (watchlist)

```json
{
  "id": "mm000000-0000-0000-0000-000000000002",
  "domain_name": "nu-bank.net",
  "tld": "net",
  "label": "nu-bank",
  "score_final": 0.61,
  "matched_rule": "brand_containment",
  "matched_seed_value": "nubank",
  "source_stream": "openintel",
  "first_detected_at": "2025-03-01T14:00:00Z",
  "domain_first_seen": "2024-08-10T09:00:00Z",
  "derived_score": 0.44,
  "derived_bucket": "watchlist",
  "derived_risk": "low",
  "signal_codes": ["brand_containment"],
  "active_signals": [
    {
      "code": "brand_containment",
      "severity": "low",
      "score_adjustment": 0.04,
      "description": "Marca contida no domínio como substring.",
      "source_tool": "similarity_scan"
    }
  ],
  "llm_assessment": null,
  "status": "new",
  "enrichment_status": "pending",
  "auto_disposition": null
}
```

---

## 6. Bloco: Timeline de Eventos de um Match (`GET /v1/matches/{match_id}/events`)

### O que é exibido hoje no Drawer
Lista de eventos: data, event_source badge, event_type, tool_name

### Dados disponíveis mas NÃO exibidos hoje

| Campo | Significado |
|-------|-------------|
| `result_data` | Payload completo da ferramenta (WHOIS, DNS, SSL, etc.) |
| `signals` | Sinais que este evento contribuiu |
| `score_snapshot` | Score no momento do evento |
| `tool_version` | Versão da ferramenta |
| `ttl_expires_at` | Quando este dado expira e precisa ser re-executado |

### Exemplo de eventos em ordem cronológica

```json
{
  "items": [
    {
      "id": "ev000001",
      "event_type": "tool_execution",
      "event_source": "scan",
      "tool_name": "dns_lookup",
      "tool_version": "1.0",
      "created_at": "2025-04-10T09:12:05Z",
      "result_data": {
        "a_records": ["185.220.101.5"],
        "mx_records": ["10 mail.nubankk.com"],
        "ns_records": ["ns1.cloudflare.com", "ns2.cloudflare.com"],
        "txt_records": ["v=spf1 include:sendgrid.net ~all"],
        "resolves": true,
        "dns_age_days": 1
      },
      "signals": [
        {
          "code": "mx_active",
          "severity": "medium",
          "score_adjustment": 0.15,
          "description": "Registros MX ativos indicam capacidade de envio de e-mail."
        }
      ],
      "score_snapshot": {
        "before": 0.87,
        "after": 0.87
      },
      "ttl_expires_at": "2025-04-13T09:12:05Z"
    },
    {
      "id": "ev000002",
      "event_type": "tool_execution",
      "event_source": "enrichment",
      "tool_name": "whois",
      "tool_version": "1.0",
      "created_at": "2025-04-10T12:15:22Z",
      "result_data": {
        "registrar": "Namecheap, Inc.",
        "creation_date": "2025-04-09T22:47:00Z",
        "expiration_date": "2026-04-09T22:47:00Z",
        "registrant_country": "PW",
        "registrant_email": "privacy@whoisguard.com",
        "domain_age_days": 1,
        "privacy_protected": true
      },
      "signals": [
        {
          "code": "fresh_registration",
          "severity": "high",
          "score_adjustment": 0.25,
          "description": "Domínio registrado há menos de 7 dias."
        }
      ],
      "score_snapshot": { "before": 0.87, "after": 0.92 },
      "ttl_expires_at": "2025-04-17T12:15:22Z"
    },
    {
      "id": "ev000003",
      "event_type": "tool_execution",
      "event_source": "enrichment",
      "tool_name": "ssl_check",
      "created_at": "2025-04-10T12:16:01Z",
      "result_data": {
        "valid": true,
        "issuer": "Let's Encrypt",
        "issued_at": "2025-04-09T23:15:00Z",
        "expires_at": "2025-07-09T23:15:00Z",
        "days_remaining": 89,
        "days_since_issuance": 1,
        "san_entries": ["nubankk.com", "www.nubankk.com"],
        "subject_cn": "nubankk.com"
      },
      "signals": [
        {
          "code": "ssl_issued_recently",
          "severity": "medium",
          "score_adjustment": 0.12,
          "description": "Certificado SSL emitido há menos de 7 dias."
        }
      ],
      "score_snapshot": { "before": 0.92, "after": 0.92 },
      "ttl_expires_at": "2025-04-24T12:16:01Z"
    },
    {
      "id": "ev000004",
      "event_type": "tool_execution",
      "event_source": "enrichment",
      "tool_name": "blacklist_check",
      "created_at": "2025-04-10T12:17:44Z",
      "result_data": {
        "spamhaus_dbl": true,
        "spamhaus_zen": false,
        "surbl": false,
        "uribl": true,
        "lists_hit": ["spamhaus_dbl", "uribl"],
        "total_checked": 4
      },
      "signals": [
        {
          "code": "blacklisted_spamhaus",
          "severity": "high",
          "score_adjustment": 0.20,
          "description": "Domínio encontrado na lista negra Spamhaus DBL."
        }
      ],
      "score_snapshot": { "before": 0.92, "after": 0.92 },
      "ttl_expires_at": "2025-04-13T12:17:44Z"
    },
    {
      "id": "ev000005",
      "event_type": "tool_execution",
      "event_source": "enrichment",
      "tool_name": "suspicious_page",
      "created_at": "2025-04-10T12:20:11Z",
      "result_data": {
        "page_type": "phishing",
        "has_login_form": true,
        "brand_logo_detected": true,
        "redirect_chain": ["http://nubankk.com", "https://nubankk.com/login"],
        "title": "Nubank — Acesse sua conta",
        "language": "pt",
        "http_status": 200
      },
      "signals": [
        {
          "code": "phishing_page_detected",
          "severity": "critical",
          "score_adjustment": 0.35,
          "description": "Página com formulário de login clonado detectada."
        }
      ],
      "score_snapshot": { "before": 0.92, "after": 0.92 },
      "ttl_expires_at": "2025-04-13T12:20:11Z"
    },
    {
      "id": "ev000006",
      "event_type": "llm_assessment",
      "event_source": "assessment",
      "tool_name": null,
      "created_at": "2025-04-10T12:31:00Z",
      "result_data": {
        "risco_score": 91,
        "categoria": "phishing_ativo",
        "parecer_resumido": "Domínio nubankk.com apresenta múltiplos indicadores de campanha de phishing ativa...",
        "principais_motivos": [
          "Página com formulário de login idêntico ao Nubank detectada",
          "Certificado SSL emitido há 3 dias via Let's Encrypt",
          "MX ativo: domínio pode enviar/receber e-mails",
          "Presente na lista Spamhaus DBL"
        ],
        "recomendacao_acao": "Acionar equipe jurídica imediatamente para takedown.",
        "confianca": 0.95
      },
      "signals": null,
      "score_snapshot": null,
      "ttl_expires_at": null
    }
  ],
  "total": 6
}
```

---

## 7. Campos existentes no banco mas SEM endpoint hoje

Estes campos existem nos modelos ORM mas ainda não são expostos via API na página da marca:

### `similarity_match` — campos não expostos no snapshot

| Campo | Tipo | Conteúdo |
|-------|------|----------|
| `score_trigram` | float | Score trigram isolado |
| `score_levenshtein` | float | Score Levenshtein isolado |
| `score_brand_hit` | float | Score de hit de marca |
| `score_keyword` | float | Score de keyword |
| `score_homograph` | float | Score de homógrafo |
| `actionability_score` | float | Score composto de acionabilidade |
| `reasons` | array | Lista de razões textuais do match |
| `attention_reasons` | array | Razões do bucket de atenção |
| `recommended_action` | string | Ação recomendada pelo scanner |
| `enrichment_summary` | JSONB | Resumo estruturado do enriquecimento |
| `confidence` | float | Confiança geral da classificação |
| `reviewed_by` | UUID | Quem revisou |
| `reviewed_at` | datetime | Quando foi revisado |

### `enrichment_summary` — estrutura raw (exemplo)

```json
{
  "target": "nubankk.com",
  "signals": [
    { "code": "phishing_page_detected", "severity": "critical", "description": "..." },
    { "code": "blacklisted_spamhaus", "severity": "high", "description": "..." }
  ],
  "tools": {
    "dns_lookup":       { "status": "ok",    "summary": { "resolves": true, "mx_active": true } },
    "whois":            { "status": "ok",    "summary": { "domain_age_days": 1, "privacy_protected": true } },
    "ssl_check":        { "status": "ok",    "summary": { "valid": true, "days_since_issuance": 1 } },
    "blacklist_check":  { "status": "ok",    "summary": { "lists_hit": ["spamhaus_dbl"], "total_checked": 4 } },
    "suspicious_page":  { "status": "ok",    "summary": { "page_type": "phishing", "has_login_form": true } },
    "safe_browsing":    { "status": "ok",    "summary": { "threat_types": [] } },
    "urlhaus":          { "status": "ok",    "summary": { "found": false } },
    "phishtank":        { "status": "ok",    "summary": { "in_database": false } },
    "email_security":   { "status": "ok",    "summary": { "spf": true, "dkim": false, "dmarc": false, "spoofing_risk": "medium" } },
    "ip_geolocation":   { "status": "ok",    "summary": { "country": "PW", "asn": "AS13335", "org": "Cloudflare" } },
    "http_headers":     { "status": "ok",    "summary": { "score": "poor", "missing": ["X-Frame-Options", "CSP"] } },
    "screenshot":       { "status": "ok",    "summary": { "captured": true, "s3_key": "screenshots/nubankk.com/2025-04-10.jpg" } }
  }
}
```

### `monitored_brand` — campo não exposto

| Campo | Tipo | Conteúdo |
|-------|------|----------|
| `alert_webhook_url` | string | URL de webhook para notificações automáticas |

---

## 8. Resumo: Oportunidades de Storytelling por Bloco

### 🧭 Header — "Quem é esta marca?"
**Hoje:** nome + badge de saúde + contadores  
**Potencial:** adicionar `noise_mode`, data de criação do monitoramento, total de TLDs monitorados, número de seeds ativas

---

### 🛡️ Saúde Própria — "Como estão nossos domínios?"
**Hoje:** tabela com ✓/✗ por check  
**Potencial:**
- Mostrar `days_remaining` do SSL com cor progressiva (verde > 60, amarelo > 30, vermelho < 30)
- Mostrar `spoofing_risk` como badge colorido
- Detalhar `headers.score` com chips das headers faltantes
- Mostrar todos os 10 checks (hoje só 6 são exibidos — faltam `takeover`, `safe_browsing`, `urlhaus`, `phishtank`, `suspicious_page`)
- Mini-gráfico de histórico de saúde por ciclo

---

### 📊 Atividade — "O que aconteceu nos últimos dias?"
**Hoje:** tabela de ciclos com status e contadores  
**Potencial:**
- Gráfico de linha: `threats_detected` por dia (últimos 30 dias)
- Gráfico de barras: `new_matches_count` vs `dismissed_count`
- Indicador de tempo de execução dos pipelines (`health_finished_at - health_started_at`)
- Diferencial: `enrichment_budget` vs `enrichment_total` (% de ameaças analisadas)

---

### ⚠️ Ameaças — "O que encontramos?"
**Hoje:** tabela com domain, bucket, score %, risk, 3 signal codes, data  
**Potencial:**
- Exibir `source_stream` (origem: certstream, czds, openintel, crtsh)
- Exibir `domain_first_seen` separado de `first_detected_at` (diferença = latência de detecção)
- Exibir `score_final` e `derived_score` lado a lado (impacto do enriquecimento)
- Exibir `matched_rule` como chip (exact_label_match, brand_containment, etc.)
- Mini coluna de sinais com severidade por cor
- Status da revisão humana (new/reviewing/confirmed_threat)

---

### 🔍 Drawer de Ameaça — "O que sabemos sobre este domínio?"
**Hoje:** scores, sinais, LLM assessment, timeline de eventos (resumida), form de review  
**Potencial:**
- Expandir eventos para mostrar `result_data` por ferramenta (accordion por tool)
- Exibir `score_snapshot.before/after` em cada evento (evolução do score)
- Mostrar `enrichment_summary.tools` como status cards de cada ferramenta
- Exibir `domain_first_seen` vs `first_detected_at` como "latência de detecção"
- Exibir país de registro, registrar, privacidade (do WHOIS)
- Exibir IP + ASN + país de hospedagem (do ip_geolocation)
- Screenshot capturada (se disponível no S3)
- Mostrar `delivery_risk` como badge separado
- Mostrar `confidence` do LLM

---

### ⚙️ Configuração — "Como a marca está configurada?"
**Hoje:** collapsible com domains, keywords, aliases, TLD scope, notes  
**Potencial:**
- Mostrar `seeds` com tipos e pesos (hoje omitido visualmente)
- Mostrar `noise_mode` com explicação do que significa
- Mostrar `alert_webhook_url` (configurado ou não)
- Mostrar `aliases` separados por tipo (brand_alias, brand_phrase, support_keyword)
- Explicar por que cada seed foi gerada (source_ref_type + source_ref_id)

---

## 9. Campos disponíveis no banco mas sem endpoint hoje (requerem novo endpoint)

Para implementar alguns dos potenciais acima, seria necessário um novo endpoint ou expandir os existentes:

| Dado desejado | O que é necessário |
|---------------|---------------------|
| Histórico de score de um match | Query em `monitoring_event` por `match_id` + extrair `score_snapshot` |
| Screenshot capturada | Campo no `enrichment_summary.tools.screenshot.s3_key` |
| Breakdown de scores léxicos | Campos em `similarity_match`: `score_trigram`, `score_levenshtein`, etc. |
| Evolução de ameaças por dia | Aggregate em `monitoring_cycle` — já existe, só precisa de endpoint de métricas |
| WHOIS raw | Campo `result_data` em `monitoring_event` com `tool_name = "whois"` |
| IP + ASN + país | Campo `result_data` em `monitoring_event` com `tool_name = "ip_geolocation"` |

---

*Documento gerado em: 2026-04-13 — baseado no código-fonte do frontend e backend em `feature/main`*
