# 005 — Ordenação e Prioridade nas Páginas de Ingestão

## Contexto

Cada motor de ingestão (CZDS, OpenINTEL, CertStream, etc.) tem sua própria lógica de
ordenação de execução: atualmente o CZDS ordena por `corpus_size ASC → priority ASC → tld ASC`.
Essa ordenação não está visível nem configurável na interface admin.

O usuário precisa:
1. Ver e editar a **prioridade numérica** de cada TLD inline na tabela
2. Escolher o **modo de ordenação** do motor (ex: corpus-first vs priority-first)
3. Poder **ordenar a tabela visualmente** por qualquer coluna
4. Ver a tabela ordenada por padrão conforme a **ordem real de execução** do motor

---

## Escopo

### Feature 1 — Edição de prioridade por TLD (inline)

Adicionar coluna "Prioridade" à tabela de TLDs em cada página de ingestão que suporte o conceito.

**Comportamento:**
- Input numérico inline na coluna "Prioridade"
- Persiste ao `onBlur` (PATCH na API)
- Valores menores = executam primeiro
- Indicação visual quando o valor difere do padrão (ex: `100`)

**Motores afetados:** CZDS (suportado), OpenINTEL (a avaliar), CertStream (N/A — stream contínuo)

**API já disponível:** `PATCH /v1/czds/policy/{tld}` aceita `{ priority: number }`

---

### Feature 2 — Modo de ordenação por motor

Cada página de ingestão terá um seletor de modo de ordenação, persistido por motor no backend.

**Modos propostos para CZDS:**
| Modo | Ordenação SQL | Descrição |
|------|--------------|-----------|
| `corpus_first` (padrão atual) | `corpus_size ASC → priority ASC → tld ASC` | Menores TLDs primeiro |
| `priority_first` | `priority ASC → corpus_size ASC → tld ASC` | Prioridade manual domina |
| `alphabetical` | `tld ASC` | Ordem alfabética pura |

**UI:** select/segmented control no topo da página, próximo ao cron config.

**Backend necessário:**
- Nova tabela `czds_ingestor_settings` (ou coluna em tabela existente): `ordering_mode VARCHAR`
- Endpoint `PATCH /v1/czds/settings` + `GET /v1/czds/settings`
- Worker lê o modo antes de cada ciclo

---

### Feature 3 — Ordenação visual da tabela por coluna

A tabela de TLDs suporta clique no cabeçalho para ordenar por qualquer coluna disponível.

**Colunas clicáveis:** TLD, Prioridade, Ativo, Última OK, Duração, Inseridos, Falhas
**Ordenação padrão:** espelha a ordem real de execução (ver Feature 2 — modo ativo)
**Estado da ordenação:** local (client-side), não persiste entre reloads

**Comportamento:**
- Clique na coluna: ordena ASC
- Segundo clique: ordena DESC
- Terceiro clique: volta ao padrão (ordem de execução)
- Ícone de seta no cabeçalho indica coluna ativa e direção

---

## Arquitetura de Implementação

### Backend

```
app/
├── models/
│   └── czds_ingestor_settings.py        # nova tabela (ou coluna em czds_tld_policy)
├── schemas/
│   └── czds_ingestion.py                # + CzdsSettingsResponse, CzdsSettingsPatchRequest
├── repositories/
│   └── czds_policy_repository.py        # + get_settings(), patch_settings()
└── api/v1/routers/
    └── czds_ingestion.py                # + GET /settings, PATCH /settings
```

Migração Alembic necessária para a tabela/coluna de settings.

### Frontend

```
frontend/
├── lib/
│   ├── types.ts                         # + CzdsSettings, ordering_mode type
│   └── api.ts                           # + ingestionApi.getSettings(), patchSettings()
└── components/ingestion/
    ├── tld-metrics-table.tsx            # + coluna Prioridade + sort por coluna
    ├── source-config-page.tsx           # + load settings, pass to table + mode selector
    └── ordering-mode-selector.tsx       # novo: select/segmented control
```

---

## Critérios de Aceite

- [ ] Coluna "Prioridade" visível e editável inline em `/admin/ingestion/czds`
- [ ] Mudança de prioridade persiste no backend imediatamente ao sair do campo
- [ ] Seletor de modo de ordenação disponível no topo da página (por motor)
- [ ] Modo persiste entre sessões (salvo no backend)
- [ ] Tabela ordenada por padrão conforme modo de execução ativo
- [ ] Clique em cabeçalho ordena a tabela visualmente (ASC → DESC → padrão)
- [ ] Ícone de direção visível na coluna ativa
- [ ] Colunas sem sentido de ordenação (ex: sparkbar de runs) não são clicáveis
- [ ] Mobile: tabela com scroll horizontal funciona corretamente

---

## Dependências

- `001` (CZDS Ingestão) deve estar estável (está `in_progress`)
- Backend CZDS policy PATCH já disponível — não é bloqueante para Feature 1

---

## Notas técnicas

- O modo de ordenação **não afeta a ingestão em tempo real** — só é lido no início de cada ciclo
- `priority` padrão é `100` para 1031 de 1121 TLDs — a UI deve indicar visualmente quando o valor é o padrão
- CertStream é stream contínuo — Features 1 e 2 não se aplicam; Feature 3 (sort visual) sim
- OpenINTEL: verificar se possui tabela equivalente a `czds_tld_policy` antes de implementar Features 1 e 2
