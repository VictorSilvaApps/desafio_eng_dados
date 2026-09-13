# Registro do uso de Inteligência Artificial

Exigido pela **seção 10** do enunciado. O enunciado permite usar IA à vontade, mas
mantém a equipe responsável por testar, compreender e justificar tudo — e pede
explicitamente o registro dos **erros e inadequações** encontrados nas respostas.

Este documento não é retórico. Os erros abaixo aconteceram, estão datados, e cada um
tem a correção ao lado.

---

## 1. Ferramentas utilizadas

**Claude (Opus 5), via Claude Code**, em duas sessões no dia 11/09/2026:

- **Sessão 1** — leitura do enunciado, perfilamento dos três datasets e produção de
  [`levantamento_requisitos.md`](levantamento_requisitos.md) e
  [`instrucoes_para_ia.md`](instrucoes_para_ia.md).
- **Sessão 2** — verificação daqueles documentos e implementação do pipeline RF01–RF14.

O modelo tinha acesso ao terminal, ao repositório e aos bancos. Nenhuma resposta foi
aceita sem execução: cada etapa do pipeline foi rodada e conferida contra o dado real.

**ChatGPT (GPT-5.6 Sol)** foi utilizado em 13/09/2026 para uma revisão final da
entrega da equipe. A revisão preservou a implementação existente e concentrou-se em
reprodutibilidade, execução no Windows, persistência das recomendações, documentação
e validação ponta a ponta. As alterações sugeridas também foram testadas antes de
serem incorporadas.

## 2. Exemplos de solicitações

| O que foi pedido | O que voltou |
|---|---|
| "Levante os requisitos do desafio e perfile os dados" | Catálogo RF01–RF14 com critério de aceite, perfil medido das 3 fontes e 8 lacunas do enunciado |
| "Confira se os números do levantamento se sustentam" | Script que remede tudo contra os arquivos: 35 de 35 conferiram |
| "Implemente o pipeline completo seguindo as instruções" | `src/` com 9 etapas, DDL, views, 50 testes |
| "Por que `corrigidos` deu 834 se o dado está limpo?" | Diagnóstico: era a ordenação das tags, não defeito |

## 3. Decisões apoiadas pela IA

- **Ivis pela via vetorial** em vez da proporção por categoria (G4) — o argumento do
  *cold start* (375 conteúdos sem histórico) decidiu.
- **Schema `desafio`** em vez de banco novo, depois de constatar que o usuário não tem
  `rolcreatedb`.
- **Filtros do Superset por um segundo PUT**, em vez de alterar o `toolkit/`
  compartilhado com as outras aulas.
- **Chave de duplicidade diferente por fonte** — `(usuario, conteudo)` em comentários,
  mas a quádrupla com tipo e instante em interações.

Todas foram revisadas pela equipe e estão registradas no [README](../README.md).

---

## 4. Erros e inadequações encontrados nas respostas

### 4.1 — Contador de correções que nunca contava nada

A função `_mudou`, que alimenta o contador `corrigidos` do RF05, normalizava **os dois
lados** antes de comparar:

```python
elif _texto(antigo) != _texto(novo):     # errado
```

`_texto` remove espaços das pontas e colapsa espaços internos. Aplicá-la ao valor
original apagava exatamente a diferença que a função existia para detectar — o contador
viveria zerado para sempre, e ninguém notaria, porque zero é justamente o valor
esperado num dado limpo.

**Como foi pego:** um teste com `'  texto   sujo  '` esperava `corrigidos == 1` e
recebeu `0`.
**Correção:** comparar contra o valor cru. `src/ingestao/tratamento.py`.

### 4.2 — A métrica corrigida passou a mentir para o outro lado

Consertado o 4.1, o pipeline reportou **834 dos 994 comentários como "corrigidos"**.
Número alto demais para um dado descrito como limpo. Ao medir:

```
tags fora de ordem alfabética : 837
tags com maiúscula            : 0
tags com espaço nas pontas    : 0
tags repetidas no mesmo doc   : 0
```

Os 834 eram **só a ordenação das tags** que o próprio tratamento aplica. Ordenar
padroniza, mas não conserta nada — e apresentar isso como "834 registros corrigidos"
daria à banca uma ideia falsa da qualidade dos dados.

**Correção:** `_mudou` passou a comparar o conteúdo da lista, não a ordem. `corrigidos`
voltou a 0, que é a resposta verdadeira. Dois testes novos travam o comportamento.

### 4.3 — Teste que afirmava que uma data válida era inválida

Um teste gerado listava `'20250306'` entre os formatos que deveriam ser rejeitados. Ele
falhou — e o validador estava certo: desde o Python 3.11, `date.fromisoformat` aceita o
**formato básico** do ISO 8601, e `20250306` é uma data ISO legítima. Rejeitá-la seria
o erro, porque o RF04 manda *converter* datas para um formato único, não recusar uma
grafia válida.

**Correção:** o teste virou o oposto — documenta que o formato básico é aceito — e a
conversão para formato único ganhou teste próprio em `tests/test_tratamento.py`.

### 4.4 — Nomes de categoria abreviados no levantamento

O `levantamento_requisitos.md` lista as categorias como `IA`, `BI` e `Eng. de Dados`.
Os valores reais no arquivo são **`Inteligência Artificial`**, **`Business
Intelligence`** e **`Engenharia de Dados`**. As abreviações eram licença editorial para
a tabela caber na página.

