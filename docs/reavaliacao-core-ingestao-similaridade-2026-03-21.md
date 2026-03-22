# Reavaliacao do Core: Ingestao de Dominios e Similaridade

Data da analise: 2026-03-21

## Escopo

Esta reavaliacao cobriu apenas o core do produto:

- ingestao de dominios via CZDS;
- persistencia otimizada da tabela `domain`;
- analise e identificacao de similaridade entre dominios;
- aderencia entre implementacao, PRD e documentos tecnicos;
- validacao de endpoints e comportamento real do runtime atual.

Fontes consultadas:

- `.specs/product_definition.md`
- `.specs/features/domain-database/prd.md`
- `docs/czds-zone-ingestion-refinement.md`
- `docs/domain-table-redesign-proposal.md`
- `docs/similarity-analysis-architecture.md`
- `docs/similarity-service-refinement.md`
- codigo em `backend/app/**` e migrations em `backend/alembic/versions/**`
- runtime real exposto em `http://localhost:8005`
- banco PostgreSQL real da stack `obs_*`

Nota importante:

- O runtime e o banco carregam estado historico de revisoes anteriores. Isso aparece nos logs de ingestao e em `ingestion_run`.
- Os achados abaixo consideram o que o codigo atual diz, o que o banco atual contem e o que os endpoints realmente entregam hoje.

## Resumo executivo

Conclusao curta: o core esta funcional apenas de forma parcial e hoje nao esta aderente ao que o produto promete para ingestao canonica, rastreabilidade historica e confianca da similaridade.

Os problemas que mais colocam o sucesso do produto em risco sao:

1. a ingestao esta armazenando tambem hostnames/subdominios do zone file, nao apenas dominios canonicos;
2. a modelagem historica prometida no PRD nao existe na base atual;
3. a calibragem de similaridade produz ruido alto e classifica casos obvios de forma errada;
4. o contrato proposto para o servico de similaridade nao foi implementado;
5. a operacao de ingestao pode travar um TLD indefinidamente;
6. endpoints administrativos criticos continuam sem autenticacao e com organizacao placeholder.

Se eu tivesse que escolher uma unica prioridade imediata, seria esta:

- corrigir a canonicalizacao da ingestao antes de continuar expandindo a similaridade ou adicionar mais TLDs.

## Testes e validacoes executadas

| Validacao | Resultado | Observacao |
|---|---|---|
| `GET /health` | `200` | backend responde normalmente |
| `GET /openapi.json` | `200` | OpenAPI disponivel |
| `GET /v1/czds/runs?limit=5` | `200` | endpoints de operacao ativos |
| `GET /v1/brands` | `200` | 7 marcas ativas retornadas para a org placeholder |
| `GET /v1/brands/{google}/matches?limit=10` | `200` | 5.478 matches para Google |
| `POST /v1/brands/{google}/scan?tld=net` | `202` | scan delta executou e finalizou com 0 novos candidatos |
| `POST /v1/brands` com `Google` duplicado | `409` | deduplicacao funciona apenas dentro da org placeholder |
| `POST /v1/czds/trigger-sync` com `org` | `409` | bloqueado porque existe run preso em `running` |
| `GET /v1/matches/{uuid-inexistente}` | `404` | endpoint responde |
| `GET /v1/czds/runs/{uuid-inexistente}` | `404` | endpoint responde |
| `python -m pytest -q` em `backend/` | falhou por ausencia de testes | `no tests ran in 0.06s` |
| `python -m pytest -q /app/tests` no container | falhou | `pytest` nao esta instalado na imagem |

Dados reais consultados no banco:

- `domain`: 31.309.767 linhas
- `similarity_match`: 11.496 linhas
- `similarity_scan_cursor`: 19 linhas
- `zone_file_artifact`: 6 linhas
- `domain_observation`: tabela inexistente
- `domain_old`: 8.787 MB
- banco `obs`: 14 GB

## Aderencia resumida

