# Instruções para o agente de IA — Desafio Prático 1

> Documento autossuficiente. Quem executar isto **não participou** do levantamento e não tem
> acesso à conversa que o originou. Tudo o que é preciso saber está aqui ou em
> [`levantamento_requisitos.md`](levantamento_requisitos.md).

---

## 1. Missão e limites

Construir um pipeline reprodutível de dados educacionais: **ingestão → PostgreSQL + MongoDB →
embeddings/pgvector → recomendação → dashboard no Superset**, atendendo os requisitos RF01 a
RF14 do enunciado em `documentacao/fontes/Desafio_1_Fundamentos_de_Dados_para_IA.docx`.

**Orçamento:** ~12 h de trabalho para uma equipe de 3. Não é um projeto de produção.

**A regra que domina todas as outras:** a equipe será avaliada explicando a solução, e
qualquer integrante pode ser chamado a explicar qualquer parte (seção 12 do enunciado).
Portanto:

- Prefira código óbvio e linear a abstração elegante.
- Nada de metaprogramação, factory dinâmica ou camada de plugin.
- Cada decisão não trivial vira **uma linha no README** explicando o porquê.
- Se uma solução não couber numa explicação de 30 segundos, escolha a mais simples.

**Não invente requisito.** Funcionalidade extra não substitui requisito obrigatório ausente
(orientação explícita da seção 1 do enunciado). Termine os 14 RFs antes de melhorar qualquer
coisa.

---

## 2. Estado do ambiente

Verificado em 11/09/2026. **Nada aqui precisa ser instalado ou provisionado.**

| Recurso | Estado | Como usar |
|---|---|---|
| Python | 3.14.4, único na máquina | venv já existe em `desafio_eng_dados/.venv` |
| PostgreSQL | 18.6 no host, `:5432` | credenciais no `.env` |
| pgvector | `postgresql-18-pgvector` 0.8.1 instalado | `CREATE EXTENSION IF NOT EXISTS vector` |
| MongoDB | ativo em `127.0.0.1:27017` | `MONGO_URI` no `.env` |
| Superset | ativo em `:8088`, admin/admin, em Docker | só pela API REST — ver §2.1 |
| Modelo de embeddings | `paraphrase-multilingual-MiniLM-L12-v2`, 384 dims, **em cache** | não baixa nada |

Dependências já instaladas no venv: `torch 2.13.0+cpu`, `sentence-transformers 6.0.1`,
`pymongo 4.18.1`, `psycopg2-binary 2.9.13`, `pandas 3.0.5`, `scikit-learn 1.9.1`,
`python-dotenv`, `pyyaml`, `rich`, `ruff`.

> **Não crie um venv novo e não atualize pins.** A máquina só tem Python 3.14 e pins antigos
> de bibliotecas de ML não têm wheel `cp314` — a instalação quebra. Se precisar mesmo instalar
> algo, confira antes se há wheel `cp314`/`abi3`/`py3-none-any` no PyPI, e instale `torch`
> apenas pelo índice CPU (`--index-url https://download.pytorch.org/whl/cpu`).

### 2.1 Superset — duas restrições que custam tempo

1. **O Superset roda em contêiner e não pertence a esta equipe.** O `docker-compose` está em
   `/home/ficdevia-11-noturno/superset_lab/superset`, **sem permissão de leitura**. Não tente
   editá-lo nem reiniciar os serviços. Trabalhe pela API REST em `http://localhost:8088`.
2. **Para o Superset alcançar o PostgreSQL do host, o endereço é `172.17.0.1`, não
   `localhost`.** Dentro do contêiner, `localhost` é o próprio contêiner e
   `host.docker.internal` **não resolve** nesta máquina. Já está parametrizado como
   `SUPERSET_DB_HOST` no `.env.example`.

### 2.2 Segredos

Credenciais vêm do `.env` (já existe `.env.example` na raiz do repositório), carregado por
`toolkit/db.py` via `python-dotenv`. Variáveis: `DB_HOST`, `DB_NAME`, `DB_USER`,
`DB_PASSWORD`, `MONGO_URI`, `MONGO_DB`, `SUPERSET_URL`, `SUPERSET_USER`, `SUPERSET_PASS`,
`SUPERSET_DB_HOST`.

**Nunca** escreva uma senha em código, em SQL, em log ou no README. O `.env` está no
`.gitignore` e deve continuar.

---

## 3. Reaproveite o `toolkit/` — não reescreva

Este repositório já tem um toolkit funcionando, com as armadilhas das aulas resolvidas.
**Leia `toolkit/*.py` antes de escrever qualquer linha.** Assinaturas conferidas:

| RF | Use | Assinatura |
|---|---|---|
| RF02 | `toolkit.ingestao.ler_tabela` | `(caminho) -> DataFrame` — CSV/TSV/Excel/JSON |
| RF02 | `toolkit.ingestao.csv_bem_formado` | `(caminho) -> (bool, str)` — detecta vírgula solta antes de estourar |
| RF04/RF06 | `toolkit.ingestao.inserir_df` | `(df, tabela, conflito=None, atualizar=True) -> int` — **`conflito` torna a ingestão idempotente** |
| RF06 | `toolkit.ingestao.ingerir_arquivo` | `(caminho, tabela, pk=None, conflito=None)` |
| RF07 | `toolkit.ingestao.ingerir_json_bruto` | `(caminho, tabela, chave=None)` — JSONB com dedup por chave |
| RF06 | `toolkit.db.conectar` / `executar` / `consultar` | `consultar(sql, params) -> list[dict]` |
| RF07 | `toolkit.db.conectar_mongo` | `() -> Database` (pymongo) |
| RF08 | `toolkit.vetorial.criar_tabela_vetorial` | `(tabela, modelo=MODELO_TEXTO, colunas_extra='')` — já faz `CREATE EXTENSION` |
| RF08 | `toolkit.vetorial.indexar_textos` | `(tabela, itens: list[(id, texto)], modelo=...)` — `ON CONFLICT`, atende "não duplicar embedding" |
| RF08 | `toolkit.vetorial.criar_indice` | `(tabela, metrica='cosseno')` — HNSW |
| RF09 | `toolkit.vetorial.buscar` | `(tabela, consulta, limite=5) -> [{id, conteudo, distancia, similaridade}]` |
| RF12 | `toolkit.kpis.taxa` / `media` / `distribuicao` | `distribuicao(tabela, coluna) -> [{categoria, total, participacao_pct}]` |
| RF12 | `toolkit.kpis.exibir` / `exibir_tabela` | saída em formato de cartão no console |
| RF13 | `toolkit.superset.Superset` | `.garantir_banco()`, `.garantir_dataset(tabela, db_id)`, `.criar_grafico(nome, viz, ds_id, params)`, `.montar_dashboard(titulo, linhas)` |
| RF13 | helpers de gráfico | `kpi(metrica, legenda, formato)`, `barras(dimensao, metrica)`, `linha(dimensao_tempo, metrica)`, `rosca(...)`, `tabela(...)`, `medidor(...)`, `m_sql(expr, rotulo)`, `m_simples(coluna, agregacao, rotulo)` |

`montar_dashboard(titulo, linhas)` recebe `linhas = [[(chart_id, largura), ...], ...]` com as
larguras somando 12. Ele já resolve o `position_json` e o `chart_configuration` — vincular um
gráfico ao dashboard **não** o posiciona, e isso já está tratado.

### 3.1 O que **não** existe no toolkit e você precisa construir

| RF | Construir |
|---|---|
| RF01 | Carregador de `config.yaml` + entrypoint `python -m src.main` |
| RF03 | Motor de validação e classificação |
| RF05 | Resumo da ingestão em JSON |
| RF10 | Motor de recomendação |
| RF11 | Tabela `recomendacao` e sua persistência |
| RF14 | Registro estruturado de execução |
| RF13 | ⚠️ **Filtros interativos** — ver aviso abaixo |

> ⚠️ **`montar_dashboard` grava `native_filter_configuration: []` fixo** (linha 159 de
> `toolkit/superset.py`). O RF13 exige **2 filtros interativos**. Você precisa estender o
> método para aceitar filtros nativos, ou adicionar os dois pela UI do Superset e exportar o
> dashboard depois. **Não marque o RF13 como pronto sem os filtros.**

---

## 4. As fontes de dados

Os três arquivos estão em `documentacao/fontes/`. Copie-os para `dados/brutos/` e **não os
altere** — o RF04 exige preservar os originais.

| Arquivo | Registros | Campos |
|---|---|---|
| `catalogo.csv` | 1000 | `conteudo_id, titulo, tipo, categoria, nivel, carga_horaria_min, data_publicacao, descricao, autor` |
| `interacoes.json` | 1000 | `usuario_id, conteudo_id, tipo_interacao, data_hora, tempo_consumido, percentual_conclusao, avaliacao_atribuida` |
| `comentarios.json` | 1000 | `usuario_id, conteudo_id, avaliacao, comentario, tags[], data` |