Se tivessem sido copiadas para o domínio do validador, os **1000 registros do catálogo**
seriam classificados como "categoria fora do domínio" — e o pipeline pareceria estar
funcionando, só que rejeitando tudo.

**Correção:** os domínios em `src/ingestao/validacao.py` foram extraídos do arquivo, não
do documento.

### 4.5 — Lacuna que o levantamento não viu: títulos repetidos

O levantamento perfilou o tamanho das descrições, mas não a unicidade dos títulos. O
problema só apareceu ao **rodar** a busca semântica: a primeira consulta devolveu a
mesma linha três vezes, com similaridade idêntica.

O catálogo tem **811 títulos distintos em 1000 conteúdos** e 612 descrições distintas.
Como o embedding é feito de título + descrição (RF08), conteúdos diferentes acabam com
vetores idênticos.

**Correção:** não são duplicatas — têm id, autor e carga diferentes, e continuam todos
no banco. A deduplicação acontece na exibição, em `busca.py` e `motor.py`.

### 4.6 — Ambiguidade do `Icur` que passou batido no levantamento

O levantamento resolveu as ambiguidades do `Ivis` (G4) e da faixa "Estável" (G3), mas
tratou o `Icur` como se estivesse definido. Não está: "proporção de sinais positivos na
categoria do candidato" não diz qual é o denominador, e as duas leituras plausíveis dão
resultados incompatíveis — uma delas classificaria quase tudo como Negativo.

**Correção:** decisão tomada, justificada no docstring de
`src/recomendacao/motor.py` e registrada no README.

### 4.7 — Função do toolkit que geraria SQL inválido

O `instrucoes_para_ia.md` mapeia `RF08 → toolkit.vetorial.criar_indice`. Mas essa função
monta o nome do índice interpolando o nome da tabela, e a tabela do desafio é qualificada
pelo schema:

```
CREATE INDEX idx_desafio.conteudo_embedding_embedding ...   -- ponto no identificador
```

**Correção:** o índice HNSW é criado no `sql/criar_banco.sql`, com `vector_cosine_ops`
casando com o operador `<=>` da consulta. O motivo está comentado em
`src/vetorial/embeddings.py`.

### 4.8 — O Git alterou os arquivos de origem em silêncio

No primeiro commit da documentação, o `git` avisou que trocaria CRLF por LF no
`catalogo.csv`. Com `core.autocrlf = input`, o blob versionado ficou **1001 bytes menor**
que o arquivo baixado do Drive — um `\r` por linha. Os arquivos deixaram de ser idênticos
à origem, o que contraria o RF04 e a rastreabilidade do levantamento.

**Correção:** `.gitattributes` com `-text` para `documentacao/fontes/**` e
`dados/brutos/**`, e `git add --renormalize`. Os três datasets voltaram a bater hash a
hash com o disco.

### 4.9 — Recomendações acumulavam a cada reexecução

A persistência usava `gerado_em` como parte da chave de conflito. Como cada execução
gera um novo horário, executar o mesmo pipeline novamente criava outro lote completo
de recomendações. Com a mesma entrada, duas execuções poderiam deixar 3000 registros
onde o resultado corrente esperado era de 1500.

Não era uma falha de execução: o próprio README documentava esse comportamento como
histórico por lote. Na revisão final, ele foi tratado como uma inadequação de
reprodutibilidade, porque o restante da carga é idempotente e a entrega deve poder ser
executada novamente sem acumular estado anterior.

**Correção:** `motor.persistir()` passou a remover o lote anterior e inserir o novo
dentro da mesma transação. A correção foi verificada executando a recomendação duas
vezes; após ambas, `COUNT(*) = 1500` e `COUNT(DISTINCT gerado_em) = 1`.

---

## 5. O que a equipe alterou nas respostas

| Alteração | Motivo |
|---|---|
| Leitura da ingestão sem `pandas` | O pandas converte data e número na leitura e apaga o defeito antes de o validador do RF03 vê-lo |
| Carga num cursor único, sem `inserir_df` | O RF06 exige transação; a função do toolkit abre uma conexão por chamada |
| Filtros do Superset por PUT adicional | Alterar o `toolkit/` afetaria as outras aulas |
| `dados/brutos/` com permissão 444 | Garante o "preservar os originais" do RF04 por permissão, não por disciplina |
| Distribuição das faixas sobre os 150 mil pares | A lista final é o topo do ranking e sai quase toda Positiva; só a distribuição completa mostra que a faixa discrimina (31,4% / 31,9% / 36,7%) |

---

## 6. Conclusão honesta

O uso de IA acelerou muito o trabalho, desde a implementação inicial até a revisão
final, mas **nove inadequações verificáveis** foram identificadas durante a validação.
Várias delas só apareceram quando o código foi executado, os números foram questionados
ou o estado real dos bancos e do repositório foi conferido. Dois dos erros (4.1 e 4.2)
eram de medição: o programa rodava sem reclamar e reportava um número errado, que é a
falha mais perigosa num pipeline de dados, porque não se anuncia.

A lição prática para a apresentação é: **rodar não é verificar**. As respostas da IA
foram confrontadas com os dados reais, testes, bancos, logs e comportamento do pipeline
antes de serem aceitas pela equipe.
