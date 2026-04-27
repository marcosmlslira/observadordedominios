# Especificação de Refatoração: FastAPI Moderno (Async/Templates)

## 1. Motivação e Objetivos

O estado atual do backend utiliza padrões síncronos herdados de versões anteriores, o que limita a escalabilidade do FastAPI e cria acoplamento excessivo entre as rotas e o banco de dados.

**Objetivos da refatoração:**
- **Performance:** Migrar de I/O bloqueante (síncrono) para não bloqueante (`async/await`), permitindo que o FastAPI processe milhares de requisições simultâneas eficientemente.
- **Arquitetura Clean:** Implementar rigorosamente o **Repository Pattern** e **Service Layer**, removendo lógica de banco de dados e consultas das rotas.
- **Tipagem Forte:** Adotar o SQLAlchemy 2.0 (estilo 2.0 com `select()`) em conjunto com `AsyncSession`.

---

## 2. Mudanças de Infraestrutura e Dependências

### 2.1. Driver de Banco de Dados (`pyproject.toml`)
- **Remover:** `psycopg2-binary` (Driver síncrono).
- **Adicionar:** `asyncpg` (Driver assíncrono para PostgreSQL).
- **Justificativa:** O driver assíncrono é obrigatório para utilizar `AsyncSession` do SQLAlchemy sem bloquear o loop de eventos.

### 2.2. Sessão de Banco (`backend/app/infra/db/session.py`)
- **Alterar `create_engine`** para `create_async_engine`.
- **Alterar `sessionmaker`** para usar `class_=AsyncSession`.
- **Novo `get_db`:**
  ```python
  async def get_db() -> AsyncGenerator[AsyncSession, None]:
      async with AsyncSessionLocal() as session:
          try:
              yield session
              await session.commit()
          except Exception:
              await session.rollback()
              raise
  ```

---

## 3. Refatoração das Camadas (Domínio a Domínio)

### 3.1. Camada de Repositório (`backend/app/repositories/`)
Atualmente, muitos repositórios usam `db.query()`. Eles devem ser convertidos para:
- **Assinaturas:** De `def` para `async def`.
- **Sintaxe SQLAlchemy 2.0:**
  - **Antigo:** `db.query(Model).filter(...)`
  - **Novo:** `stmt = select(Model).where(...)` -> `result = await db.execute(stmt)` -> `result.scalars().first()`.
- **Justificativa:** Compatibilidade com execução assíncrona e melhor suporte a tipagem estática.

### 3.2. Camada de Serviço (`backend/app/services/`)
- **Assinaturas:** De `def` para `async def`.
- **Chamadas:** Adicionar `await` em todas as interações com repositórios.
- **Justificativa:** Garantir que a pilha de chamadas seja assíncrona do início ao fim.

### 3.3. Camada de Rotas (`backend/app/api/v1/routers/`)
Esta é a camada com maior volume de código legado (mais de 80 funções `def`).
- **Definição:** Mudar todos os `@router.get/post/... def` para `async def`.
- **Dependência:** Injetar `db: AsyncSession = Depends(get_db)`.
- **Desacoplamento:** Mover qualquer lógica residual de `db.query` ou manipulação de modelos para os respectivos Serviços.
- **Justificativa:** Permite que o FastAPI execute as rotas de forma não bloqueante.

---

## 4. Plano de Execução Gradual (Estratégia Anti-Quebra)

Para evitar que a aplicação pare de funcionar, a refatoração deve seguir esta ordem:

1. **Setup Dual:** Manter temporariamente o `get_db` síncrono e criar um `get_async_db` novo.
2. **Migração por Arquivo:**
   - Escolher um router (ex: `auth.py`).
   - Identificar todos os serviços e repositórios usados por ele.
   - Refatorar Repositórios -> Serviços -> Rotas desse domínio específico para `async`.
   - Testar unitariamente e manualmente.
3. **Limpeza:** Quando o último arquivo for migrado, remover o `get_db` síncrono e o driver `psycopg2`.

