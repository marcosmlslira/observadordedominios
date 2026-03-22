# Gestão de Refinamentos e Planos (`.specs/todos`)

Este diretório centraliza o planejamento executável de cada refinamento técnico.

## Convenção de numeração

- Cada novo refinamento recebe um número sequencial de 3 dígitos: `001`, `002`, `003`...
- Cada item possui sua própria pasta: `.specs/todos/<NNN>/`

## Estrutura padrão por item

```text
.specs/todos/<NNN>/
  plan.md            # plano técnico de implementação (tarefas por fase)
  references.md      # links e decisões do refinamento
  status.md          # status atual, dono, datas e checklist
```

## Arquivo geral de controle

- O arquivo `.specs/todos/_registry.md` é a fonte principal de ordem e status.
- Sempre que um novo refinamento for criado:
  1. adicionar nova linha no `_registry.md`;
  2. criar pasta numerada;
  3. preencher `plan.md`, `references.md` e `status.md`.

## Regras de atualização

- Status permitidos: `todo`, `in_progress`, `blocked`, `done`.
- Atualizar `_registry.md` e `status.md` no mesmo commit/alteração.
- Não reutilizar números já existentes.
