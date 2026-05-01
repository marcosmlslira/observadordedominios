---
name: database-modeling
description: Expert in database modeling
---

# 🗄️ SKILL: Database Modeling Expert

> **Para GitHub Copilot** — Use este guia sempre que houver qualquer decisão de modelagem de dados: escolha de banco, design de entidades, relacionamentos, índices, estratégias de armazenamento ou evolução de schema.

---

## 🧠 Filosofia

> **"O banco de dados é o contrato mais difícil de quebrar em um sistema. Decida bem na primeira vez — mas projete para mudar."**

A modelagem não começa pelo banco. Começa pelos dados: como eles nascem, como são lidos, com que frequência mudam e por quanto tempo precisam existir. A tecnologia vem depois.

---

## 🔍 Etapa 0 — Antes de Modelar: Faça as Perguntas Certas

Nunca abra um editor de schema sem responder:

```
1. Qual é o padrão de acesso predominante? (leitura / escrita / ambos)
2. Os dados têm estrutura definida ou variam por registro?
3. Qual é o volume esperado? (hoje e em 2 anos)
4. Os dados se relacionam fortemente ou são independentes?
5. Preciso de consistência forte (ACID) ou posso aceitar consistência eventual?
6. Os dados são quentes (acessados frequentemente) ou frios (histórico)?
7. Preciso buscar por texto, por localização, por similaridade?
8. Os dados mudam com frequência ou são majoritariamente imutáveis?
```

As respostas a essas perguntas determinam **qual tecnologia usar antes de qualquer outra decisão**.

---

## 🗺️ Guia de Escolha de Tecnologia por Tipo de Dado

### 📊 Dados Relacionais e Transacionais
**Quando usar:** Entidades com relacionamentos claros, necessidade de joins, consistência ACID, regras de negócio com integridade referencial.

**Tecnologias:**
| Banco | Quando escolher |
|---|---|
| **PostgreSQL** | Padrão para a maioria dos sistemas. Rico em tipos, extensível, JSONB, full-text search nativo. Escolha por padrão. |
| **MySQL / MariaDB** | Quando o time já tem expertise ou há requisito de compatibilidade. Evitar para workloads analíticos. |
| **SQLite** | Desenvolvimento local, apps mobile, sistemas embarcados. Nunca em produção multi-usuário. |

**Sinais de que você está no lugar certo:**
- Dados têm forma consistente (mesmos campos por registro)
- Precisa de transações entre múltiplas entidades
- Relatórios e agregações são frequentes
- Integridade de dados é crítica

---

### 🔑 Cache e Dados de Sessão
**Quando usar:** Dados temporários, alta frequência de leitura/escrita, tolerância a perda, TTL definido.

**Tecnologias:**
| Banco | Quando escolher |
|---|---|
| **Redis** | Padrão para cache, sessões, filas simples, pub/sub, rate limiting, leaderboards. In-memory, sub-milissegundo. |
| **Memcached** | Cache simples de chave-valor sem estruturas complexas. Mais leve que Redis, menos features. |
| **DragonflyDB** | Alternativa moderna ao Redis com melhor performance e compatibilidade com a API do Redis. |

**Sinais de que você está no lugar certo:**
- Latência de leitura precisa ser < 5ms
- Dados podem ser reconstruídos se perdidos
- Acesso é sempre por chave exata (sem queries complexas)
- Dados têm expiração natural

---

### 📄 Dados Semiestruturados / Flexíveis
**Quando usar:** Estrutura variável por documento, hierarquias aninhadas, sem schema fixo.

**Tecnologias:**
| Banco | Quando escolher |
|---|---|
| **MongoDB** | Documentos ricos e aninhados, estrutura que varia por registro, times com preferência por JSON. Cuidado com consistência. |
| **PostgreSQL + JSONB** | Quando 80% dos dados são relacionais e 20% precisam de flexibilidade. Evita adicionar outro banco. |
| **CouchDB** | Quando sincronização offline e multi-master são requisitos. Nicho. |
| **DynamoDB** | Serverless AWS, escala massiva, acesso por chave/range. Custo de aprendizado alto de modelagem. |