Domínios reais: `tipo` ∈ {Curso, Vídeo, Artigo, Podcast} · `nivel` ∈ {Básico, Intermediário,
Avançado} · 8 categorias · `tipo_interacao` ∈ {visualização, início, conclusão, curtida,
avaliação, compartilhamento} · avaliações 1–5 · `usuario_id` 1–150 · `conteudo_id` 1–1000.

**O perfil completo está na seção 5 do [levantamento](levantamento_requisitos.md).** Leia-o
antes de escrever os validadores — ele muda o que você vai fazer.

---

## 5. Modelo de dados alvo

Escreva em `sql/criar_banco.sql`, idempotente (`CREATE TABLE IF NOT EXISTS`), executável do
zero.

```
usuario              usuario_id PK
                     primeira_interacao, ultima_interacao   (derivadas)

categoria            categoria_id PK, nome UNIQUE

conteudo             conteudo_id PK
                     titulo, tipo, nivel, carga_horaria_min, data_publicacao,
                     descricao, autor
                     categoria_id FK -> categoria

interacao            interacao_id PK
                     usuario_id FK -> usuario
                     conteudo_id FK -> conteudo
                     tipo_interacao, data_hora, tempo_consumido,
                     percentual_conclusao, avaliacao_atribuida (NULL permitido)

conteudo_embedding   conteudo_id PK/FK -> conteudo
                     embedding vector(384)
                     modelo TEXT           -- RF08 exige registrar o modelo
                     gerado_em TIMESTAMP

recomendacao         recomendacao_id PK
                     usuario_id FK, conteudo_id FK
                     pontuacao NUMERIC, posicao INT,
                     classificacao TEXT,   -- Positivo / Estável / Negativo
                     gerado_em TIMESTAMP
                     UNIQUE (usuario_id, conteudo_id, gerado_em)
```

**A tabela `usuario` não tem fonte.** Nenhum arquivo traz dados de usuário — só o
`usuario_id` referenciado. Derive de `SELECT DISTINCT usuario_id` das duas fontes JSON (são
150, contíguos de 1 a 150) e **registre essa decisão no README**: é uma lacuna do enunciado.

Obrigações do RF06 a não esquecer: PK e FK em tudo, `UNIQUE` barrando duplicidade de
identificador, e **carga dentro de transação** — falha no meio faz rollback, não deixa carga
parcial.

---

## 6. Ordem de execução

Cada etapa tem critério de aceite verificável sozinho. **Não avance sobre etapa quebrada.**

| # | Etapa | RF | Pronto quando |
|---|---|---|---|
| 1 | Estrutura, `config.yaml`, `.env`, entrypoint | RF01 | `python -m src.main --ajuda` responde; nenhuma senha no código |
| 2 | Leitura das 3 fontes com contagem | RF02 | log mostra 3 arquivos × 1000 registros |
| 3 | Validação e classificação | RF03 | todo registro classificado; não-válidos com motivo; **testes da §8 passando** |
| 4 | Tratamento e padronização | RF04 | `dados/brutos/` intacto; `dados/processados/` gravado |
| 5 | Resumo JSON | RF05 | arquivo com as 8 chaves obrigatórias |
| 6 | DDL + carga no PostgreSQL | RF06 | `criar_banco.sql` roda do zero; reexecutar a carga não duplica |
| 7 | Carga no MongoDB + 5 operações | RF07 | `mongodb/consultas.js` roda; justificativa no README |
| 8 | Embeddings | RF08 | 1000 vetores; rodar 2× não duplica; modelo registrado na tabela |
| 9 | Busca semântica | RF09 | 3 consultas distintas demonstradas com saída salva |
| 10 | Recomendação | RF10 | fórmula da §7; nenhum conteúdo concluído na lista |
| 11 | Persistir recomendações | RF11 | tabela populada e consultável |
| 12 | Métricas, KPIs e views | RF12 | ≥2 métricas + ≥2 KPIs; `kpis.md` com os 6 campos por KPI |
| 13 | Dashboard | RF13 | 3 cartões + barras + linhas + **2 filtros**; exportado |
| 14 | Registro de execução | RF14 | log de uma execução mostra as 8 categorias |

O RF14 não é a última etapa de verdade — instrumente desde a etapa 1 e vá preenchendo.

---

## 7. Motor de recomendação (RF10), sem ambiguidade

Fórmula do enunciado:

```
Pontuação = ( (Ivis + Icur) / 2 ) * 100 * Iconc
```

### Ivis — índice de visualizações, 0.0 a 1.0
O enunciado aceita duas definições. **Use a vetorial** (reaproveita o RF08 e resolve o
*cold start* de 375 conteúdos sem histórico):

1. Monte o **centroide** do usuário: média dos embeddings dos conteúdos com que ele
   interagiu (visualização, início, conclusão).
