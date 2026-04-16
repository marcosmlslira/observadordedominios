# Especificação Técnica — CertStream Multi‑TLD com Política por Interface

## 1. Objetivo

Permitir que a ingestão `CertStream`:

1. ingira **todos os TLDs** observados no stream (não apenas `.br`);
2. respeite rigorosamente o estado **ativo/inativo** configurado na interface admin (`/admin/ingestion/certstream`);
3. cadastre automaticamente TLDs novos na política de ingestão para aparecerem na interface;
4. crie partições sob demanda para TLDs novos quando necessário;
5. opere de forma resiliente com concorrência de escrita com outras ingestões.

---

## 2. Contexto Atual (As-Is)

### 2.1 Backend

- O worker `ct_ingestor` roda continuamente e faz flush em lotes via `ingest_ct_batch`.
- O pipeline de normalização `normalize_ct_domains` usa `filter_suffix="br"` por padrão.
- O cliente `CertStreamClient` filtra por sufixos e, sem sufixo explícito, cai para `[".br"]`.
- A política `ingestion_tld_policy` existe e já sustenta ativo/inativo por `source + tld`.
- A criação de partição é dinâmica (`ensure_partition`) com `lock_timeout=1ms`.

### 2.2 Interface

- A tela de configuração já permite:
  - listar TLDs por source,
  - ativar/desativar individualmente,
  - ativar/desativar em massa.
- Para `certstream`, o texto indica stream contínuo e cron aplicando ao batch `crt.sh`.

### 2.3 Gap principal

Mesmo com política genérica no banco/UI, o pipeline de CertStream permanece com viés `.br` e o pré-filtro usa extração simplificada (`último label`), o que não representa corretamente TLDs multinível (`com.br`, `net.br`, etc.).

---

## 3. Escopo

## 3.1 Em escopo

- CertStream ingestindo qualquer TLD válido recebido.
- Aplicação de política `ingestion_tld_policy` por TLD efetivo (ex.: `com.br`, `co.uk`, `app`).
- Descoberta automática de TLD novo para `source=certstream`.
- Criação automática de partição por TLD quando ausente.
- Ajustes de robustez para concorrência e falhas transitórias de lock.
- Ajustes de testes unitários/integrados.

## 3.2 Fora de escopo

- Mudanças visuais grandes na UI.
- Mudanças de design system.
- Migração de arquitetura de particionamento (ex.: hash/range).
- Alterações de fluxo de CZDS/OpenINTEL além do necessário para convivência.

---

## 4. Requisitos Funcionais

## RF-01 — Captura multi‑TLD no stream

O CertStream deve aceitar eventos para qualquer TLD, sem filtro hardcoded `.br` no caminho de ingestão.

## RF-02 — Normalização sem restrição fixa de sufixo

No fluxo de CertStream, a normalização deve:

- extrair `registered_domain` e `effective_tld` via PSL (`tldextract`);
- deduplicar por `(name, tld)`;
- não descartar domínios por não terminarem em `.br`.

## RF-03 — Política por TLD efetivo

Antes de persistir no `domain`, cada item normalizado deve consultar política por `source='certstream'` e **tld efetivo completo**.

Exemplos:

- `banco.com.br` consulta `certstream/com.br`;
- `brand.co.uk` consulta `certstream/co.uk`;
- `example.app` consulta `certstream/app`.

## RF-04 — Auto-discovery de TLD novo

Se `certstream/<tld>` não existir em `ingestion_tld_policy`, deve ser criado automaticamente com:

- `is_enabled = true` (default permissivo);
- `priority = null` (não aplicável ao stream contínuo).

Isso garante que o TLD apareça na interface e possa ser desativado pelo operador.

## RF-05 — Respeito imediato ao toggle da interface

Ao desativar `certstream/<tld>` na UI:

- novos itens desse TLD devem parar de ser gravados no flush subsequente;
- domínios já gravados não devem ser removidos automaticamente.

Ao reativar:

- gravação volta no ciclo seguinte.

## RF-06 — Criação de partição on-demand