| Tema | Status | Veredito |
|---|---|---|
| Ingestao CZDS basica | parcial | baixa e persiste artefatos, mas o alvo persistido esta contaminado |
| Salvamento otimizado | parcial | schema simplificado existe, mas a base ainda carrega legado pesado e sem historico |
| Delta real e rastreabilidade | nao aderente | historico append-only nao existe hoje |
| Similaridade operacional | parcial | gera resultado e persiste matches, mas com ruido alto |
| Contrato do similarity service | nao aderente | endpoint proposto nao existe |
| Seguranca e multitenancy operacional | nao aderente | endpoints publicos e org placeholder |
| Protecao por testes | nao aderente | nao ha suite automatizada |

## Achados criticos

### 1. A ingestao esta salvando owner names/subdominios, nao apenas dominios canonicos

Evidencias:

- `backend/app/services/use_cases/apply_zone_delta.py:21-43` promete "second-level domain names", mas apenas le `owner = parts[0]` e faz `yield owner` sem reduzir para dominio registravel.
- O PRD exige canonicalizacao e padronizacao de `TLD/eTLD+1` em `.specs/features/domain-database/prd.md:68-71`.
- O banco atual mostra contaminacao real:
  - `info`: 134.203 labels com ponto no `label` (`2,39%`)
  - `net`: 189.044 labels com ponto (`1,45%`)
  - `org`: 383.082 labels com ponto (`3,02%`)
- Exemplos reais persistidos na tabela `domain`:
  - `ns1.virtualfundsuri.info`
  - `ns1.miamifruits.pro.namesilo.info`
  - `ns1.techniker-tk.info`
- Exemplos reais que viraram match de similaridade:
  - `ns1.ads-google.net`
  - `ns.google0.org`
  - `google.w-w-a.info`

Impacto real:

- o produto deixa de monitorar somente dominios registraveis e passa a monitorar ruido de DNS/infraestrutura;
- a similaridade fica poluida por hostnames que nao representam registros de dominio atacantes;
- o volume armazenado cresce sem gerar inteligencia proporcional;
- o score perde confianca exatamente no centro do produto.

Recomendacao objetiva:

- normalizar a ingestao para persistir somente o dominio canonico registravel;
- se for necessario preservar owner names tecnicos, guardar em outra estrutura de evidencias, nao em `domain`;
- reprocessar/backfill da base depois da correcao, ou a similaridade continuara contaminada.

### 2. O modelo historico prometido no PRD nao existe na base atual

Evidencias:

- O PRD exige modelo temporal `event + snapshot` e observacoes append-only em `.specs/features/domain-database/prd.md:78-81` e `.specs/features/domain-database/prd.md:254-261`.
- O refinamento de CZDS tambem define `domain_observation` como evento append-only em `docs/czds-zone-ingestion-refinement.md:56-60` e `docs/czds-zone-ingestion-refinement.md:228-235`.
- A migration `backend/alembic/versions/005_domain_redesign_partitioned.py:66-71` faz `DROP TABLE IF EXISTS domain_observation` e renomeia a tabela antiga para `domain_old`.
- O banco atual realmente nao possui `domain_observation`.
- O model Python `backend/app/models/domain_observation.py:16-19` ainda referencia `domain.id`, mas o model atual `backend/app/models/domain.py:13-15` nao tem `id`; a PK agora e `(name, tld)`.
- `backend/app/main.py:27-30` registra apenas `health`, `czds_ingestion`, `monitored_brands` e `similarity`; nao existem endpoints de consulta de dominios/observacoes pedidos em `.specs/features/domain-database/prd.md:281-288`.

Impacto real:

- nao existe trilha historica confiavel por fonte para auditoria e investigacao;
- nao ha como explicar "quando apareceu", "em qual execucao apareceu" e "qual evidencia sustentou o estado";
- a implementacao atual nao entrega a base global historica descrita para o produto;
- o proprio codigo de modelo ficou semanticamente incoerente com o schema vigente.

Recomendacao objetiva:

- decidir explicitamente se o produto vai ser `snapshot-only` ou `event + snapshot`;
- se a decisao correta for seguir o PRD, restaurar `domain_observation`, ajustar o schema e expor endpoints de consulta;
- se a decisao for simplificar o produto, atualizar PRD, refinamentos e promessas comerciais antes de seguir.