---

## 5. Arquivos Críticos Identificados

| Arquivo | Problema | Prioridade |
| :--- | :--- | :--- |
| `backend/app/api/v1/routers/ingestion.py` | Volume massivo de rotas `def` e lógica complexa. | Alta |
| `backend/app/api/v1/routers/similarity.py` | Uso intensivo de `db.query` direto nas rotas. | Alta |
| `backend/app/repositories/similarity_repository.py` | Repositório com lógica densa que precisa de refatoração 2.0. | Média |
| `backend/app/infra/db/session.py` | Ponto central de falha se migrado incorretamente. | Crítica |

> **Correção factual (2026-04-27):** uma versão anterior desta tabela afirmava `similarity_repository.py >40k linhas`. O arquivo real tem **1.232 linhas** — denso, mas tratável. Mantido como prioridade Média pela complexidade lógica, não pelo tamanho.

---

## 6. Impacto nos Fluxos Principais

A refatoração assíncrona afetará os pilares fundamentais do sistema da seguinte forma:

### 6.1. Fluxos de Ingestão (CZDS, OpenIntel, ZoneFiles)
- **Status Atual:** A ingestão é acionada por rotas síncronas que muitas vezes iniciam tarefas em background ou processam grandes volumes de metadados de TLDs.
- **Mudança:** A migração para `async` permitirá que o roteador de ingestão (`ingestion.py` e `czds_ingestion.py`) gerencie múltiplas verificações de status e gatilhos de workers sem ocupar threads do servidor.
- **Ganhos:** Maior responsividade do painel de controle durante ciclos pesados de ingestão.

### 6.2. Busca de Similaridade
- **Status Atual:** O `similarity_repository.py` é um dos mais complexos, realizando consultas pesadas para cruzamento de marcas e domínios.
- **Mudança:** As consultas de similaridade serão convertidas para o estilo SQLAlchemy 2.0 Assíncrono. Isso é crítico, pois buscas de similaridade são intensivas em I/O de banco.
- **Desafio:** Garantir que as lógicas de agregação e filtros de "self-owned" não sofram regressão de performance durante a tradução para `select().where()`.

### 6.3. Módulo de Tools (DNS, Whois, Screenshots)
- **Status Atual:** Ferramentas como `dns_lookup`, `whois_lookup` e `screenshot` são inerentemente lentas por dependerem de serviços externos. Atualmente, o servidor pode ficar "preso" esperando esses retornos se o pool de threads esgotar.
- **Mudança:**
    - **DNS:** O `dnspython` já suporta chamadas assíncronas que devem ser implementadas.
    - **Whois/GeoIP:** Como são bibliotecas síncronas, deverão ser encapsuladas em `run_in_executor` para não travar o loop de eventos.
    - **Screenshots:** A integração com Playwright já deve ser garantida como assíncrona.
- **Ganhos:** O sistema poderá processar dezenas de análises de ferramentas simultaneamente sem enfileiramento no nível do servidor web.

---

## 7. Grau de Preocupação e Auditoria de Código

Dada a complexidade e o tamanho atual do backend, a preocupação deve ser **alta**, pois o projeto encontra-se em um estado "híbrido perigoso": ele usa um framework assíncrono (FastAPI), mas quase toda a sua implementação interna é síncrona e bloqueante.

### 7.1. Contagem de Referências Problemáticas
Após uma auditoria inicial, foram identificados os seguintes pontos críticos que exigem refatoração:

- **Roteadores (API):** Foram encontradas **89 definições de rotas síncronas (`def`)**. Destas, pelo menos **6 rotas críticas** (especialmente em `similarity.py` e `monitored_brands.py`) realizam consultas ao banco de dados (`db.query`) diretamente no corpo da função, violando a separação de camadas.
- **Repositórios:** Foram localizadas **49 ocorrências de `db.query` ou `session.query`** espalhadas por 11 arquivos de repositório diferentes. O `similarity_repository.py` e o `ingestion_run_repository.py` concentram a lógica mais densa e difícil de migrar.
- **Serviços Bloqueantes:** Foi detectado o uso de `time.sleep()` e `httpx.Client` (síncrono) dentro de serviços de geração de sementes (`generate_brand_seeds.py`). Em um ambiente assíncrono, um `time.sleep(40)` durante um rate limit travaria **todo o backend** para todos os usuários.

