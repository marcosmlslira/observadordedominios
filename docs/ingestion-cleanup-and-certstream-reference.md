# Limpeza do Legado de Ingestão e Referência Abstrata de CertStream

Data: 2026-04-25  
Status: Fase 1 implementada (desligamento operacional + ocultação de UI/API ativa)

## 1) Diagnóstico do desvio de cron (causa-raiz)

### Sintoma observado
- Scheduler novo configurado para `01:00 UTC-3` (`04:00 UTC`) no módulo `ingestion`.
- UI em `/admin/ingestion` exibindo cron diferente.

### Causa-raiz
- O backend da tela de ingestão estava lendo cron de fontes legadas (valores de `settings.*_SYNC_CRON` e modelo antigo com `certstream/crtsh`), em vez de usar somente a configuração ativa do fluxo novo.
- Havia convivência de stacks/serviços legados (`ct_ingestor`, `certstream_server`, workers antigos por fonte) com o `ingestion_worker`, gerando sinais operacionais conflitantes para a observabilidade do Admin.

### Evidências técnicas (antes da limpeza)
- `backend/app/api/v1/routers/ingestion.py`: resumo/cycle-status com `certstream`/`crtsh` e cron por `settings`.
- `frontend/app/admin/ingestion/page.tsx`: filtros e matrizes com `certstream`/`crtsh`.
- `infra/stack.yml` e `infra/stack.dev.yml`: serviços `ct_ingestor` + `certstream_server` coexistindo com pipeline novo.

## 2) Inventário objetivo do que desabilitar por camada

## Infra
- Desativar `certstream_server` e `ct_ingestor`.
- Remover `czds_ingestor` e `openintel_ingestor` da stack de produção.
- Manter `ingestion_worker` como scheduler único diário.

## Backend (API/serviços)
- Não expor mais `certstream/crtsh` em:
  - `GET /v1/ingestion/summary`
  - `GET /v1/ingestion/cycle-status`
  - `GET /v1/ingestion/tld-status` (validação restrita a `czds|openintel`)
- Validar `source` apenas em `czds|openintel` na camada de config (`ingestion_config_service`).
- Encerrar automaticamente runs legados em execução (`certstream/crtsh`) no startup da API.

## Banco/config operacional
- `ingestion_source_config`: manter somente fontes ativas (`czds`, `openintel`).
- Encerrar runs legados `running` e preservar histórico para auditoria.
- Remover políticas operacionais de `certstream` em `ingestion_tld_policy`.

## Frontend
- Remover `certstream/crtsh` de filtros/listagens/cartões de saúde da página Admin Ingestion.
- Manter UI orientada apenas para `czds` e `openintel`.
- Remover semântica de “stream contínuo + cron crt.sh” do card de agendamento.

## Testes
- Atualizar testes de summary para aceitar apenas fontes ativas.
- Cobrir rejeição de `certstream` em `tld-status`.

## Docs
- Este documento consolida limpeza e referência funcional para futura reimplementação de CT stream.

## 3) Plano em 2 fases

## Fase 1 (agora)
- Desligamento operacional do legado sem apagar histórico.
- UI/API ativa sem referências operacionais a `certstream/crtsh`.
- Scheduler exibido a partir de configuração ativa + baseline explícito `04:00 UTC = 01:00 UTC-3`.

## Fase 2 (remoção definitiva)
- Remover código legado não utilizado:
  - worker `ct_ingestor`,
  - clients/use-cases ligados a `certstream/crtsh`,
  - migrações/colunas/tipos não mais necessários para operação.
- Limpar documentação histórica legada e scripts operacionais que dependem de CT antigo.

## 4) Referência abstrata de CertStream (sem acoplamento à implementação antiga)

## O que é
- Feed em tempo real de eventos de Certificate Transparency (CT) contendo domínios observados em certificados emitidos.
- Útil para detecção precoce de domínios suspeitos antes de propagação em outras fontes.

## Entradas esperadas
- Evento de CT contendo, no mínimo:
  - timestamp de observação,
  - lista de nomes de domínio/FQDN do certificado (SAN/CN),
  - metadados opcionais (issuer/log/source).

## Saídas esperadas
- Lote normalizado de domínios registráveis por TLD, pronto para upsert idempotente.
- Métricas operacionais por flush:
  - recebidos,
  - normalizados,
  - inseridos,
  - descartados por política.

## Pipeline funcional mínimo
1. Ingestão de eventos do stream.
2. Bufferização em memória com deduplicação por janela curta.
3. Normalização (lowercase, registrable domain, saneamento).
4. Aplicação de política por TLD (allow/deny/prioridade).
5. Persistência idempotente no destino (upsert sem duplicação lógica).
6. Atualização de métricas e checkpoint.

## Buffering, deduplicação e idempotência
- Buffer por tamanho/tempo (`max_items` ou `max_age_seconds`).
- Deduplicação intra-buffer por chave canônica do domínio.
- Escrita idempotente no banco (`ON CONFLICT DO NOTHING` ou estratégia equivalente).

## Políticas por TLD
- Fonte de verdade em tabela de configuração por `source+tld`.
- Estados mínimos:
  - habilitado/desabilitado,
  - prioridade opcional,
  - timestamps de atividade.
- Descoberta automática de novos TLDs opcional, mas sempre com política explícita para ativação real.

## Checkpoints e observabilidade
- Checkpoint mínimo:
  - último offset/instante processado,
  - último flush com sucesso.
- Telemetria:
  - taxa de entrada por minuto,
  - latência de flush,
  - taxa de erro/retry,
  - backlog do buffer,
  - saúde de conexão.
- Health endpoint deve refletir:
  - stream conectado/desconectado,
  - idade do último evento,
  - idade do último flush com sucesso.

## Modos de falha e requisitos para futura reimplementação
- Falhas esperadas:
  - desconexão do stream,
  - burst acima da capacidade de flush,
  - erro de normalização em eventos malformados,
  - indisponibilidade temporária do banco.
- Requisitos:
  - reconnect com backoff exponencial e jitter,
  - flush parcial resiliente (sem perder lote inteiro),
  - DLQ/log estruturado para itens inválidos,
  - shutdown gracioso com drenagem de buffer,
  - limites de memória/pressão (backpressure).

## 5) Critérios de aceite da limpeza
- `/admin/ingestion` não mostra `certstream` nem `crtsh`.
- `GET /v1/ingestion/summary` retorna apenas `czds` e `openintel`.
- `GET /v1/ingestion/cycle-status` não inclui agendamentos legados CT.
- `GET /v1/ingestion/tld-status?source=certstream` retorna erro de validação.
- `infra/stack.yml` e `infra/stack.dev.yml` sem `ct_ingestor` e `certstream_server`.
- Existe somente um scheduler diário operacional de ingestão (`ingestion_worker`).
- Runs históricos legados permanecem para auditoria; novos runs legados não são operacionais.