**Sinais de que você está no lugar certo:**
- Cada registro pode ter campos diferentes
- Estrutura do dado evolui frequentemente
- Dados são naturalmente hierárquicos (sem normalização)
- Não precisa de joins complexos

---

### 🔍 Busca e Texto
**Quando usar:** Full-text search, autocomplete, busca facetada, relevância, fuzzy matching.

**Tecnologias:**
| Banco | Quando escolher |
|---|---|
| **Elasticsearch** | Busca avançada, logs, analytics. Poderoso mas caro para operar. |
| **Meilisearch** | Busca de produto simples e rápida. Fácil de operar, excelente UX. Ideal para startups. |
| **Typesense** | Alternativa ao Meilisearch, open source, busca tolerante a erros. |
| **PostgreSQL (pg_trgm + tsvector)** | Quando o volume é moderado e não quer adicionar outro serviço. Surpreendentemente capaz. |
| **Algolia** | SaaS gerenciado, fácil integração, caro em escala. Ótimo para MVP. |

**Sinais de que você está no lugar certo:**
- Usuário digita e espera sugestões em tempo real
- Busca precisa ser tolerante a erros de digitação
- Precisa de ranking por relevância
- Filtros combinados (facets) são comuns

---

### ⏱️ Dados de Série Temporal
**Quando usar:** Métricas, eventos com timestamp, IoT, monitoramento, logs estruturados.

**Tecnologias:**
| Banco | Quando escolher |
|---|---|
| **TimescaleDB** | Extensão do PostgreSQL. Melhor opção se já usa Postgres. Hypertables, compressão, funções de janela. |
| **InfluxDB** | Stack completo de observabilidade. Bom para IoT e métricas de infraestrutura. |
| **ClickHouse** | Analítica em escala massiva, OLAP, queries em bilhões de rows em segundos. |
| **QuestDB** | Alta performance de ingestão, SQL nativo. Ótimo para trading e IoT. |

**Sinais de que você está no lugar certo:**
- Dado sempre tem timestamp como dimensão principal
- Volume de ingestão é alto e constante
- Queries são sempre por range de tempo
- Dados antigos podem ser comprimidos ou deletados

---

### 🕸️ Dados de Grafo
**Quando usar:** Relacionamentos complexos e dinâmicos, múltiplos graus de separação, recomendações, redes sociais.

**Tecnologias:**
| Banco | Quando escolher |
|---|---|
| **Neo4j** | Padrão para grafos. Linguagem Cypher expressiva. Ótimo para social graph, fraud detection. |
| **Amazon Neptune** | Gerenciado AWS. Suporta Gremlin e SPARQL. |
| **PostgreSQL + pgRouting** | Grafos simples e roteamento quando já usa Postgres. |
| **ArangoDB** | Multi-model (documento + grafo). Quando precisa dos dois. |

**Sinais de que você está no lugar certo:**
- A pergunta envolve "conexões entre X e Y através de Z"
- Traversal de múltiplos níveis de relação é frequente
- Relacionamentos têm propriedades próprias
- Schema de relações muda com frequência

---

### 📍 Dados Geoespaciais
**Quando usar:** Coordenadas, polígonos, proximidade, rotas, mapas.

**Tecnologias:**
| Banco | Quando escolher |
|---|---|
| **PostgreSQL + PostGIS** | Padrão da indústria. Completo, maduro, integrado ao Postgres. |
| **MongoDB** | Suporte a geo integrado, bom para queries simples de proximidade. |
| **Redis + RedisGeo** | Queries de proximidade em tempo real, high throughput. |

**Sinais de que você está no lugar certo:**
- Dados têm latitude/longitude
- Precisa de "encontre os X mais próximos de Y"
- Trabalha com polígonos, regiões ou rotas
- Filtros combinam localização com outros atributos

---