Para cada TLD habilitado presente no lote:

- garantir partição (`ensure_partition`) antes do `upsert`;
- se a partição já existir, seguir fluxo normal;
- se criação falhar por lock transitório, o TLD deve ser reprocessado em lote futuro.

## RF-07 — Convivência com outras ingestões

Quando CertStream e outra ingestão escreverem na mesma partição:

- não deve existir bloqueio global entre workers;
- o banco resolve concorrência por transação/lock de linha (`ON CONFLICT`);
- falhas pontuais de lock DDL não devem derrubar o worker inteiro.

---

## 5. Requisitos Não Funcionais

## RNF-01 — Resiliência

Falha de um TLD no flush não deve comprometer processamento dos demais TLDs do mesmo lote sempre que tecnicamente possível.

## RNF-02 — Observabilidade

Log estruturado por flush contendo no mínimo:

- `source`,
- `batch_size_raw`,
- `batch_size_normalized`,
- `batch_size_enabled`,
- `batch_size_disabled`,
- `tlds_seen`,
- `tlds_enabled`,
- `tlds_disabled`,
- `tlds_partition_retry`.

## RNF-03 — Performance

Manter throughput do stream com overhead mínimo por item, evitando consulta por domínio individual quando possível (cache curto por TLD no flush).

## RNF-04 — Segurança operacional

Sem `docker-compose`, sem libs fora da stack atual, sem mudanças de responsabilidade de camadas.

---

## 6. Desenho Técnico (To-Be)

## 6.1 Fluxo de ingestão CertStream

1. **Receive**: worker recebe SAN domains do websocket.
2. **Normalize**: transforma em `(name, tld, label)` sem filtro `.br`.
3. **Policy stage**:
   - resolve estado por `tld` para `source='certstream'`;
   - cria linha faltante (default enabled=true);
   - separa habilitados vs desabilitados.
4. **Partition stage**:
   - garante partição para TLDs habilitados.
5. **Persist stage**:
   - `bulk_upsert_multi_tld` apenas dos habilitados.
6. **Metrics stage**:
   - atualiza métricas de run (`seen/inserted`) e logs de filtragem.

## 6.2 Regra de TLD efetivo

`tld` da política deve ser o mesmo `suffix` do PSL (`tldextract.suffix`), nunca o último label simples.

## 6.3 Estratégia para locks de partição

- manter `lock_timeout=1ms` para não enfileirar DDL;
- se falhar criação de partição para um TLD:
  - registrar warning com contexto;
  - pular apenas aquele TLD no flush atual;
  - continuar com os demais;
  - retry natural em próximos lotes.

## 6.4 Estratégia de policy lookup

- montar mapa por `set(tlds_in_batch)` em vez de consulta por domínio;
- para TLD não encontrado, `ensure_tld(certstream, tld, is_enabled=True)`;
- cache em memória por flush para reduzir round-trips.

---

## 7. Impacto em Componentes

## 7.1 Backend (alterações esperadas)

- `backend/app/services/domain_normalizer.py`
  - suportar fluxo de normalização sem filtro fixo por sufixo para CertStream.
- `backend/app/services/use_cases/ingest_ct_batch.py`
  - política por TLD efetivo no contexto `source='certstream'`;
  - fallback atual `.br` removido para CertStream.
- `backend/app/worker/ct_ingestor.py`
  - remover dependência de extração simplificada (`_extract_tld` por último label) no gating.
- `backend/app/infra/external/certstream_client.py`
  - permitir modo sem filtro restritivo (captura ampla) ou filtro dinâmico de política sem default forçado `.br`.
- `backend/app/repositories/domain_repository.py`
  - preservar `ensure_partition` e ajustar tratamento para não abortar lote inteiro por um único TLD.

## 7.2 Banco de dados

- Sem mudança obrigatória de schema para funcionalidade mínima.
- Opcional: migration para índices auxiliares/metadados de observabilidade de TLDs descobertos.

## 7.3 Frontend

- Sem breaking change de API.
- A tabela `/admin/ingestion/certstream` passa a crescer dinamicamente conforme TLDs descobertos.