### 7.2. Por que se preocupar?
1. **Gargalo Invisível:** O sistema pode parecer funcionar bem com poucos usuários, mas sob carga moderada, o tempo de resposta aumentará exponencialmente devido ao esgotamento das threads de trabalho (worker threads) do FastAPI, que estão sendo usadas para esperar o banco de dados.
2. **Débito Técnico de Manutenção:** O SQLAlchemy 2.0 (estilo assíncrono) tem uma sintaxe fundamentalmente diferente. Quanto mais código for escrito no padrão antigo (`db.query`), mais caro e arriscado será o processo de migração no futuro.
3. **Instabilidade de Performance:** Processos de ingestão pesados podem causar "micro-travamentos" na UI do usuário final, pois o loop de eventos fica impedido de processar requisições simples enquanto espera uma query complexa de TLDs terminar.

---

## 8. Análise de Riscos e Impactos

A migração de um ecossistema síncrono para assíncrono em Python é uma das alterações mais profundas em um backend, trazendo riscos significativos que devem ser mitigados:

### 8.1. Riscos Técnicos (Loop de Eventos)
- **Bloqueio do Event Loop:** O maior risco é esquecer uma chamada síncrona (como `requests.get`, `time.sleep` ou um driver de DB síncrono) dentro de uma rota `async def`. Isso trava o loop de eventos para todos os usuários simultâneos, degradando a performance em vez de melhorá-la.
- **Race Conditions:** No modelo assíncrono, tarefas podem ser suspensas e retomadas. Se houver estado compartilhado globalmente (como variáveis de classe ou globais), podem ocorrer condições de corrida que não existiam no modelo síncrono clássico do WSGI.

### 8.2. Riscos de Banco de Dados
- **Gerenciamento de Transações:** A `AsyncSession` exige o uso explícito de `await session.commit()`. Esquecer um `await` pode deixar conexões abertas no pool (Connection Leaks) ou transações em aberto, levando ao estouro do limite de conexões do PostgreSQL.
- **Lazy Loading:** Atributos de modelos SQLAlchemy configurados como `lazy="select"` (padrão) falharão ao serem acessados fora do contexto da query original se não forem carregados via `joinedload` ou `selectinload`. Isso causará erros de `MissingGreenlet` em tempo de execução.

### 8.3. Riscos Operacionais e de Integração
- **Bibliotecas Incompatíveis:** Algumas bibliotecas de terceiros usadas no projeto (ex: `python-whois`, `geoip2`, `imagehash`) são puramente síncronas. Elas **não** podem ser chamadas diretamente em rotas assíncronas sem o uso de `run_in_executor` (threads), sob risco de travar o servidor.
- **Estabilidade dos Testes:** Testes existentes baseados em `pytest` sem o plugin `pytest-asyncio` ou que utilizam mocks síncronos para o banco de dados precisarão ser integralmente reescritos.

### 8.4. Curva de Aprendizado e Debugging
- **Stack Traces Complexas:** O rastreamento de erros em código assíncrono é mais difícil de ler, pois o loop de eventos intercalando tarefas torna a sequência temporal menos óbvia nos logs.
- **Deadlocks Silenciosos:** Erros de concorrência podem ser intermitentes e difíceis de reproduzir em ambiente de desenvolvimento, aparecendo apenas sob carga em produção.

---

## 9. Conclusão e Recomendação (proposta original)