2. `Ivis = similaridade de cosseno (centroide, embedding do candidato)`, truncada em `[0, 1]`.
   Com vetores normalizados, `similaridade = 1 - distancia` e `distancia` vem do operador
   `<=>` do pgvector.
3. **Usuário sem histórico:** caia para a definição alternativa do enunciado — proporção do
   tempo consumido na mesma categoria — e registre o fallback no log.

### Icur — índice de curtidas e avaliações, 0.0 a 1.0
Proporção de sinais positivos do usuário na **categoria do candidato**, onde sinal positivo é
`tipo_interacao = 'curtida'` ou avaliação `>= 4` (em `interacoes.avaliacao_atribuida` ou em
`comentarios.avaliacao`). Sem sinal nenhum na categoria, `Icur = 0`.

### Iconc — filtro binário eliminatório
`0` se o usuário **já concluiu** o conteúdo, `1` caso contrário. Zera a pontuação, como o
enunciado determina. Na prática: `EXISTS (interacao WHERE tipo_interacao = 'conclusão')`.

### Classificação
O enunciado escreve a faixa "Estável" como `40 > Pontuação < 70`, que é **impossível de
satisfazer** — erro de digitação evidente. Cruzando com as outras duas faixas, implemente:

```python
if iconc == 0 or pontuacao <= 40:   classificacao = 'Negativo'
elif pontuacao >= 70:               classificacao = 'Positivo'
else:                               classificacao = 'Estável'   # 40 < P < 70
```

**Registre essa interpretação no README.** É uma decisão de equipe sobre um defeito do
enunciado, e vai ser perguntada.

Saída por recomendação, conforme o RF10: usuário, conteúdo recomendado, pontuação, posição e
data de geração. Descarte os `Negativo` da lista de sugestões.

---

## 8. Validação (RF03) — leia antes de implementar

**Os dados de entrada estão limpos.** Zero órfãos, zero duplicatas exatas, zero datas fora do
ISO, zero valores fora de faixa, zero campos ausentes. Se você apenas rodar os validadores
sobre os arquivos reais, o resumo do RF05 sai com **todos os contadores em zero** — e parece
que a validação não foi implementada.

Faça assim:

1. **Validadores como funções puras**, sem banco e sem arquivo:
   `validar_conteudo(registro) -> (classificacao, motivo | None)`, uma por fonte.
   Classificações: `valido`, `invalido`, `incompleto`, `duplicado`.
2. **Teste cada regra do RF03 com um registro sintético inválido** em `tests/`. É isso que
   demonstra a validação na apresentação — um teste por regra: campo obrigatório ausente,
   identificador inválido, data malformada, categórico fora do domínio, avaliação fora de
   1–5, numérico negativo, e referência a usuário/conteúdo inexistente.
3. **Relate honestamente.** Os únicos achados reais são **6 pares (usuario_id, conteudo_id)
   repetidos** em `comentarios.json` e **2** em `interacoes.json`. Devem aparecer no resumo
   como duplicados.

### Duas armadilhas que produzem números errados

> **Não trate `avaliacao_atribuida = null` como incompleto.** São 644 das 1000 interações, e
> a ausência é **semanticamente correta**: só há nota quando o tipo de interação é avaliação.
> Classificar como incompleto infla o contador em 64% e destrói a credibilidade do resumo.

> **Não detecte duplicidade pelo texto do comentário.** Existem apenas **22 textos distintos**
> em 1000 registros — o dado sintético recicla frases. Essa regra marcaria ~978 registros como
> duplicados. A chave natural é o par **(usuario_id, conteudo_id)**.

---

## 9. Métricas, KPIs e dashboard (RF12, RF13)

O RF12 exige **2 métricas operacionais** + **2 KPIs de decisão**, cada KPI com **nome,
objetivo, fórmula, fonte dos dados, periodicidade e interpretação** em
`documentacao/kpis.md`. Exponha tudo como **views** no PostgreSQL (`sql/consultas.sql`) — o
Superset consome view, não código Python.

Sugestões que os dados sustentam:

- **Métrica operacional** — volume de interações por período; conteúdos distintos consumidos.
- **KPI — taxa de conclusão:** `conclusões / inícios`. Decide onde o conteúdo está perdendo gente.
- **KPI — cobertura do catálogo:** conteúdos com alguma interação / total. Hoje seria
  **625/1000**; 135 conteúdos não têm interação **nem** comentário. Indicador direto de
  curadoria.