### 📁 Arquivos e Objetos Binários
**Regra:** Nunca armazene arquivos binários no banco relacional.

| Solução | Quando usar |
|---|---|
| **S3 / R2 / GCS** | Padrão. Armazene a URL no banco, o arquivo no object storage. |
| **MinIO** | Self-hosted, compatível com S3 API. Para on-premise ou custo. |
| **Cloudinary / Imgix** | Quando precisa de transformação de imagens (resize, crop, CDN). |

**No banco, armazene apenas:**
- URL do arquivo
- Metadata (nome original, tamanho, mime type, hash)
- Referência à entidade dona do arquivo

---

## 🏗️ Projetando Entidades — Do Conceito ao Schema

### Passo 1 — Identifique as Entidades

Uma entidade é qualquer **coisa sobre a qual o sistema precisa guardar informação**. Encontre-as respondendo:

```
- Quais são os substantivos principais do domínio do negócio?
- O que o usuário cria, lê, atualiza ou deleta?
- O que tem identidade própria e ciclo de vida independente?
```

**Sinais de que algo é uma entidade (e não um atributo):**
- Tem múltiplos atributos próprios
- Pode existir independentemente de outra coisa
- Tem um ID próprio
- Outros registros fazem referência a ele

**Sinais de que algo é um atributo (e não uma entidade):**
- É sempre lido junto com outra entidade
- Não tem sentido existir sozinho
- Nunca é referenciado por outras entidades
- É um valor simples (string, número, booleano)

---

### Passo 2 — Mapeie os Relacionamentos

Para cada par de entidades, determine:

```
1. Qual é a cardinalidade? (1:1, 1:N, N:M)
2. O relacionamento é obrigatório ou opcional?
3. O relacionamento tem atributos próprios?
4. O que acontece com um lado quando o outro é deletado?
```

**Padrões de relacionamento:**

```
1:1  → Chave estrangeira na tabela menos acessada, ou merge na mesma tabela
1:N  → Chave estrangeira no lado N (filho aponta para pai)
N:M  → Tabela de junção com seus próprios atributos se necessário
```

**Relacionamentos com atributos próprios viram entidades:**
```
❌ User → (comprou) → Product
✅ User → Order → OrderItem → Product
         (data, total)  (qty, price)
```

---

### Passo 3 — Normalização com Bom Senso

Normalize até a **3ª Forma Normal (3NF)** como ponto de partida, mas desnormalize conscientemente quando houver razão de performance.

**Checklist de normalização:**
- [ ] Cada tabela representa uma única entidade ou relacionamento
- [ ] Cada coluna depende da chave primária inteira (não parcialmente)
- [ ] Nenhuma coluna depende de outra coluna não-chave
- [ ] Não há grupos repetitivos (arrays de valores em uma coluna)
- [ ] Não há dados duplicados que podem divergir

**Quando desnormalizar é correto:**
- Colunas denormalizadas para evitar joins caros em leitura intensiva
- Campos calculados quando o cálculo é caro e o dado muda pouco
- Tabelas de leitura (read models) em arquiteturas CQRS

---

### Passo 4 — Defina Chaves com Intenção

| Tipo de Chave | Quando usar | Cuidados |
|---|---|---|
| **UUID v4** | IDs expostos em URLs, sistemas distribuídos, multi-tenant | Index maior, não sequencial (fragmentação) |
| **UUID v7** | UUID com ordenação temporal. Melhor dos dois mundos. **Recomendado.** | Requer suporte no banco ou geração na aplicação |
| **BIGSERIAL / BIGINT auto** | Sistemas simples, não expostos externamente, joins internos | Não expor em URLs públicas |
| **ULID** | Alternativa ao UUID v7, legível, ordenável | Menos nativo nos bancos |
| **Chave natural** | Só quando o valor é verdadeiramente único e imutável (ex: CPF como secondary key) | Nunca como PK primária — valores de negócio mudam |

---

### Passo 5 — Indexação Estratégica