### 3. O redesign economizou schema, mas o banco ainda paga 8,8 GB de legado morto

Evidencias:

- `backend/alembic/versions/005_domain_redesign_partitioned.py:69-76` renomeia a tabela antiga para `domain_old` e nao a remove no `upgrade`.
- No banco atual:
  - `domain_old`: `8787 MB`
  - `domain_net`: `2334 MB`
  - `domain_org`: `2366 MB`
  - `domain_info`: `1070 MB`
  - banco `obs`: `14 GB`

Impacto real:

- quase dois terços do banco atual sao ocupados por legado que nao participa do fluxo atual;
- backup, restore, storage e janelas operacionais ficam mais caros do que o necessario;
- a narrativa de "salvamento otimizado" esta parcialmente anulada na pratica.

Recomendacao objetiva:

- validar se `domain_old` ainda e necessario para rollback;
- se nao for, remover ou arquivar fora do banco transacional;
- documentar a politica de descarte de legado apos migration estrutural.

### 4. A calibragem da similaridade esta produzindo falso positivo e classificacao errada

Evidencias de codigo:

- `backend/app/services/use_cases/run_similarity_scan.py:25-27` persiste qualquer match com `score_final >= 0.30`.
- `backend/app/services/use_cases/compute_similarity.py:190-197` marca `critical` se `brand_hit == 1.0 and score_keyword > 0`, mesmo quando o `score_final` e baixo.
- `backend/app/services/use_cases/compute_similarity.py:221-224` marca `typosquatting` sempre que `lev >= 0.7 and trigram >= 0.4`, inclusive em match exato.

Evidencias no banco:

- `11.496` matches no total.
- `7.155` matches sao apenas `brand_containment`.
- `8.509` contem `brand_containment` em algum nivel.
- Casos `critical` com score muito baixo:
  - Google: `317` criticos abaixo de `0.5`, `93` abaixo de `0.4`, `37` abaixo de `0.35`
  - Itau: `87` criticos abaixo de `0.5`, `64` abaixo de `0.4`, `43` abaixo de `0.35`
- Exemplos reais marcados como `critical` com score perto de `0.30`:
  - `ns-cloud-b1.googledomains.com.providencechurchofchrist.org` (`0.3022`)
  - `mckinneyavenuetransitauthority.org` para Itau (`0.3093`)
  - `californiatransitauthority.net` para Itau (`0.3188`)
- Match exato tambem esta sendo rotulado como typosquatting:
  - `google.net`, `google.org`, `google.info`
  - `facebook.net`, `facebook.org`, `facebook.info`
  - `itau.net`, `itau.org`, `itau.info`

Impacto real:

- alert fatigue;
- perda de confianca do usuario no score de risco;
- desperdicio operacional na triagem;
- risco de o produto parecer "barulhento" em vez de util.

Recomendacao objetiva:

- separar explicitamente `exact brand match`, `brand containment`, `typosquatting`, `homograph` e `infra hostname`;
- impedir que `critical` seja atribuido quando o score final e baixo;
- excluir hostnames/subdominios antes do scoring;
- incluir allowlist/owned domains por organizacao para evitar marcar ativos legitimos como ameaca.

### 5. O contrato proposto para o similarity service nao foi implementado

Evidencias:

- `docs/similarity-service-refinement.md:16-17` define `POST /v1/similarity/search`.
- `docs/similarity-service-refinement.md:93-94` define `GET /v1/similarity/health`.
- O router real `backend/app/api/v1/routers/similarity.py:21-87` implementa somente:
  - `GET /v1/brands/{brand_id}/matches`
  - `GET /v1/matches/{match_id}`
  - `PATCH /v1/matches/{match_id}`
- O disparo de analise hoje e via `POST /v1/brands/{brand_id}/scan` em `backend/app/api/v1/routers/monitored_brands.py:169-205`.
- Nao existe endpoint read-heavy com `query_domain`, `algorithms`, `min_score`, `offset`, `include_deleted` ou `tld_allowlist`.