A refatoração não é apenas uma melhoria estética, mas uma necessidade de infraestrutura para a saúde a longo prazo do Observador de Domínios. A recomendação original é iniciar a migração pelo módulo de **Auth** (menor risco) e avançar imediatamente para o de **Similarity** (maior ganho de performance).

> **Atenção:** esta conclusão é a tese original do documento. A Seção 10 a seguir traz uma revisão posterior que **diverge** desta recomendação. As duas estão preservadas intencionalmente para que a decisão final seja consciente do contraponto.

---

## 10. Revisão Estratégica (2026-04-27) — contraponto

Esta seção foi adicionada em revisão posterior. Não invalida as Seções 1-9, mas oferece um contraponto baseado em verificação direta do código atual.

### 10.1. Veredito da revisão: NÃO executar agora
A refatoração é conceitualmente válida, mas **prematura** dado o estado atual do produto e do código. Recomenda-se adiar até existirem métricas que justifiquem o custo.

### 10.2. Por que adiar (contraponto às Seções 7 e 9)
1. **Gargalo provavelmente não está nas rotas REST.** O trabalho pesado do produto (ingestão CZDS/OpenIntel, similarity scan, assessment, enrichment, health checks) já está isolado em `app/worker/` — fora do ciclo HTTP. Migrar rotas para async não acelera nada disso. O ROI verdadeiro estaria em uma fila de jobs (Celery/arq/dramatiq) para os workers, que é uma discussão diferente.
2. **Sem gargalo demonstrado.** A Seção 7 fala em "gargalo invisível" e "esgotamento de threads", mas não há baseline de p95/CPU/threadpool em produção. O produto ainda está pré-lançamento (auth, billing, similarity em construção). FastAPI executa rotas `def` em threadpool: a stack atual (psycopg2 + `SessionLocal`) suporta facilmente o volume esperado de PMEs sem degradar.
3. **Custo desproporcional ao benefício.** 88-89 endpoints + 13 repositórios + camada de serviços + retrabalho de testes representam semanas de trabalho transversal, congelando o roadmap de features críticas (auth/billing) sem entregar valor visível ao usuário.
4. **A "preocupação alta" da Seção 7 é argumentativa, não medida.** Frases como "tempo de resposta aumentará exponencialmente sob carga moderada" são plausíveis, mas o limite real do threadpool padrão do AnyIO (~40 threads) só é atingido com volume real significativo — que ainda não existe.

### 10.3. Quando reabrir esta spec
Reabrir quando **pelo menos um** dos critérios for atendido:
- Telemetria mostrando p95 de latência alto em rotas REST com CPU do backend baixo (= espera por I/O nas rotas, não nos workers).
- Volume real de tráfego concorrente acima de ~200 req/s sustentadas.
- Auth + billing + similarity estáveis em produção, com base de usuários pagantes ativa.
- Necessidade comprovada de WebSockets / Server-Sent Events (que exigem async nativamente).

### 10.4. Alternativas com melhor ROI no curto prazo
- **Async pontual e cirúrgico:** apenas em rotas que fazem chamadas HTTP externas lentas (Stripe, Resend, APIs de terceiros), usando o `httpx.AsyncClient` que já está no `pyproject.toml`. Não exige migrar repositórios nem driver de DB.
- **Fila de jobs para workers:** se o objetivo real é escalar processamento, mover os módulos de `app/worker/` para uma fila gerenciada (arq + Redis, por exemplo) entrega muito mais que async nas rotas REST.
- **Reforçar Repository/Service Layer mantendo síncrono:** o objetivo arquitetural ("remover lógica de DB das rotas") da Seção 1 e o problema das "6 rotas críticas com `db.query` direto" da Seção 7.1 podem ser resolvidos **sem** migrar para async. É o mesmo Clean Architecture, custo bem menor, sem risco de event loop.
- **Eliminar `time.sleep()` e `httpx.Client` síncrono em código compartilhado:** ponto válido da Seção 7.1 e que pode ser corrigido isoladamente, sem migração global.