---

## 8. Compatibilidade e Migração

## 8.1 Backward compatibility

- Endpoints atuais de `ingestion config` e `tld-policy` permanecem.
- `cron` de `certstream` continua representando apenas o batch `crt.sh`.

## 8.2 Estratégia de rollout

1. Deploy backend com suporte multi‑TLD e policy efetiva.
2. Monitorar logs de criação de partição e volume de novos TLDs por 24–72h.
3. Ajustar TLDs na interface conforme necessidade operacional.

## 8.3 Rollback

- rollback de código para comportamento anterior;
- dados já ingeridos/partições criadas permanecem (sem impacto de integridade).

---

## 9. Critérios de Aceite (UAT)

## CA-01

Dado `certstream/com` ativo, quando chegar domínio `foo.com`, então `foo.com` deve ser persistido.

## CA-02

Dado `certstream/com` inativo, quando chegar `bar.com`, então não deve ser persistido.

## CA-03

Dado que `certstream/xyzabc` não existe, quando chegar `brand.xyzabc`, então:

- linha `certstream/xyzabc` deve ser criada na policy com `is_enabled=true`;
- domínio deve ser processado (salvo se outro bloqueio ocorrer).

## CA-04

Ao desativar um TLD na UI, o efeito deve ocorrer sem reiniciar worker.

## CA-05

Quando CertStream e CZDS/OpenINTEL gravarem no mesmo TLD simultaneamente, não deve ocorrer falha sistêmica do worker.

## CA-06

Quando criação de partição falhar por lock transitório, o worker deve seguir com outros TLDs e registrar retry posterior.

## CA-07

TLD multinível (`com.br`, `co.uk`) deve respeitar exatamente sua própria policy, sem colapsar para `br`/`uk`.

---

## 10. Plano de Testes

## 10.1 Unitários

- normalização CertStream sem filtro `.br`;
- mapeamento correto de TLD efetivo multinível;
- auto-criação de policy para TLD novo;
- bloqueio por `is_enabled=false`;
- não regressão para `.br`.

## 10.2 Integração (DB real)

- ingestão concorrente em mesmo TLD com `ON CONFLICT`;
- criação de partição dinâmica com corrida de concorrência;
- falha de lock em um TLD sem derrubar flush completo.

## 10.3 E2E funcional (admin)

- TLD novo aparece na tela do source `certstream`;
- toggle ativo/inativo altera comportamento real de persistência.

---

## 11. Riscos e Mitigações

## Risco 1 — Explosão de partições

Com “todos TLDs”, número de partições pode crescer significativamente.

Mitigação:

- monitorar contagem de partições e tempo de planejamento;
- revisar estratégia de housekeeping/limites operacionais;
- opcionalmente adicionar controles de admissão por política.

## Risco 2 — Carga maior de ingestão

Remoção do filtro `.br` amplia volume de eventos.

Mitigação:

- observar throughput de flush e latência de commit;
- ajustar `CT_BUFFER_FLUSH_SIZE` e `CT_BUFFER_FLUSH_SECONDS` se necessário.

## Risco 3 — Toggle não refletir instantaneamente

Mitigação:

- garantir consulta de policy por flush/lote (não cache longo sem invalidação).

---

## 12. Decisões de Produto/Operação

1. **Default para TLD novo**: `enabled=true`.
2. **Sem bloqueio global entre ingestões**: concorrência resolvida no banco.
3. **Persistência parcial por lote é aceitável**: TLD com lock transitório pode ficar para retry.

---

## 13. Checklist de Implementação

- [ ] remover filtro hardcoded `.br` do caminho CertStream;
- [ ] aplicar policy por TLD efetivo no lote;
- [ ] auto-criar `ingestion_tld_policy` para TLD novo de certstream;
- [ ] garantir partição por TLD habilitado;
- [ ] tornar flush resiliente por TLD (sem abortar lote inteiro);
- [ ] adicionar logs/contadores de enabled/disabled/retry;
- [ ] cobrir testes unitários + integração + e2e admin.