**Regra base:** Crie índices para as queries que você vai executar, não para as colunas que acha que serão buscadas.

```sql
-- Analise o padrão de acesso ANTES de criar o índice
-- Exemplo: se a query mais comum é:
SELECT * FROM orders WHERE user_id = ? AND status = ? ORDER BY created_at DESC;

-- O índice ideal é composto e na ordem certa:
CREATE INDEX idx_orders_user_status_created 
ON orders(user_id, status, created_at DESC);
```

**Tipos de índice e quando usar:**

| Tipo | Quando usar |
|---|---|
| **B-Tree** (padrão) | Igualdade, range, ORDER BY. Uso geral. |
| **Hash** | Apenas igualdade exata. Não suporta range. |
| **GIN** | Arrays, JSONB, full-text search |
| **GiST** | Dados geoespaciais, range types, similaridade |
| **BRIN** | Tabelas muito grandes com dados naturalmente ordenados (ex: logs por data) |
| **Partial Index** | Quando só um subconjunto dos dados é consultado frequentemente |

```sql
-- Partial index: só indexa pedidos ativos (não os históricos)
CREATE INDEX idx_orders_active ON orders(user_id, created_at)
WHERE status NOT IN ('completed', 'cancelled');
```

**Antipadrões de indexação:**
- ❌ Indexar todas as colunas "por precaução"
- ❌ Índice em colunas de baixa cardinalidade (ex: boolean, status com 2 valores)
- ❌ Índices redundantes (A,B já cobre queries em A)
- ❌ Nunca revisar índices não utilizados (custam espaço e escrita)

---

## 📐 Templates de Schema

### Entidade Base (padrão para qualquer tabela)

```sql
CREATE TABLE entities (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- ou UUID v7
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at  TIMESTAMPTZ                                  -- soft delete opcional
);

-- Trigger para updated_at automático
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;
```

### Multi-tenancy por Row (mais comum em SaaS)

```sql
-- Toda tabela do tenant tem tenant_id
ALTER TABLE resources ADD COLUMN tenant_id UUID NOT NULL REFERENCES tenants(id);

-- Índice composto sempre começa com tenant_id
CREATE INDEX idx_resources_tenant ON resources(tenant_id, created_at DESC);

-- RLS (Row Level Security) no PostgreSQL
ALTER TABLE resources ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON resources
  USING (tenant_id = current_setting('app.current_tenant')::uuid);
```

### Tabela de Auditoria / Event Log

```sql
CREATE TABLE audit_logs (
  id          BIGSERIAL PRIMARY KEY,
  entity_type VARCHAR(100) NOT NULL,
  entity_id   UUID NOT NULL,
  action      VARCHAR(20) NOT NULL,  -- CREATE, UPDATE, DELETE
  actor_id    UUID,                   -- quem fez
  actor_type  VARCHAR(50),            -- user, system, api_key
  old_data    JSONB,
  new_data    JSONB,
  metadata    JSONB,                  -- IP, user agent, etc
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Índices para as queries mais comuns
CREATE INDEX idx_audit_entity ON audit_logs(entity_type, entity_id, occurred_at DESC);
CREATE INDEX idx_audit_actor  ON audit_logs(actor_id, occurred_at DESC);
```

### Status com Máquina de Estados

```sql
-- Nunca use string livre para status — use enum ou constraint
CREATE TYPE order_status AS ENUM (
  'draft', 'pending_payment', 'paid', 'processing', 
  'shipped', 'delivered', 'cancelled', 'refunded'
);

CREATE TABLE orders (
  id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  status  order_status NOT NULL DEFAULT 'draft',
  -- ...
  CONSTRAINT valid_status_transition CHECK (
    -- regras de transição podem ser validadas aqui ou na aplicação
    status IS NOT NULL
  )
);
```

---

## 🚨 Antipadrões — O que Nunca Fazer

