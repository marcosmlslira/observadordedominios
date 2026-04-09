**Documento de Requisitos de Produto (PRD)**

**Título:** Ingestão de Dados OpenINTEL via S3 (Complemento ao Pipeline CZDS + CertStream)  
**Versão:** 1.1  
**Data:** 09 de abril de 2026  
**Autor:** Grok (baseado nos requisitos do usuário)  
**Objetivo do documento:** Definir de forma clara e não-técnica os requisitos para a nova funcionalidade de ingestão dos dados de ccTLDs do OpenINTEL diretamente do S3 público, sem download local, com controle de ingestão por TLD e integração total com o dashboard existente.

### 1. Introdução
O sistema atual já ingere dados completos de gTLDs via CZDS e dados em tempo real via CertStream.  
Esta funcionalidade complementa o pipeline com os **307 ccTLDs** (ex.: .br, .uk, .de, .au etc.) fornecidos pelo OpenINTEL, que não estão disponíveis no CZDS.  

O foco é obter listas de apex domains (eTLD+1) de forma eficiente, performática e confiável, especialmente para TLDs grandes como .com (onde o CZDS é lento e volumoso).

### 2. Objetivos de Negócio
- Complementar a cobertura de domínios com ccTLDs que o CZDS não entrega.
- Reduzir significativamente o tempo e recursos de processamento de TLDs grandes (ex.: .com).
- Garantir que a ingestão seja **idempotente** (não duplique dados) e **robusta** (continue funcionando mesmo quando não houver dados novos).
- Permitir que o time de dados visualize facilmente as ingestões no **dashboard atual** do sistema.
- Evitar qualquer conflito com o pipeline existente de CZDS.

### 3. Escopo
**In Scope:**
- Leitura direta dos arquivos Parquet do OpenINTEL no S3 público (sem salvar nada no disco).
- Descoberta automática do **último snapshot disponível** por TLD.
- Controle centralizado de ingestão (o que foi processado por TLD + data).
- Tratamento automático de cenários sem arquivo ou sem dados novos.
- **Integração com o dashboard atual** para visualização completa das ingestões realizadas (status, data, quantidade de registros, TLD etc.).
- Integração com o lakehouse existente (salvar os dados enriquecidos no destino atual).
- Suporte inicial para os 307 ccTLDs (prioridade para .br e outros relevantes para o negócio).

**Out of Scope:**
- Ingestão de medições completas de gTLDs ou forward-DNS (apenas as listas de ccTLDs).
- Processamento de dados históricos antigos (foco em snapshots recentes).

### 4. Requisitos Funcionais

**RF-01 – Descoberta Automática**  
O sistema deve navegar automaticamente no S3 e identificar o snapshot mais recente (data + arquivo) disponível para cada TLD desejado.

**RF-02 – Controle de Ingestão**  
Deve existir um registro central que armazene, para cada TLD:
- Data do snapshot ingerido
- Arquivo S3 utilizado
- Quantidade de registros processados
- Status (sucesso / falha)

**RF-03 – Idempotência**  
Se o mesmo snapshot de um TLD já foi ingerido, o sistema deve pular automaticamente e registrar o motivo.

**RF-04 – Leitura Direta**  
Os dados devem ser lidos diretamente do S3 (streaming) e filtrados pelo TLD desejado, sem download completo do arquivo.

**RF-05 – Tratamento de Ausência**  
Quando não existir arquivo para um TLD em um determinado dia ou período:
- O sistema deve registrar o evento como “sem dados disponíveis”.
- Não deve gerar erro ou parar o pipeline.
- Deve continuar processando os demais TLDs.

**RF-06 – Execução Agendada**  
O job deve rodar diariamente (ou conforme agendamento configurado) e processar todos os TLDs configurados.

**RF-07 – Integração com Dashboard Atual**  
Todas as ingestões realizadas (OpenINTEL) devem aparecer automaticamente no dashboard existente do sistema, com as mesmas colunas e filtros usados pelas ingestões CZDS e CertStream.

### 5. Requisitos Não Funcionais

- **Performance:** Leitura e filtro de TLD deve ser significativamente mais rápido que o parsing de zone files do CZDS (meta: redução de tempo em pelo menos 70% para TLDs grandes).
- **Escalabilidade:** Suportar dezenas de TLDs simultaneamente sem impacto no pipeline atual.
- **Confiabilidade:** Tolerância a falhas de rede ou ausência temporária de dados no S3.
- **Segurança:** Acesso apenas via S3 anônimo público (sem credenciais).
- **Monitoramento:** Logs claros de cada etapa (descoberta, ingestão, skip) que alimentam o dashboard.
- **Manutenibilidade:** Configuração simples de lista de TLDs (sem alterar código).
- **Sem Conflito com CZDS:** A ingestão OpenINTEL **não pode executar ao mesmo tempo** que a ingestão CZDS, pois ambas escrevem na **mesma partição** do lakehouse. O sistema deve garantir que os jobs nunca rodem em paralelo (ex.: lock, agendamento sequencial ou mutex).

### 6. Fluxo de Alto Nível (Visão Geral)
1. Scheduler dispara o job diário (com garantia de não sobrepor o job CZDS).
2. Para cada TLD configurado → Sistema consulta o S3 e encontra o snapshot mais recente.
3. Verifica no controle de ingestão se já foi processado.
4. Se não → Lê diretamente o Parquet, filtra pelo TLD e envia para o lakehouse (mesma partição do CZDS).
5. Registra o sucesso/quantidade no controle de ingestão.
6. Os dados aparecem imediatamente no dashboard atual.
7. Se não houver dados → Registra “skip” e continua.

### 7. Métricas de Sucesso
- Taxa de ingestão diária ≥ 95% dos TLDs configurados.
- Tempo médio de processamento por TLD < 5 minutos (meta inicial).
- Zero duplicidade de dados.
- Zero conflitos ou sobreposições com o job CZDS.
- Logs 100% rastreáveis e visíveis no dashboard (o que foi ingerido, quando e por quê).
- Redução perceptível no gargalo do .com e outros gTLDs grandes.

### 8. Dependências e Premissas
- Acesso ao bucket S3 público do OpenINTEL (endpoint e bucket já confirmados).
- Licença CC BY-NC-SA 4.0 respeitada (atribuição nos logs ou documentação interna).
- Pipeline atual (CZDS + CertStream) permanece inalterado.
- Ambiente tem suporte a leitura Parquet via S3.
- O scheduler atual permite agendamento sequencial ou lock para evitar execução simultânea com CZDS.

### 9. Riscos e Mitigações
- Risco: Mudança na estrutura do S3 → Mitigação: Descoberta dinâmica de arquivos (não hard-coded).
- Risco: Ausência prolongada de dados → Mitigação: Tratamento explícito de “sem arquivo”.
- Risco: Volume alto em alguns dias → Mitigação: Leitura em streaming + filtro precoce.
- Risco: Conflito com CZDS → Mitigação: Lock ou agendamento sequencial obrigatório (já incluído nos requisitos).