> **Não use "avaliação média" como KPI de qualidade.** A distribuição é enviesada: média 4,15
> com 79% das notas em 4 ou 5. O indicador quase não varia entre categorias e não discrimina
> nada. Use a **proporção de notas ≤ 2** ou a **distribuição** — informa muito mais.

Para o RF13, justifique cada gráfico pela natureza do dado: série temporal → linhas;
comparação entre categorias → barras; valor único de acompanhamento → cartão. E defina
explicitamente as **2 perguntas de negócio** que o dashboard responde — o enunciado cobra isso.

---

## 10. Regras de qualidade

- `dados/brutos/` **intocado**. Todo tratamento escreve em `dados/processados/`.
- Toda ingestão idempotente: `ON CONFLICT` obrigatório. Rodar duas vezes não pode duplicar.
- `ruff check .` limpo antes de considerar qualquer etapa pronta.
- Testes dos validadores passando (§8).
- Segredos só no `.env`. Nunca em código, log ou README.
- Mensagens de log e commits em português, como o resto do repositório.

---

## 11. Armadilhas conhecidas

| Armadilha | Correção |
|---|---|
| **O PDF do enunciado está truncado** — termina no meio do RF13, sem RF14 nem seções 8–12 | Use o `.docx` em `documentacao/fontes/` |
| Dados limpos zeram os contadores do RF03/RF05 | Validadores puros + testes sintéticos (§8) |
| `avaliacao_atribuida` nula tratada como incompleto | É legítima em 644 registros — não conte |
| Duplicidade detectada por texto de comentário | Só há 22 textos distintos — use (usuario_id, conteudo_id) |
| Superset não enxerga o PostgreSQL | Use `172.17.0.1`, não `localhost`; `host.docker.internal` não resolve |
| Índice HNSW ignorado pelo planejador | O operador do índice tem que casar com o da consulta: `<=>` ↔ `vector_cosine_ops` |
| Reingestão duplicando tudo silenciosamente | `conflito=` em `inserir_df`, `ON CONFLICT` no SQL |
| Pins de ML da apostila não instalam | Python 3.14: exigir wheel `cp314`/`abi3`; `torch` só pelo índice CPU |
| `montar_dashboard` não cria filtros nativos | Estender o método ou adicionar os 2 filtros pela UI (§3.1) |
| Vincular gráfico ao dashboard não o posiciona | Já resolvido no toolkit via `position_json` |
| Tentar editar o compose do Superset | Sem permissão — trabalhe pela API REST |

---

## 12. Checklist final

**Requisitos funcionais**

- [ ] RF01 — roda por `python -m src.main`, config em arquivo, segredos fora do código
- [ ] RF02 — 3 fontes lidas, nome e contagem informados
- [ ] RF03 — todo registro classificado, não-válidos com motivo
- [ ] RF04 — padronizado; originais preservados; tratados em diretório próprio
- [ ] RF05 — resumo JSON com as 8 contagens + tempo total
- [ ] RF06 — 5 entidades, PK/FK/UNIQUE, transação, `criar_banco.sql` entregue
- [ ] RF07 — Mongo com as 5 operações e a justificativa da escolha
- [ ] RF08 — embeddings em pgvector, sem duplicar, modelo registrado
- [ ] RF09 — busca semântica com 3 consultas demonstradas, limite configurável
- [ ] RF10 — recomendação pela fórmula, concluídos removidos
- [ ] RF11 — recomendações persistidas com pontuação, posição e data
- [ ] RF12 — 2 métricas + 2 KPIs, cada KPI com os 6 campos, expostos em views
- [ ] RF13 — 3 cartões + barras + linhas + **2 filtros**, 2 perguntas de negócio, gráficos justificados
- [ ] RF14 — log com as 8 categorias, permitindo achar origem e causa

**Entregáveis (seção 11)**

- [ ] Código de ingestão
- [ ] Arquivos de dados utilizados
- [ ] Modelo conceitual e lógico
- [ ] Scripts do PostgreSQL
- [ ] Documentos e consultas do MongoDB
- [ ] Implementação da busca vetorial
- [ ] Implementação da recomendação
- [ ] **Exportação do dashboard do Superset**
- [ ] Documentação de instalação e execução

**Documentação (seções 9 e 10)**

- [ ] `README.md` com decisões, limitações e instruções de reprodução
- [ ] Decisões registradas: tabela `usuario` derivada · faixa "Estável" corrigida ·
      `Ivis` pela via vetorial · `src/` + árvore da seção 11
- [ ] `documentacao/kpis.md`
- [ ] `documentacao/uso_da_ia.md` — **incluindo erros e inadequações reais das respostas da IA**
- [ ] Dependências registradas · `.env` fora do Git
