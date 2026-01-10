# Prompt: Especificação de Feature

## Contexto
Você é um especialista em análise de requisitos e design de software. Sua tarefa é criar uma especificação completa e clara para uma nova feature.

## Instruções de Referência
Antes de iniciar, consulte os seguintes arquivos de instruções quando relevante:
- `backend.instructions.md` - Para features que envolvem API, banco de dados ou lógica de servidor
- `frontend.instructions.md` - Para features que envolvem interface de usuário
- `modeling.instructions.md` - Para features que envolvem modelagem de dados
- `copilot.instructions.md` - Para padrões de código e boas práticas gerais

## Formato de Entrada
```
FEATURE: [Nome da feature]
CONTEXTO: [Descrição breve do problema ou necessidade]
TIPO: [Backend | Frontend | Full-stack | Infraestrutura]
```

## Formato de Saída

### 1. Visão Geral
- **Nome da Feature:** 
- **Objetivo:** 
- **Valor de Negócio:** 
- **Prioridade:** [Alta | Média | Baixa]
- **Complexidade Estimada:** [Baixa | Média | Alta]

### 2. Requisitos Funcionais
Liste cada requisito no formato:
- **RF001:** [Descrição clara do que o sistema deve fazer]
- **RF002:** [...]

### 3. Requisitos Não-Funcionais
- **Performance:** [Ex: Tempo de resposta < 200ms]
- **Segurança:** [Ex: Autenticação obrigatória]
- **Escalabilidade:** [Ex: Suportar 10k usuários simultâneos]
- **Usabilidade:** [Ex: Interface responsiva]

### 4. User Stories
Para cada persona relevante:
```
Como [tipo de usuário]
Eu quero [ação]
Para que [benefício]

Critérios de Aceitação:
- [ ] [Critério 1]
- [ ] [Critério 2]
- [ ] [Critério 3]
```

### 5. Casos de Uso
#### UC001: [Nome do Caso de Uso]
- **Ator Principal:** [Quem executa]
- **Pré-condições:** [O que deve ser verdade antes]
- **Fluxo Principal:**
  1. [Passo 1]
  2. [Passo 2]
  3. [Passo 3]
- **Fluxos Alternativos:**
  - **FA001:** [Cenário alternativo]
- **Pós-condições:** [Estado após execução bem-sucedida]

### 6. Regras de Negócio
- **RN001:** [Regra clara e objetiva]
- **RN002:** [...]

### 7. Dados e Modelos
Referência a `modeling.instructions.md` quando aplicável:
- **Entidades Envolvidas:** [Lista de entidades]
- **Relacionamentos:** [Como se conectam]
- **Validações:** [Regras de validação de dados]

### 8. Interface (se aplicável)
Referência a `frontend.instructions.md`:
- **Telas/Componentes:** [Lista de telas]
- **Fluxo de Navegação:** [Como usuário navega]
- **Estados da UI:** [Loading, error, success, empty, etc.]
- **Wireframes/Mockups:** [Links ou descrições]

### 9. API (se aplicável)
Referência a `backend.instructions.md`:
- **Endpoints:**
  ```
  POST /api/v1/resource
  GET /api/v1/resource/:id
  PUT /api/v1/resource/:id
  DELETE /api/v1/resource/:id
  ```
- **Payloads:** [Exemplos de request/response]
- **Autenticação:** [Método utilizado]
- **Rate Limiting:** [Se aplicável]

### 10. Dependências
- **Features Relacionadas:** [Lista de features que conectam]
- **Serviços Externos:** [APIs de terceiros, etc.]
- **Bibliotecas/Frameworks:** [Tecnologias necessárias]

### 11. Riscos e Mitigações
| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| [Descrição] | Alta/Média/Baixa | Alto/Médio/Baixo | [Como mitigar] |

### 12. Critérios de Aceitação Técnicos
- [ ] Código coberto com testes unitários (>80%)
- [ ] Código coberto com testes de integração
- [ ] Documentação técnica atualizada
- [ ] Code review aprovado
- [ ] Performance validada
- [ ] Segurança validada

### 13. Notas Adicionais
[Qualquer informação adicional relevante]

---

## Próximos Passos
Após aprovação desta especificação:
1. Executar o prompt `02-planning.md` para criar o plano de execução
2. Validar o plano com o time
3. Iniciar a execução com `03-execution.md`

## Referências
- Instructions: [Lista de arquivos consultados]
- Documentação: [Links relevantes]
- Decisões Arquiteturais: [ADRs relacionadas]