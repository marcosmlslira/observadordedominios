# Redesenho do Monitoramento de Similaridade por Perfil

> Data: 2026-03-24
> Status: Proposta tecnica para implementacao incremental
> Escopo: backend, API admin, worker de similaridade, observabilidade e migracao do modelo atual

## 1. Problema a corrigir

O modelo atual trata uma marca monitorada como uma unica string:

- tabela atual: `monitored_brand`
- sinal principal: `brand_label`
- API atual: `POST /v1/brands`
- scanner atual: `run_similarity_scan()` usa apenas `brand.brand_label`

Isso funciona razoavelmente para seeds simples como:

- `listenx`
- `comgas`
- `gsuplementos`

Mas quebra quando o ponto de partida real do cliente e um dominio oficial completo, por exemplo:

- `gsuplementos.com.br`
- `comgas.com.br`
- `listenx.com.br`

Hoje o sistema converte esse valor para um `brand_label` unico e tenta procurar variacoes como se ele fosse uma label registravel. O resultado e ruim por tres motivos:

1. `gsuplementos.com.br` nao deve ser buscado como uma label unica no canal de dominios registraveis.
2. Casos como `gsuplementos.com.net` pertencem ao canal de hostname/certificado, nao ao canal de zone file.
3. Quando a marca comercial e o dominio oficial divergem, um unico label nao representa a identidade monitorada.

O produto precisa continuar partindo do dominio oficial, mas de forma decomposta e multi-canal.

## 2. Objetivo do redesenho

Trocar o modelo atual de "marca monitorada = um label" por "perfil de monitoramento = identidade composta".

Esse perfil deve permitir monitorar, ao mesmo tempo:

- marca principal
- dominios oficiais
- labels derivados desses dominios
- aliases e marcas associadas
- termos de apoio

Sem obrigar o usuario a entender a estrutura interna do motor.

## 3. Principios do novo modelo

- O usuario cadastra um perfil simples.
- O sistema gera seeds tecnicas automaticamente.
- Seeds nao sao equivalentes entre si; cada uma tem peso e canal proprios.
- O motor separa deteccao de:
  - dominio registravel
  - hostname/certificado
  - marca associada
- Palavras genericas nunca devem disparar sozinhas.
- O front deve sempre explicar por qual sinal e por qual canal o match foi encontrado.

## 4. Entidade principal: Monitoring Profile

### 4.1 Conceito

`MonitoringProfile` passa a ser a unidade principal de monitoramento.

Ele substitui conceitualmente o `MonitoredBrand`, mas a migracao deve ser incremental para nao quebrar o sistema atual.

### 4.2 Campos de negocio

- `display_name`
  - nome amigavel do perfil no admin
  - exemplo: `Growth Suplementos`
- `primary_brand_name`
  - nome principal da marca
  - exemplo: `Growth Suplementos`
- `noise_mode`
  - `conservative | standard | broad`
- `tld_scope`
  - lista de TLDs para o canal de dominios registraveis
- `is_active`
- `notes`

### 4.3 Modelo alvo de dados

```sql
CREATE TABLE monitoring_profile (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL,
    display_name VARCHAR(253) NOT NULL,
    primary_brand_name VARCHAR(253) NOT NULL,
    noise_mode VARCHAR(16) NOT NULL DEFAULT 'standard',
    tld_scope TEXT[] NOT NULL DEFAULT '{}',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
```

## 5. Entidades filhas do perfil

### 5.1 Dominios oficiais

Representam os dominios reais e canonicos do cliente.

Exemplos:

- `gsuplementos.com.br`
- `growth.com`

Schema:

```sql
CREATE TABLE monitoring_profile_domain (
    id UUID PRIMARY KEY,
    profile_id UUID NOT NULL REFERENCES monitoring_profile(id) ON DELETE CASCADE,
    domain_name VARCHAR(253) NOT NULL,
    registrable_domain VARCHAR(253) NOT NULL,
    registrable_label VARCHAR(228) NOT NULL,
    public_suffix VARCHAR(24) NOT NULL,
    hostname_stem VARCHAR(228) NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX uq_profile_domain_name
ON monitoring_profile_domain(profile_id, domain_name);
```

Regras:

- `registrable_domain` e a porcao registravel canonicamente normalizada.
- `registrable_label` e o label que deve alimentar CZDS.
- `hostname_stem` e opcional e serve para CT/hostname.

Exemplo:

| domain_name | registrable_domain | registrable_label | public_suffix | hostname_stem |
|---|---|---|---|---|
| `gsuplementos.com.br` | `gsuplementos.com.br` | `gsuplementos` | `com.br` | `gsuplementos.com` |

### 5.2 Aliases e marcas associadas

Representam nomes comerciais, nomes curtos, aliases, frases e variantes conhecidas.

Schema:

```sql
CREATE TABLE monitoring_profile_alias (
    id UUID PRIMARY KEY,
    profile_id UUID NOT NULL REFERENCES monitoring_profile(id) ON DELETE CASCADE,
    alias_value VARCHAR(253) NOT NULL,
    alias_type VARCHAR(24) NOT NULL,
    weight_override NUMERIC(4,2) NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX uq_profile_alias_value
ON monitoring_profile_alias(profile_id, alias_value, alias_type);
```

Tipos recomendados:

- `brand_primary`
- `brand_alias`
- `brand_phrase`
- `support_keyword`

Exemplo para Growth:

- `Growth Suplementos` -> `brand_primary`
- `growth` -> `brand_alias`
- `growth suplementos` -> `brand_phrase`
- `suplementos` -> `support_keyword`

### 5.3 Seeds tecnicas

Seeds sao o formato interno usado pelo motor. Podem ser derivadas automaticamente ou cadastradas manualmente.

Schema:

```sql
CREATE TABLE monitoring_seed (
    id UUID PRIMARY KEY,
    profile_id UUID NOT NULL REFERENCES monitoring_profile(id) ON DELETE CASCADE,
    source_ref_type VARCHAR(24) NOT NULL,
    source_ref_id UUID NULL,
    seed_value VARCHAR(253) NOT NULL,
    seed_type VARCHAR(32) NOT NULL,
    channel_scope VARCHAR(32) NOT NULL,
    base_weight NUMERIC(4,2) NOT NULL,
    is_manual BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX ix_seed_profile_channel
ON monitoring_seed(profile_id, channel_scope, is_active);
```

Tipos recomendados:

- `official_domain`
- `domain_label`
- `hostname_stem`
- `brand_primary`
- `brand_alias`
- `brand_phrase`
- `support_keyword`

Canal:

- `registrable_domain`
- `certificate_hostname`
- `associated_brand`
- `both`

## 6. Seeds derivadas automaticamente

O sistema deve gerar seeds automaticamente quando um perfil ou seus filhos forem alterados.

### 6.1 A partir de dominio oficial

Entrada:

- `gsuplementos.com.br`

Seeds:

- `gsuplementos` -> `domain_label`, canal `registrable_domain`, peso alto
- `gsuplementos.com.br` -> `official_domain`, canal `certificate_hostname`, peso medio
- `gsuplementos.com` -> `hostname_stem`, canal `certificate_hostname`, peso alto

### 6.2 A partir da marca principal

Entrada:

- `Growth Suplementos`

Seeds:

- `growth suplementos` -> `brand_primary`
- `growth` -> `brand_alias`

### 6.3 A partir de termos de apoio

Entrada:

- `suplementos`

Seed:

- `suplementos` -> `support_keyword`, canal `associated_brand`, peso baixo

### 6.4 Regras

- `support_keyword` nunca pode disparar match sozinha.
- `brand_alias` curto ou generico precisa de coocorrencia ou match mais forte.
- `official_domain` nao entra no canal de dominio registravel como string unica.
- `hostname_stem` existe apenas para CT/crt.sh/CertStream.

## 7. Canais de deteccao

O motor deve separar os resultados por canal.

### 7.1 Registrable domain

Fonte principal:

- tabela `domain` populada por CZDS

Objetivo:

- identificar dominios registraveis suspeitos

Exemplos:

- `gsuplementos.net`
- `growthsuplementos.store`
- `g-suplementos.com`

Seeds aceitas:

- `domain_label`
- `brand_primary`
- `brand_alias`
- `brand_phrase`

Seeds proibidas:

- `official_domain`
- `hostname_stem`

### 7.2 Certificate hostname

Fontes principais:

- CertStream
- crt.sh

Objetivo:

- identificar hostnames e certificados suspeitos

Exemplos:

- `gsuplementos.com.net`
- `login.gsuplementos-secure.app`
- `growthsuplementos.com.evil.tld`

Seeds aceitas:

- `hostname_stem`
- `official_domain`
- `domain_label`
- `brand_phrase`

### 7.3 Associated brand

Objetivo:

- cobrir casos em que a marca comercial diverge do dominio oficial

Exemplos:

- `growth-login.app`
- `growthpay-secure.net`

Seeds aceitas:

- `brand_primary`
- `brand_alias`
- `brand_phrase`
- `support_keyword` apenas como reforco

## 8. Mudancas no score

O score atual e centrado em `brand_label`. O novo score precisa considerar:

- qualidade da seed
- canal em que o match surgiu
- tipo de evidencia lexical
- contexto suspeito
- confianca da fonte

### 8.1 Pesos base por tipo de seed

| seed_type | peso_base |
|---|---:|
| `domain_label` | 1.00 |
| `hostname_stem` | 0.95 |
| `brand_primary` | 0.90 |
| `official_domain` | 0.85 |
| `brand_phrase` | 0.80 |
| `brand_alias` | 0.65 |
| `support_keyword` | 0.20 |

