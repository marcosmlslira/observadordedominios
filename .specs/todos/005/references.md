# 005 — Referências

## Código existente relevante

### Frontend
- `frontend/components/ingestion/tld-metrics-table.tsx` — tabela atual de TLDs (sem coluna de prioridade, sem sort)
- `frontend/components/ingestion/tld-policy-table.tsx` — componente com inputs de prioridade (existe mas não usado na página)
- `frontend/components/ingestion/source-config-page.tsx` — página de configuração por motor
- `frontend/lib/types.ts:524` — interface `TldMetricsRow` (sem `priority`)
- `frontend/lib/types.ts:231` — interface `CzdsPolicyItem` (tem `priority`)
- `frontend/lib/types.ts:243` — interface `CzdsPolicyPatchRequest` (tem `priority?`)
- `frontend/lib/api.ts:107` — `ingestionApi.patchPolicy(tld, body)` → `PATCH /v1/czds/policy/{tld}`
- `frontend/lib/api.ts:110` — `ingestionApi.reorderPolicy(tlds[])` → `POST /v1/czds/policy/reorder`

### Backend
- `backend/app/api/v1/routers/czds_ingestion.py:163` — `PATCH /v1/czds/policy/{tld}` (aceita `priority`)
- `backend/app/api/v1/routers/czds_ingestion.py:184` — `POST /v1/czds/policy/reorder`
- `backend/app/schemas/czds_ingestion.py:132` — `CzdsPolicyPatchRequest` (campos opcionais: `is_enabled`, `priority`, `cooldown_hours`)
- `backend/app/worker/czds_ingestor.py:107` — query SQL de ordenação do ciclo de execução
- `backend/app/worker/czds_ingestor.py:56` — `_SIZE_THRESHOLD = 1_000_000`

## Ordenação atual do worker (czds_ingestor.py)
```sql
ORDER BY COALESCE(m.count, 999999999) ASC,  -- corpus size (desconhecido = último)
         p.priority ASC,                    -- prioridade manual
         p.tld ASC                          -- desempate alfabético
```

## Páginas afetadas
- `https://observadordedominios.com.br/admin/ingestion/czds`
- `https://observadordedominios.com.br/admin/ingestion/openintel`
- `https://observadordedominios.com.br/admin/ingestion/certstream` (apenas sort visual)

## Modos de ordenação propostos
| Modo | Label UI | Ordenação |
|------|----------|-----------|
| `corpus_first` | "Corpus (padrão)" | `corpus_size ASC → priority ASC → tld ASC` |
| `priority_first` | "Prioridade manual" | `priority ASC → corpus_size ASC → tld ASC` |
| `alphabetical` | "Alfabética" | `tld ASC` |