### 10.5. Se mesmo assim for executado
Pré-requisitos mínimos antes de iniciar:
- Suite de testes de integração cobrindo as rotas críticas (auth, billing, ingestion). Sem isso, regressões silenciosas são quase certas.
- Plano de migração das libs síncronas (`python-whois`, `geoip2`, `imagehash`): wrapper único com `asyncio.to_thread` e proibição lint-checada de chamada direta em código async.
- Métrica de baseline (latência p50/p95/p99 por rota) capturada **antes** da migração, para validar que houve ganho real ao final.

---

## 11. Embasamento para Decisão Futura

Esta seção documenta **sinais objetivos**, **ordens de grandeza** e **anti-sinais** para evitar refatorar por modismo. Use isto quando reabrir a discussão.

### 11.1. Como FastAPI realmente trata rotas `def`
FastAPI **não bloqueia o event loop** quando uma rota é `def` (síncrona): ele a executa em um threadpool gerenciado pelo Starlette/AnyIO (default ~40 threads). O bloqueio só acontece se uma rota `async def` chamar código síncrono pesado **sem** `run_in_executor`/`asyncio.to_thread`.

**Implicação prática:** rotas `def` com `psycopg2` hoje servem requisições paralelas via threads. O ganho de async é **maior throughput por processo** (1 thread principal vs. ~40), não "destravar" requests. Para a escala de PMEs, o threadpool sobra.

### 11.2. Sinais POSITIVOS — quando async passa a valer a pena
Reabrir esta spec se **dois ou mais** dos sinais abaixo forem reais (não hipotéticos):

| Sinal | Como medir | Limiar de ação |
|---|---|---|
| Threadpool saturando | Métrica `anyio.to_thread` ocupação ou logs de timeout em rotas | >70% utilização sustentada |
| Latência p95 alta com CPU baixa | Prometheus/Grafana ou APM (Sentry, Datadog) | p95 >500ms com CPU <40% |
| Conexões DB no limite | `pg_stat_activity` no Postgres | >80% do `max_connections` |
| Volume de tráfego | Req/s no load balancer | >200 req/s sustentadas |
| Necessidade de streaming | WebSockets, SSE, long polling exigidos por feature | Spec de produto pedindo |
| Chamadas externas serializadas | Rota faz N HTTP calls que poderiam ser paralelas | Latência somada >1s evitável |

### 11.3. Anti-sinais — NÃO usar como justificativa
Estes argumentos aparecem com frequência mas não justificam a migração isoladamente:
- "É o padrão moderno do FastAPI." — Padrão ≠ obrigatório. FastAPI suporta `def` oficialmente.
- "Async é mais rápido." — Falso para CPU-bound; verdadeiro só para I/O-bound sob concorrência alta.
- "SQLAlchemy 2.0 é melhor." — Verdade, mas o estilo `select()` 2.0 funciona **igualmente em sync**. Você pode migrar para o estilo 2.0 **sem** trocar para `AsyncSession`.
- "asyncpg é mais rápido que psycopg2." — Em microbenchmarks isolados sim; em rota real com ORM a diferença some.
- "Vamos precisar disso quando crescer." — YAGNI. Refatore quando o crescimento for real, não previsto.

### 11.4. Ordens de grandeza — custo estimado
Baseado no estado atual do código (verificado 2026-04-27):

| Item | Volume | Esforço estimado |
|---|---|---|
| Endpoints `def` → `async def` | 88-89 | 1-2 dev-dias |
| Repositórios (sync → async + select 2.0) | 13 | 5-8 dev-dias |
| Serviços (propagar await) | ~15 arquivos | 2-3 dev-dias |
| Wrappers para libs síncronas (whois/geoip2/imagehash) | 3 libs | 1 dev-dia |
| Reescrita de testes | depende da cobertura atual | 3-5 dev-dias |
| Estabilização (bugs MissingGreenlet, lazy load, deadlocks) | imprevisível | 3-7 dev-dias |
| **Total realista (1 dev experiente)** | | **15-25 dev-dias** |

