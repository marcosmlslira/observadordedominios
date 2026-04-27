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
| `backend/app/repositories/similarity_repository.py` | Repositório gigante (>40k linhas) que precisa de refatoração 2.0. | Média |
| `backend/app/infra/db/session.py` | Ponto central de falha se migrado incorretamente. | Crítica |

---

## 6. Análise de Riscos e Impactos

A migração de um ecossistema síncrono para assíncrono em Python é uma das alterações mais profundas em um backend, trazendo riscos significativos que devem ser mitigados:

### 6.1. Riscos Técnicos (Loop de Eventos)
- **Bloqueio do Event Loop:** O maior risco é esquecer uma chamada síncrona (como `requests.get`, `time.sleep` ou um driver de DB síncrono) dentro de uma rota `async def`. Isso trava o loop de eventos para todos os usuários simultâneos, degradando a performance em vez de melhorá-la.
- **Race Conditions:** No modelo assíncrono, tarefas podem ser suspensas e retomadas. Se houver estado compartilhado globalmente (como variáveis de classe ou globais), podem ocorrer condições de corrida que não existiam no modelo síncrono clássico do WSGI.

### 6.2. Riscos de Banco de Dados
- **Gerenciamento de Transações:** A `AsyncSession` exige o uso explícito de `await session.commit()`. Esquecer um `await` pode deixar conexões abertas no pool (Connection Leaks) ou transações em aberto, levando ao estouro do limite de conexões do PostgreSQL.
- **Lazy Loading:** Atributos de modelos SQLAlchemy configurados como `lazy="select"` (padrão) falharão ao serem acessados fora do contexto da query original se não forem carregados via `joinedload` ou `selectinload`. Isso causará erros de `MissingGreenlet` em tempo de execução.

### 6.3. Riscos Operacionais e de Integração
- **Bibliotecas Incompatíveis:** Algumas bibliotecas de terceiros usadas no projeto (ex: `python-whois`, `geoip2`, `imagehash`) são puramente síncronas. Elas **não** podem ser chamadas diretamente em rotas assíncronas sem o uso de `run_in_executor` (threads), sob risco de travar o servidor.
- **Estabilidade dos Testes:** Testes existentes baseados em `pytest` sem o plugin `pytest-asyncio` ou que utilizam mocks síncronos para o banco de dados precisarão ser integralmente reescritos.

### 6.4. Curva de Aprendizado e Debugging
- **Stack Traces Complexas:** O rastreamento de erros em código assíncrono é mais difícil de ler, pois o loop de eventos intercalando tarefas torna a sequência temporal menos óbvia nos logs.
- **Deadlocks Silenciosos:** Erros de concorrência podem ser intermitentes e difíceis de reproduzir em ambiente de desenvolvimento, aparecendo apenas sob carga em produção.

---
**Nota:** Esta especificação serve como guia técnico para futuras implementações, visando alinhar o projeto aos padrões de mercado para aplicações FastAPI de alta performance.