```
❌ EAV (Entity-Attribute-Value)
   Tabelas genéricas com colunas "key" e "value".
   Parece flexível, é um pesadelo de queries e integridade.
   → Use JSONB se precisar de flexibilidade.

❌ Colunas de status como string livre
   status = "ativo", "Ativo", "ATIVO", "active"...
   → Use ENUM ou tabela de lookup com FK.

❌ Arrays de IDs em uma coluna
   user_ids = "1,2,3,45,67"
   → Use tabela de junção.

❌ Lógica de negócio no nome da coluna
   is_premium_user_who_signed_up_before_2023
   → Derive na aplicação, não encode no schema.

❌ Timestamps sem timezone
   TIMESTAMP em vez de TIMESTAMPTZ
   → Sempre use TIMESTAMPTZ. Sempre.

❌ Soft delete sem índice parcial
   WHERE deleted_at IS NULL em toda query sem índice
   → CREATE INDEX ... WHERE deleted_at IS NULL

❌ Chave primária composta em tabelas de negócio
   PRIMARY KEY (user_id, product_id) em tabelas com comportamento
   → Use surrogate key (UUID) + unique constraint no composto.

❌ Busca com LIKE '%termo%'
   Não usa índice, full scan em produção
   → Use full-text search (tsvector, Meilisearch, etc.)
```

---

## 🔄 Evolução de Schema — Migrações Seguras

### Regras para migrações sem downtime:

```
1. NUNCA faça DROP em produção sem ciclo de deprecação
2. Adicionar coluna nullable é seguro. Adicionar NOT NULL sem DEFAULT não é.
3. Renomear coluna = adicionar nova + migrar dados + remover antiga (3 deploys)
4. Índices grandes: CREATE INDEX CONCURRENTLY (não bloqueia writes)
5. Toda migração deve ter rollback definido antes de executar
```

**Ciclo seguro para mudar uma coluna:**
```
Deploy 1: Adiciona nova coluna (nullable)
Deploy 2: Aplicação escreve em ambas as colunas
Deploy 3: Migra dados históricos (batch, fora do horário de pico)
Deploy 4: Aplicação lê da nova coluna
Deploy 5: Remove a coluna antiga
```

---

## ✅ Checklist de Revisão de Modelagem

Antes de aplicar qualquer schema em produção:

```markdown
### Estrutura
- [ ] Cada tabela representa uma única entidade/conceito
- [ ] Não há grupos repetitivos ou arrays de valores em colunas
- [ ] Relacionamentos N:M têm tabela de junção
- [ ] Relacionamentos com atributos viraram entidades próprias

### Chaves e Tipos
- [ ] PKs são surrogates (UUID v7 ou BIGSERIAL)
- [ ] Todos os campos de tempo usam TIMESTAMPTZ
- [ ] Status e enums usam tipo definido, não string livre
- [ ] Campos obrigatórios têm NOT NULL

### Performance
- [ ] Índices criados para as queries principais (não "por precaução")
- [ ] Soft delete tem índice parcial
- [ ] Queries de listagem têm limite de paginação

### Segurança e Operação
- [ ] Dados sensíveis identificados (PII, financeiro)
- [ ] Estratégia de auditoria definida para entidades críticas
- [ ] Plano de migração tem rollback documentado
- [ ] Volume esperado avaliado (índices BRIN? Particionamento necessário?)
```

---

## 💬 Dicas para o Copilot ao Usar Esta Skill

- Sempre pergunte o padrão de acesso antes de sugerir um banco.
- PostgreSQL é o default seguro para 80% dos casos — não recomende MongoDB sem razão clara.
- Quando o schema envolver multi-tenancy, sempre mencione RLS.
- Sugira UUID v7 sobre UUID v4 em novos projetos.
- Se o dado é arquivo binário, redirecione para object storage imediatamente.
- Sempre verifique se um índice existente já cobre a necessidade antes de criar um novo.
- Em migrações, pergunte sobre downtime tolerance antes de sugerir a abordagem.

---

*SKILL.md — Database Modeling Expert | Versão 1.0*
