# 015 — OpenINTEL Zonefiles Grandes no Databricks: Diagnóstico e Plano de Correção

## Objetivo

Restabelecer a confiabilidade da ingestão `openintel` para TLDs `zonefile` grandes no caminho Databricks, com foco em:

- `ch`
- `fr`
- `se`
- outros TLDs da mesma classe de volume

O objetivo não é apenas "fazer passar no Databricks", mas garantir uma estratégia que seja:

- previsível em memória
- observável em produção
- economicamente controlável
- compatível com crescimento futuro dos snapshots

---

## Situação Atual

### Evidências já confirmadas

- `jp` (`cctld-web`) no Databricks: `SUCCESS`
- `ee` (`zonefile`) no Databricks: `SUCCESS`
- `ch` (`zonefile`) no Databricks: `OOM / exit 137`
- `fr` (`zonefile`) no Databricks: erro reportado pelo operador
- `se` (`zonefile`) foi submetido para validação pontual
- `info` (`czds`) no Databricks: `SUCCESS`
- `org` (`czds`) no Databricks: `SUCCESS`

### Tamanhos medidos dos snapshots OpenINTEL `zonefile` em `2026-05-01`

| TLD | Arquivos | Tamanho total | Maior arquivo |
|-----|----------|---------------|---------------|
| `ch` | 3 | 2.58 GB | 1.24 GB |
| `ee` | 1 | 92.5 MB | 92.5 MB |
| `fr` | 3 | 3.69 GB | 1.33 GB |
| `li` | 1 | 47.7 MB | 47.7 MB |
| `se` | 3 | 2.44 GB | 1.97 GB |
| `sk` | 1 | 585.9 MB | 585.9 MB |

### Conclusão parcial

O problema não é "todo Databricks falha" nem "todo zonefile falha".

Tambem nao ha evidencia, ate aqui, de que "dataset grande no Databricks" falhe por si so.

O problema esta concentrado em `OpenINTEL zonefiles` grandes e no perfil de memoria do parser atual dessa fonte.

### Restrição Operacional Confirmada

Não é possível aumentar a capacidade do ambiente atual.

O que existe disponível para validação/execução é:

- Databricks `serverless`
- Databricks `community`, com limitações próprias do ambiente

Isso elimina a estratégia de "subir memória/compute" como solução principal.

---

## Causa Técnica Mais Provável

O parser atual em `ingestion/ingestion/sources/openintel/client.py`:

1. faz `get_object(...).read()` do objeto inteiro
2. faz `pl.read_parquet(BytesIO(payload))`
3. acumula `DataFrame`s em memória
4. concatena todos
5. executa `unique()`
6. materializa `to_list()`
7. ordena em memória

Esse modelo é compatível com snapshots pequenos e médios, mas é frágil para snapshots multi-GB.

Portanto, a causa-raiz provável é:

- **algoritmo memory-hungry**
- agravado por `zonefiles` grandes
- potencialmente sensível à cardinalidade e ao layout do parquet do TLD

---

## Hipóteses a Validar

### H1 — O problema é o algoritmo atual, independentemente do ambiente

Se `ch` falha localmente e também falha no Databricks com OOM, o gargalo está no parser.

### H2 — TLDs grandes podem exigir faixas distintas de memória

Mesmo entre TLDs grandes, o comportamento pode variar por:

- cardinalidade
- compressão
- distribuição por row group
- custo de deduplicação

### H3 — Mais memória pode aliviar, mas não resolve estruturalmente

Escalar o compute do Databricks pode reduzir a frequência de erro, mas não elimina a fragilidade do parser atual.

### H4 — O gargalo não é genérico de ingestões grandes

Se `CZDS:info` e `CZDS:org` concluem com sucesso no mesmo ambiente, a causa não está apenas em "volume grande" ou "limite geral do Databricks", mas no comportamento específico do pipeline `OpenINTEL zonefile`.

---

## Opções Técnicas

### Opção A — Reescrever o parser para processamento incremental

Substituir o padrão atual por leitura em lotes/row groups, sem materializar o snapshot inteiro.

Direção preferencial:

- `pyarrow` por row group
- deduplicação incremental
- escrita intermediária controlada

**Vantagens**
- solução estrutural
- menor consumo de memória
- mais previsível com crescimento futuro

**Desvantagens**
- implementação mais trabalhosa
- exige testes mais detalhados

### Opção B — Stage local temporário + processamento chunked

Baixar o parquet para disco local do cluster e processar por partes.

**Vantagens**
- reduz pressão de RAM
- mais simples que uma reescrita completa

**Desvantagens**
- ainda exige revisão da estratégia de deduplicação
- depende do disco efêmero do runtime

### Opção C — Processamento intermediário com Spark

Usar Spark apenas para leitura e transformação pesada, mantendo a publicação final por outros meios.

**Vantagens**
- engine apropriada para dados grandes
- escalável

**Desvantagens**
- maior complexidade operacional
- limitações de escrita externa no ambiente atual
- adiciona outra camada de execução

---

## Recomendação

### Curto prazo

1. manter `openintel` em `databricks_only` para observação controlada
2. remover temporariamente do ciclo os TLDs que falham de forma recorrente (`ch` e outros que confirmarem o padrão)
3. concluir a matriz de testes pontuais de TLDs grandes
4. usar `CZDS` grande como grupo de controle ao avaliar mudanças no parser e no runtime

### Médio prazo

5. implementar parser incremental para `zonefile`
6. testar variações de implementação dentro das limitações reais do ambiente

### Longo prazo

7. padronizar observabilidade do Databricks:
   - `run_id`
   - URL
   - estado
   - TLD/batch atual
8. definir política operacional por classe de TLD:
   - pequeno
   - médio
   - grande
   - grande crítico

---

## Comparativo com CZDS

Os testes pontuais de `CZDS` grandes servem como controle operacional da plataforma.

Resultados confirmados:

- `info`: `SUCCESS`
- `org`: `SUCCESS`

Isso indica que:

- o Databricks atual consegue concluir ingestões grandes sob as limitações de `serverless/community`
- o problema observado não deve ser tratado como limitação universal do ambiente
- a investigação precisa focar no desenho de leitura/processamento do `OpenINTEL zonefile`

---

## Matriz de Testes Requerida

### Classe pequena/média

- `ee`
- `li`
- `sk`

### Classe grande

- `ch`
- `se`
- `fr`

### Classe web

- `jp`

Para cada teste registrar:

- TLD
- modo (`cctld-web` ou `zonefile`)
- tamanho total do snapshot
- quantidade de arquivos
- runtime/cluster usado
- status final
- tempo total
- OOM ou não

---

## Entregas Esperadas

1. tabela consolidada de comportamento por TLD grande
2. decisão operacional sobre exclusão temporária de TLDs problemáticos
3. proposta técnica final do parser incremental
4. patch com observabilidade Databricks exposta em produção

---

## Critérios de Conclusão

- [ ] matriz de testes pontuais concluída
- [ ] TLDs grandes classificados por risco
- [ ] estratégia aprovada para `ch`/`fr`/`se`
- [ ] parser incremental especificado ou implementado
- [ ] observabilidade de runs Databricks disponível na API/monitor