Impacto real:

- a interface publicada para o core de similaridade nao bate com a implementacao;
- integracoes futuras vao ser escritas contra um contrato inexistente;
- o caso de uso central de "buscar dominios parecidos a partir de um dominio de entrada" continua sem entrega.

Recomendacao objetiva:

- decidir qual contrato e oficial;
- se o documento estiver correto, implementar `POST /v1/similarity/search` e `GET /v1/similarity/health`;
- se o caminho correto for scan assincorno por marca, atualizar imediatamente a documentacao e o material de produto.

### 6. A operacao de ingestao pode travar um TLD por tempo indefinido e os endpoints criticos seguem sem autenticacao

Evidencias operacionais:

- Existe um `ingestion_run` de `org` preso em `running` desde `2026-03-21 07:36:10Z`.
- `POST /v1/czds/trigger-sync` para `org` retorna `409` com `Sync already running for TLD=org`.
- O checkpoint de `org` esta parado em `2026-03-19 19:40:23Z`.
- `backend/app/api/v1/routers/czds_ingestion.py:61-66` bloqueia por status em banco, sem TTL/lease/heartbeat.
- `backend/app/api/v1/routers/czds_ingestion.py:42-80` nao tem dependencia de autenticacao.
- `backend/app/api/v1/routers/monitored_brands.py:27-28` usa `PLACEHOLDER_ORG_ID` e tambem nao tem autenticacao real.
- O refinamento de CZDS marcava autenticacao/autorizacao como obrigatoria em `docs/czds-zone-ingestion-refinement.md:64-67`.
- O PRD exige autorizacao por papel em `.specs/features/domain-database/prd.md:93-96` e `.specs/features/domain-database/prd.md:308-315`.

Impacto real:

- um crash ou falha de transicao pode congelar a ingestao de um TLD ate intervencao manual;
- qualquer cliente que alcance a API pode criar marcas, disparar scans e acionar ingestao;
- multitenancy nao existe no fluxo HTTP atual.

Recomendacao objetiva:

- implementar lease/heartbeat/timeout para `running`;
- criar rotina segura de recovery para runs presos;
- exigir autenticacao e autorizacao antes de expor esses endpoints;
- substituir a org placeholder por contexto real de identidade.

## Observacoes complementares

- Historico de `ingestion_run` mostra falhas anteriores relevantes:
  - `NameError: name 'Path' is not defined`
  - `null value in column "id" of relation "domain"`
  - `server closed the connection unexpectedly`
- Isso reforca que o fluxo ja passou por trocas estruturais importantes e hoje precisa de hardening real, nao apenas ajuste cosmético.
- `GET /v1/czds/runs` hoje omite `artifact_key` na listagem, embora `GET /v1/czds/runs/{run_id}` consiga retorna-lo. Isso e menor do que os itens acima, mas mostra inconsistencias de contrato ainda abertas.

## Prioridade recomendada

Ordem de execucao que mais reduz risco de produto:

1. corrigir canonicalizacao da ingestao para persistir somente dominios registraveis;
2. sanear a base contaminada e decidir o papel de `domain_observation`;
3. recalibrar scoring/risk da similaridade em cima de dados limpos;
4. implementar autenticacao, isolamento por organizacao e recovery de runs presos;
5. remover ou arquivar `domain_old`;
6. fechar o contrato oficial do servico de similaridade e alinhar documentacao.

## Veredito final

Hoje o projeto tem sinais fortes de valor tecnico, mas ainda nao tem o core pronto no nivel de confianca que esse negocio exige.

O que existe hoje prova que:

- a ingestao consegue carregar volume real;
- o banco suporta particoes e leitura para similaridade;
- a analise assincorna roda em producao local.

O que ainda nao esta resolvido, e precisa de atencao imediata:

- o dado base esta semanticamente errado para parte do volume;
- o historico prometido nao existe;
- o score gera muito ruido;
- o contrato do produto nao esta fechado na API;
- a operacao ainda depende demais de intervencao manual.