### 8.2 Multiplicador por canal

| canal | multiplicador |
|---|---:|
| `registrable_domain` | 1.00 |
| `certificate_hostname` | 0.85 |
| `associated_brand` | 0.75 |

### 8.3 Sinais lexicais

| sinal | faixa recomendada |
|---|---:|
| exact label match | 1.00 |
| typo forte | 0.90 |
| typo leve / transposicao | 0.80 |
| homograph / leet | 0.85 |
| containment forte | 0.60 |
| containment fraco | 0.35 |
| keyword risk context | 0.20 a 0.35 |

### 8.4 Formula recomendada

```text
score_raw =
  (seed_weight * 0.30) +
  (channel_multiplier * 0.15) +
  (lexical_signal * 0.30) +
  (keyword_context * 0.15) +
  (source_confidence * 0.10)

score_final = clamp(score_raw, 0, 1)
```

### 8.5 Regras de corte

- `support_keyword` sozinha nunca persiste match.
- `brand_alias` com menos de 6 caracteres exige:
  - exact match, ou
  - typo forte, ou
  - coocorrencia com outro seed
- hostnames encontrados por CT devem persistir com um threshold ligeiramente maior do que o canal registravel para controlar ruido.

## 9. Mudancas no resultado persistido

`similarity_match` precisa explicar o caminho de deteccao.

### 9.1 Campos novos recomendados

```sql
ALTER TABLE similarity_match
ADD COLUMN matched_channel VARCHAR(32) NULL,
ADD COLUMN matched_seed_id UUID NULL,
ADD COLUMN matched_seed_value VARCHAR(253) NULL,
ADD COLUMN matched_seed_type VARCHAR(32) NULL,
ADD COLUMN matched_rule VARCHAR(32) NULL,
ADD COLUMN source_stream VARCHAR(32) NULL;
```

Valores esperados:

- `matched_channel`
  - `registrable_domain`
  - `certificate_hostname`
  - `associated_brand`
- `matched_rule`
  - `exact_label_match`
  - `typo_candidate`
  - `homograph`
  - `brand_containment`
  - `hostname_containment`
  - `brand_plus_keyword`
- `source_stream`
  - `czds`
  - `certstream`
  - `crtsh`
  - `crtsh-bulk`

### 9.2 Beneficio operacional

O front passa a mostrar:

- por qual canal o achado apareceu
- qual seed disparou
- qual regra gerou o score

Isso reduz o ruido e melhora muito a triagem.

## 10. API alvo

## 10.1 Compatibilidade

`/v1/brands` deve continuar funcionando durante a migracao, mas internamente deve virar uma camada de compatibilidade sobre `monitoring_profile`.

### 10.2 Novos endpoints

#### Perfil principal

- `GET /v1/monitoring/profiles`
- `POST /v1/monitoring/profiles`
- `GET /v1/monitoring/profiles/{profile_id}`
- `PATCH /v1/monitoring/profiles/{profile_id}`

Payload de criacao:

```json
{
  "display_name": "Growth Suplementos",
  "primary_brand_name": "Growth Suplementos",
  "noise_mode": "standard",
  "tld_scope": ["com", "net", "org", "store", "app"],
  "is_active": true
}
```

#### Dominios oficiais

- `GET /v1/monitoring/profiles/{profile_id}/domains`
- `POST /v1/monitoring/profiles/{profile_id}/domains`
- `PATCH /v1/monitoring/domains/{domain_id}`
- `DELETE /v1/monitoring/domains/{domain_id}`

Payload:

```json
{
  "domain_name": "gsuplementos.com.br",
  "is_primary": true
}
```

#### Aliases

- `GET /v1/monitoring/profiles/{profile_id}/aliases`
- `POST /v1/monitoring/profiles/{profile_id}/aliases`
- `PATCH /v1/monitoring/aliases/{alias_id}`
- `DELETE /v1/monitoring/aliases/{alias_id}`

Payload:

```json
{
  "alias_value": "growth",
  "alias_type": "brand_alias"
}
```

#### Seeds e diagnostico

- `GET /v1/monitoring/profiles/{profile_id}/seeds`
- `POST /v1/monitoring/profiles/{profile_id}/seeds/regenerate`

Response de diagnostico:

```json
{
  "items": [
    {
      "seed_value": "gsuplementos",
      "seed_type": "domain_label",
      "channel_scope": "registrable_domain",
      "base_weight": 1.0,
      "derived_from": "official_domain"
    }
  ]
}
```

#### Scan

- `POST /v1/monitoring/profiles/{profile_id}/scan`

Parametros:

- `force_full`
- `channel`
  - `registrable_domain`
  - `certificate_hostname`
  - `all`