Adicione 30-50% se o dev for novo em async Python. Adicione bugs em produção pós-deploy ao orçamento mental.

### 11.5. Estratégia de migração incremental sugerida
Caso a decisão futura seja "fazer", **não** faça big bang. Ordem recomendada:

1. **Fase 0 — Telemetria (1 semana):** instrumentar p50/p95/p99 por rota, ocupação de threadpool, conexões DB. Sem baseline, "ganhamos performance" é fé, não engenharia.
2. **Fase 1 — Setup dual (2-3 dias):** introduzir `async_engine` + `get_async_db` **convivendo** com o síncrono. Zero rotas migradas ainda. Smoke test.
3. **Fase 2 — Piloto (1 router):** escolher o router com **menor** acoplamento (provavelmente `tools.py` ou `monitored_brands.py`). Migrar repos+serviços+rotas dele. Rodar 1 semana em produção. Comparar métricas.
4. **Fase 3 — Decisão GO/NO-GO:** se a Fase 2 mostrou ganho mensurável, continuar. Se não, **reverter e parar**. Documentar aprendizado.
5. **Fase 4 — Roll-out por domínio:** auth → billing → similarity → ingestion. Um por sprint, com janela de soak.
6. **Fase 5 — Limpeza:** remover `psycopg2`, `get_db` síncrono, código duplicado.

### 11.6. Pegadinhas específicas deste projeto
Mapeadas a partir do código atual — anote para não tropeçar quando for fazer:

- **`app/worker/*`** roda fora do request cycle. **Não migre os workers para async sem reavaliar** — eles podem se beneficiar mais de uma fila (arq/Celery) do que de async puro.
- **`python-whois`** faz chamada de rede síncrona com timeout próprio. Em código async precisa ir para `asyncio.to_thread` e respeitar timeout do loop, não da lib.
- **`geoip2`** lê arquivo MaxMind do disco. Em async, abrir uma vez no startup (singleton) e reutilizar — não abrir por request.
- **`imagehash`** é CPU-bound (PIL + numpy). Async não ajuda; se virar gargalo, vai para process pool, não thread pool.
- **`alembic`**: migrations rodam síncronas. Não precisa migrar Alembic — manter `psycopg2` apenas para o env de migration é OK.
- **Pool de conexões:** pool size atual é 5+10. Async geralmente quer pool maior (20-50) porque cada coroutine pode segurar uma conexão. Recalibrar.
- **`pool_pre_ping=True`** existe hoje. Em `asyncpg` o equivalente é `pool_pre_ping` ou usar `NullPool` com PgBouncer — decidir cedo.
- **`time.sleep()` e `httpx.Client` síncrono em `generate_brand_seeds.py`** (apontado na Seção 7.1) — corrigir **independentemente** desta migração; é um bug latente mesmo no modelo síncrono se o código for chamado de uma rota.

### 11.7. Critério de "pronto para reabrir"
Marque esta spec como acionável quando **todos** abaixo forem verdadeiros:

- [ ] Auth, billing e similarity em produção há ≥30 dias sem incidentes críticos.
- [ ] Telemetria de latência por rota e ocupação de threadpool em produção.
- [ ] Pelo menos 2 sinais positivos da Seção 11.2 confirmados com dados.
- [ ] Cobertura de testes de integração ≥60% nas rotas a migrar.
- [ ] Janela de roadmap de produto que comporte 3-4 semanas sem feature nova crítica.
- [ ] Decisão tomada sobre fila de jobs para workers (ortogonal, mas não conflitar).

Se algum item estiver "não", o ganho esperado não justifica o risco. Volte aqui em 3 meses.

---
**Nota:** Esta especificação serve como guia técnico para futuras implementações. As Seções 1-9 representam a tese original (executar a migração); as Seções 10-11 representam a revisão posterior (adiar com critérios objetivos). A decisão final cabe ao mantenedor, com ambos os lados documentados.
