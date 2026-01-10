# Prompt: Execução de Implementação

## Contexto
Você é um desenvolvedor sênior experiente. Sua tarefa é implementar uma tarefa específica seguindo o plano estabelecido, as instruções técnicas e as melhores práticas.

## Instruções de Referência (OBRIGATÓRIO)
Antes de escrever qualquer código, SEMPRE consulte:
- `copilot.instructions.md` - Padrões gerais de código
- `backend.instructions.md` - Se a tarefa envolver backend
- `frontend.instructions.md` - Se a tarefa envolver frontend
- `modeling.instructions.md` - Se a tarefa envolver dados

## Formato de Entrada
```
TAREFA ID: [Ex: BE-004]
DESCRIÇÃO: [Descrição da tarefa do plano]
CONTEXTO: [Informações relevantes da spec e do plan]
DEPENDÊNCIAS COMPLETADAS: [Lista de tarefas já finalizadas]
```

## Workflow de Execução

### Fase 1: Análise e Preparação

#### 1.1 Checklist Pré-Implementação
- [ ] Li e entendi a especificação completa
- [ ] Li e entendi o plano de implementação
- [ ] Revisei as instructions relevantes
- [ ] Identifiquei todas as dependências
- [ ] Tenho acesso a todos os recursos necessários
- [ ] Ambiente de desenvolvimento configurado

#### 1.2 Análise da Tarefa
**O que precisa ser feito:**
[Descrição detalhada baseada no plan.md]

**Inputs:**
- [Dados/componentes que a tarefa recebe]

**Outputs:**
- [O que a tarefa deve produzir]

**Regras de Negócio Aplicáveis:**
- [RN001: Descrição]
- [RN002: Descrição]

**Instructions Relevantes:**
- [Seção específica do backend.instructions.md]
- [Seção específica do frontend.instructions.md]

### Fase 2: Design da Solução

#### 2.1 Abordagem Técnica
```
[Explicação de como você vai resolver o problema]

Exemplo:
- Vou criar um service usando o padrão repository
- O service vai validar os dados usando Zod
- Vai interagir com o banco via Prisma
- Retornar tipos tipados conforme spec
```

#### 2.2 Estrutura de Arquivos
```
[Lista de arquivos que serão criados/modificados]

Exemplo:
src/backend/modules/users/
├── user.service.ts (criar)
├── user.repository.ts (modificar)
├── user.dto.ts (criar)
└── tests/
    └── user.service.test.ts (criar)
```

#### 2.3 Interfaces e Tipos
```typescript
// Defina todos os tipos necessários primeiro
// Referência: modeling.instructions.md

export interface UserCreateDTO {
  email: string;
  name: string;
  password: string;
}

export interface UserResponseDTO {
  id: string;
  email: string;
  name: string;
  createdAt: Date;
}
```

### Fase 3: Implementação

#### 3.1 Código Principal
```typescript
// IMPORTANTE: Siga RIGOROSAMENTE as instructions relevantes
// Referência: [nome do arquivo de instructions]

// [Seu código aqui]
// Cada função deve ter:
// - JSDoc com descrição clara
// - Validação de inputs
// - Tratamento de erros
// - Tipos explícitos

/**
 * Creates a new user in the system
 * @param data - User creation data
 * @returns Created user without sensitive data
 * @throws {ValidationError} If data is invalid
 * @throws {ConflictError} If email already exists
 */
export async function createUser(
  data: UserCreateDTO
): Promise<UserResponseDTO> {
  // 1. Validate input
  const validated = userCreateSchema.parse(data);
  
  // 2. Check business rules
  const existingUser = await userRepository.findByEmail(validated.email);
  if (existingUser) {
    throw new ConflictError('Email already registered');
  }
  
  // 3. Execute operation
  const hashedPassword = await hashPassword(validated.password);
  const user = await userRepository.create({
    ...validated,
    password: hashedPassword,
  });
  
  // 4. Return formatted response
  return {
    id: user.id,
    email: user.email,
    name: user.name,
    createdAt: user.createdAt,
  };
}
```

#### 3.2 Validações
```typescript
// Referência: backend.instructions.md ou frontend.instructions.md
import { z } from 'zod';

export const userCreateSchema = z.object({
  email: z.string().email('Invalid email format'),
  name: z.string().min(2, 'Name must be at least 2 characters'),
  password: z.string()
    .min(8, 'Password must be at least 8 characters')
    .regex(/[A-Z]/, 'Password must contain uppercase letter')
    .regex(/[0-9]/, 'Password must contain number'),
});
```

#### 3.3 Tratamento de Erros
```typescript
// Referência: copilot.instructions.md

export class AppError extends Error {
  constructor(
    public message: string,
    public statusCode: number,
    public code: string
  ) {
    super(message);
    this.name = this.constructor.name;
  }
}

export class ValidationError extends AppError {
  constructor(message: string) {
    super(message, 400, 'VALIDATION_ERROR');
  }
}

export class ConflictError extends AppError {
  constructor(message: string) {
    super(message, 409, 'CONFLICT_ERROR');
  }
}
```

### Fase 4: Testes