## 10.3 Mudanca na API de matches

Endpoint atual:

- `GET /v1/brands/{brand_id}/matches`

Compatibilidade recomendada:

- manter o endpoint
- internamente ler `profile_id`

Campos novos de response:

```json
{
  "matched_channel": "certificate_hostname",
  "matched_seed_type": "hostname_stem",
  "matched_seed_value": "gsuplementos.com",
  "matched_rule": "hostname_containment",
  "source_stream": "certstream"
}
```

## 11. UI admin alvo

Substituir a tela atual de "Monitored Brands" por "Monitoring Profiles".

### 11.1 Estrutura do formulario

- bloco `Perfil`
  - display name
  - marca principal
  - modo de ruido
- bloco `Dominios oficiais`
  - lista editavel
  - marcar primario
- bloco `Marcas associadas`
  - aliases e frases
- bloco `Termos de apoio`
  - editavel
- bloco `TLD scope`

### 11.2 Tela de resultado

Cada match deve mostrar:

- dominio encontrado
- canal
- seed usada
- regra
- score
- risco

Exemplo:

```text
gsuplementos.com.net
Canal: certificate_hostname
Detectado por: hostname_stem -> gsuplementos.com
Regra: hostname_containment
Risco: high
```

## 12. Estrategia de migracao

## 12.1 Fase 1: adicionar modelo novo sem quebrar o atual

- criar tabelas novas:
  - `monitoring_profile`
  - `monitoring_profile_domain`
  - `monitoring_profile_alias`
  - `monitoring_seed`
- manter `monitored_brand`
- manter workers atuais funcionando

## 12.2 Fase 2: backfill

Para cada `monitored_brand`:

- criar `monitoring_profile`
- copiar:
  - `brand_name` -> `display_name`
  - `brand_name` -> `primary_brand_name` se for um nome comercial plausivel
  - `keywords` -> aliases/keywords conforme heuristica
  - `tld_scope` -> `tld_scope`

Heuristica importante:

- se `brand_name` contem ponto e parece FQDN:
  - cadastrar em `monitoring_profile_domain`
  - derivar `registrable_label`
  - nao usar o FQDN como `brand_primary`
- se `brand_name` nao parece FQDN:
  - usar como `primary_brand_name`

## 12.3 Fase 3: gerar seeds

- rodar job de `seed regeneration`
- auditar seeds geradas por perfil

## 12.4 Fase 4: compatibilidade de API

- `/v1/brands` passa a operar sobre `monitoring_profile`
- front atual continua funcional

## 12.5 Fase 5: migrar UI

- nova tela de perfis
- visibilidade de seeds e canal

## 12.6 Fase 6: reprocessar

- rerun completo de similaridade por perfil
- repersistir matches com `matched_channel` e `matched_seed`

## 13. Exemplo completo

Entrada desejada pelo usuario:

```json
{
  "display_name": "Growth Suplementos",
  "primary_brand_name": "Growth Suplementos",
  "official_domains": ["gsuplementos.com.br"],
  "aliases": [
    { "value": "growth", "type": "brand_alias" },
    { "value": "growth suplementos", "type": "brand_phrase" }
  ],
  "support_keywords": ["suplementos"]
}
```

Seeds derivadas:

- `gsuplementos` -> `domain_label`
- `gsuplementos.com.br` -> `official_domain`
- `gsuplementos.com` -> `hostname_stem`
- `growth suplementos` -> `brand_primary`
- `growth` -> `brand_alias`
- `suplementos` -> `support_keyword`

Resultados esperados por canal:

- `gsuplementos.net` -> `registrable_domain`
- `gsuplementos.com.net` -> `certificate_hostname`
- `growth-login.app` -> `associated_brand`

## 14. Ordem recomendada de implementacao

1. Criar schema novo e seeds derivadas.
2. Adaptar backend para ler perfil em vez de um unico `brand_label`.
3. Enriquecer `similarity_match` com canal e seed.
4. Criar endpoint de diagnostico de seeds.
5. Migrar o admin para `Monitoring Profiles`.
6. Reprocessar a base e revisar thresholds de ruido.

## 15. Decisoes travadas

- O produto continua partindo de dominios oficiais.
- Dominio oficial completo nao deve ser tratado como um unico `brand_label`.
- `gsuplementos.com.net` e caso de hostname/certificado, nao de CZDS.
- `crtsh-bulk` continua manual e nao entra como scheduler.
- Termos genericos continuam permitidos, mas apenas como reforco de score.

## 16. Impacto esperado

Se implementado dessa forma, o sistema melhora em quatro frentes:

- reduz falsos negativos para perfis baseados em dominio oficial
- reduz falsos positivos de aliases genericos
- separa claramente o que e dominio registravel do que e hostname/certificado
- melhora a triagem porque cada match passa a explicar exatamente por que apareceu