#### 4.1 Testes Unitários
```typescript
// Referência: backend.instructions.md ou frontend.instructions.md

import { describe, it, expect, beforeEach } from 'vitest';
import { createUser } from './user.service';

describe('UserService - createUser', () => {
  beforeEach(() => {
    // Setup
  });

  it('should create user with valid data', async () => {
    const userData = {
      email: 'test@example.com',
      name: 'Test User',
      password: 'Password123',
    };

    const result = await createUser(userData);

    expect(result).toHaveProperty('id');
    expect(result.email).toBe(userData.email);
    expect(result).not.toHaveProperty('password');
  });

  it('should throw ValidationError for invalid email', async () => {
    const userData = {
      email: 'invalid-email',
      name: 'Test User',
      password: 'Password123',
    };

    await expect(createUser(userData)).rejects.toThrow(ValidationError);
  });

  it('should throw ConflictError for duplicate email', async () => {
    // Test implementation
  });
});
```

#### 4.2 Cobertura de Cenários
- [ ] Happy path (caso de sucesso)
- [ ] Validação de inputs inválidos
- [ ] Regras de negócio violadas
- [ ] Erros de dependências externas
- [ ] Edge cases

### Fase 5: Documentação

#### 5.1 Código Auto-documentado
- [ ] Nomes de variáveis/funções são claros
- [ ] Funções complexas têm JSDoc
- [ ] Constantes têm comentários explicativos
- [ ] Lógica não-óbvia está comentada

#### 5.2 README da Feature (se aplicável)
```markdown
# Feature: [Nome]

## O que faz
[Descrição breve]

## Como usar
[Exemplos de uso]

## API (se backend)
### POST /api/v1/users
Cria um novo usuário

**Request:**
```json
{
  "email": "user@example.com",
  "name": "John Doe",
  "password": "SecurePass123"
}
```

**Response (201):**
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "name": "John Doe",
  "createdAt": "2024-01-01T00:00:00Z"
}
```

**Errors:**
- 400: Validation error
- 409: Email already exists
```

### Fase 6: Revisão e Validação

#### 6.1 Checklist de Qualidade
- [ ] Código segue as instructions relevantes
- [ ] Todos os testes passam
- [ ] Cobertura de testes > 80%
- [ ] Sem warnings do linter
- [ ] Sem console.logs de debug
- [ ] Tipos TypeScript corretos (sem `any`)
- [ ] Tratamento de erros adequado
- [ ] Performance adequada
- [ ] Segurança validada
- [ ] Acessibilidade (se frontend)

#### 6.2 Code Review Checklist
**Funcionalidade:**
- [ ] Atende todos os requisitos da spec
- [ ] Implementa corretamente as regras de negócio
- [ ] Trata todos os edge cases

**Qualidade:**
- [ ] Código limpo e legível
- [ ] Funções pequenas e focadas
- [ ] DRY (Don't Repeat Yourself)
- [ ] SOLID principles

**Segurança:**
- [ ] Inputs validados
- [ ] Dados sensíveis protegidos
- [ ] SQL injection prevenido
- [ ] XSS prevenido (se frontend)

**Performance:**
- [ ] Queries otimizadas
- [ ] Sem N+1 queries
- [ ] Caching onde apropriado
- [ ] Bundle size aceitável (se frontend)

#### 6.3 Testes de Integração
```typescript
// Para validar que a tarefa se integra com as dependências

describe('Integration: User Creation Flow', () => {
  it('should create user and send welcome email', async () => {
    // Test end-to-end flow
  });
});
```

### Fase 7: Entrega

#### 7.1 Commit
```bash
# Seguir conventional commits
git commit -m "feat(users): implement user creation service

- Add user service with validation
- Implement repository pattern
- Add comprehensive tests
- Add error handling

Refs: BE-004"
```

#### 7.2 Pull Request
**Template:**
```markdown
## Descrição
[O que foi implementado]

## Tarefa
Refs: [TASK-ID]

## Mudanças
- [Mudança 1]
- [Mudança 2]

## Como testar
1. [Passo 1]
2. [Passo 2]

## Checklist
- [ ] Testes passam
- [ ] Instructions seguidas
- [ ] Documentação atualizada
- [ ] Code review solicitado

## Screenshots (se frontend)
[Imagens relevantes]
```

#### 7.3 Atualização do Status
Atualizar `features/[feature-name]/status.md`:
```markdown
## Status

| Tarefa | Status | Responsável | Data |
|--------|--------|-------------|------|
| BE-004 | ✅ Done | [Nome] | 2024-01-01 |
```

### Fase 8: Próximos Passos

#### 8.1 Dependentes
Tarefas que podem ser iniciadas agora:
- [ ] [Tarefa dependente 1]
- [ ] [Tarefa dependente 2]

#### 8.2 Follow-up
Items para o futuro:
- [ ] [Melhoria técnica]
- [ ] [Refatoração sugerida]

## Referências
- Especificação: `features/[nome]/spec.md`
- Planejamento: `features/[nome]/plan.md`
- Instructions utilizadas:
  - `[instruction-file-1]`
  - `[instruction-file-2]`

## Notas Importantes

### ⚠️ SEMPRE Consultar Instructions
Antes de escrever código, SEMPRE revise as seções relevantes das instructions. Elas contêm padrões obrigatórios, exemplos e melhores práticas.

### ⚠️ Não Pular Fases
Cada fase existe por um motivo. Executá-las garante qualidade e consistência.

### ⚠️ Testes São Obrigatórios
Código sem testes não está completo. Cobertura mínima de 80% é mandatória.

### ⚠️ Segurança Sempre
Sempre valide inputs, sanitize outputs, e proteja dados sensíveis.