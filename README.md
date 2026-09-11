# Desafio Prático 1 — Pipeline de Recomendação e Dashboard de Conteúdos Educacionais

FIC DEV IA · Fundamentos de Dados para IA · Grupo 6 — Pedro Gomes, Victor Silva, Kristiann Rocha

Pipeline reprodutível que integra **ingestão → PostgreSQL + MongoDB → embeddings/pgvector
→ recomendação → dashboard no Superset**, atendendo os requisitos RF01 a RF14 do enunciado
em [`documentacao/fontes/`](documentacao/fontes/).

## Como rodar

```bash
bash setup.sh && cp .env.example .env && nano .env
```

```bash
source .venv/bin/activate && python -m src.main
```

Roda de ponta a ponta em ~27s (a maior parte são os embeddings). Sem argumento
obrigatório. Para parar numa etapa: `python -m src.main --ate carga`. Etapas
disponíveis: `leitura`, `validacao`, `tratamento`, `carga`, `mongo`, `embeddings`,
`busca`, `recomendacao`, `dashboard`.

Os testes e o lint:

```bash
python -m pytest tests/ -q && ruff check src tests
```

## O que sai de uma execução

| Saída | Onde |
|---|---|
| Resumo da ingestão (RF05) | `saida/resumo_ingestao.json` |
| Registro de execução (RF14) | `saida/execucao.json` |
| Dados tratados (RF04) | `dados/processados/` |
| Busca semântica (RF09) | `saida/buscas.json` |
| Export do dashboard (RF13) | `dashboard/desafio_1.zip` |
| Dashboard no ar | <http://localhost:8088> |

Última execução verificada: 3000 registros lidos, 2994 válidos, 6 duplicados,
1000 embeddings de 384 dimensões, 1500 recomendações, dashboard com 6 gráficos e
2 filtros. Zero falhas.

## Estrutura

```
├── config.yaml              parâmetros (RF01) — sem segredo
├── .env                     segredos, fora do Git
├── src/
│   ├── main.py              orquestra as 9 etapas  →  python -m src.main
│   ├── config.py            carrega config.yaml + .env
│   ├── log.py               registro de execução (RF14)
│   ├── ingestao/            leitura, validacao, tratamento, resumo (RF02–RF05)
│   ├── carga/               postgres.py (RF06), mongo.py (RF07)
│   ├── vetorial/            embeddings.py (RF08), busca.py (RF09)
│   ├── recomendacao/        motor.py (RF10, RF11)
│   └── dashboard/           montar.py (RF13)
├── sql/
│   ├── criar_banco.sql      DDL das 6 tabelas (RF06, RF11)
│   └── consultas.sql        views de métricas e KPIs (RF12)
├── mongodb/consultas.js     as 5 operações do RF07
├── dados/brutos/            originais, somente leitura (444)
├── dados/processados/       saída do tratamento
├── documentacao/            enunciado, levantamento, KPIs, uso da IA
├── tests/                   50 testes dos validadores e do tratamento
└── toolkit/                 biblioteca da equipe, reaproveitada pelo pipeline
```

## Decisões de equipe

O enunciado deixa pontos em aberto e tem dois defeitos reais. Cada decisão abaixo foi
registrada porque **vai ser perguntada na apresentação**.

### Do levantamento de requisitos

| # | Situação | Decisão |
|---|---|---|
| **G1** | Nenhuma das 3 fontes traz dados de usuário, só o `usuario_id`, mas o RF06 exige a entidade | Tabela `usuario` **derivada** dos ids distintos das fontes JSON (150, contíguos de 1 a 150), com primeira e última atividade calculadas |
| **G3** | O enunciado escreve a faixa "Estável" como `40 > Pontuação < 70`, impossível de satisfazer | Adotado `40 < P < 70`, cruzando com `Positivo (>= 70)` e `Negativo (<= 40)`. Erro de digitação evidente |
| **G4** | `Ivis` tem duas definições no enunciado | Usada a **via vetorial** (centroide dos embeddings × candidato). Reaproveita o RF08 e cobre os 375 conteúdos sem histórico. Usuário sem histórico cai para a proporção de tempo por categoria, registrada no log |
| **G5** | RF01 exige `python -m src.main`; a árvore da seção 11 não tem `src/` | Atendidos os dois: código em `src/`, pastas de artefato como a seção 11 pede. O RF01 é obrigatório; a seção 11 se diz "sugerida" |
| **G6** | O Superset não pertence à equipe e o `docker-compose` é ilegível para o usuário atual | Toda automação via API REST em `:8088` |

### Tomadas durante a implementação

| Situação | Decisão |
|---|---|
| **`Icur` é ambíguo.** "Proporção de sinais positivos na categoria do candidato" não diz sobre o que é a proporção | Adotado `positivos na categoria ÷ sinais do usuário naquela categoria`. A leitura alternativa (dividir pelo total do usuário) vira distribuição que soma 1: com 8 categorias a média cai para 0,125 e quase tudo seria classificado como Negativo |
| **Sem permissão para criar banco** (`rolcreatedb = false`) | Schema `desafio` dentro do banco das aulas. Isola das 13 tabelas dos exercícios, permite recriar do zero e não exige sudo |
| **Duplicidade em `interacao`** | A chave **não** é `(usuario_id, conteudo_id)`: o mesmo usuário visualizar e depois concluir o mesmo conteúdo são dois fatos legítimos. A chave é `(usuario_id, conteudo_id, tipo_interacao, data_hora)`. Em `comentarios`, aí sim, é `(usuario_id, conteudo_id)` — e são os 6 duplicados reais |
| **811 títulos distintos em 1000 conteúdos** | Não são duplicatas: têm id, autor e carga diferentes. Ficam todos no banco e todos recebem embedding. Mas como o vetor é feito de título + descrição (RF08), títulos iguais geram vetores iguais e a lista sairia repetida — então busca e recomendação **deduplicam por título na exibição**, mantendo o melhor exemplar |
| **Leitura sem pandas na ingestão** | O RF03 manda validar formato de data e faixa numérica; o pandas converte isso na leitura e apaga o defeito antes do validador ver. A ingestão lê `list[dict]` cru; o pandas e o toolkit entram na carga |
| **Carga sem `toolkit.ingestao.inserir_df`** | Ele abre a própria conexão por chamada, então cada tabela seria uma transação. O RF06 exige rollback de tudo — a carga usa um cursor único |
| **Filtros do Superset** | `toolkit.superset.montar_dashboard` grava `native_filter_configuration: []` fixo. Em vez de alterar o toolkit (compartilhado com as outras aulas), os 2 filtros entram num segundo PUT por cima |
| **O que foi para o MongoDB** | Só os comentários: texto livre + array de tags, forma de documento. Catálogo, interações e recomendações ficam no PostgreSQL, onde precisam de FK e JOIN. Cada documento carrega `categoria` e `tipo` desnormalizados, sem o que a agregação do RF07 dependeria do outro banco |

## Limitações conhecidas

- **Os dados de entrada estão limpos.** Zero órfãos, zero datas inválidas, zero valores
  fora de faixa. Os contadores do RF03/RF05 saem quase todos zerados — o que a validação
  faz está provado pelos **50 testes** com registros sintéticos em [`tests/`](tests/),
  não pelos arquivos reais.
- **A taxa de conclusão passa de 100% em duas categorias.** Nem toda conclusão é
  precedida de um `início` registrado. É propriedade do dado; preferimos mostrar do que
  truncar e esconder.
- **As avaliações são enviesadas** (média 4,15, 79% em 4 ou 5). Por isso não usamos
  "avaliação média" como KPI de qualidade — ver [`documentacao/kpis.md`](documentacao/kpis.md).
- **Cold start**: 135 conteúdos não têm interação nem comentário. A escolha do `Ivis`
  vetorial mitiga, porque a similaridade textual existe para os 1000.
- **As recomendações acumulam por lote.** Cada execução grava um `gerado_em` novo, de
  propósito, para guardar o histórico. Para ver só a última:
  `SELECT * FROM desafio.vw_recomendacoes WHERE gerado_em = (SELECT MAX(gerado_em) FROM desafio.recomendacao)`.

## Requisitos atendidos

| RF | Onde | RF | Onde |
|---|---|---|---|
| RF01 | `config.yaml`, `src/config.py`, `src/main.py` | RF08 | `src/vetorial/embeddings.py` |
| RF02 | `src/ingestao/leitura.py` | RF09 | `src/vetorial/busca.py` |
| RF03 | `src/ingestao/validacao.py` + `tests/` | RF10 | `src/recomendacao/motor.py` |
| RF04 | `src/ingestao/tratamento.py` | RF11 | `motor.persistir` + `sql/criar_banco.sql` |
| RF05 | `src/ingestao/resumo.py` | RF12 | `sql/consultas.sql`, `documentacao/kpis.md` |
| RF06 | `sql/criar_banco.sql`, `src/carga/postgres.py` | RF13 | `src/dashboard/montar.py` |
| RF07 | `src/carga/mongo.py`, `mongodb/consultas.js` | RF14 | `src/log.py` |

Checklist item a item: [`documentacao/instrucoes_para_ia.md`](documentacao/instrucoes_para_ia.md), seção 12.
Registro do uso de IA (seção 10 do enunciado): [`documentacao/uso_da_ia.md`](documentacao/uso_da_ia.md).

## Ambiente

Verificado nesta máquina: PostgreSQL 18.6, pgvector 0.8.1, MongoDB 8 em
`127.0.0.1:27017`, Superset 6.1.0 em Docker (`:8088`), Python **3.14.4** (único
disponível), modelo `paraphrase-multilingual-MiniLM-L12-v2` já em cache.

> **Não crie um venv novo nem atualize pins.** A máquina só tem Python 3.14 e pins
> antigos de bibliotecas de ML não têm wheel `cp314` — a instalação quebra. Se precisar
> instalar algo, confira antes se há wheel `cp314`/`abi3`/`py3-none-any` no PyPI, e
> instale `torch` apenas pelo índice CPU.

<details>
<summary>Instalação do PostgreSQL, pgvector, MongoDB e Superset</summary>

```bash
sudo apt install -y postgresql postgresql-contrib postgresql-18-pgvector
```

```bash
sudo -u postgres psql -c "CREATE USER seu_usuario;" -c "CREATE DATABASE meu_banco_de_dados OWNER seu_usuario;"
```

```bash
sudo -u postgres psql -d meu_banco_de_dados -c 'CREATE EXTENSION vector;'
```

Desde o PostgreSQL 15 o `GRANT ALL ON DATABASE` **não** dá permissão de criar tabelas —
é preciso ser dono do banco. E a extensão `vector` exige superusuário para ser criada,
mesmo sendo usada depois por usuário comum.

```bash
curl -fsSL https://pgp.mongodb.com/server-8.0.asc | sudo gpg --yes --dearmor -o /usr/share/keyrings/mongodb-archive-keyring.gpg
```

```bash
echo "deb [ arch=amd64 signed-by=/usr/share/keyrings/mongodb-archive-keyring.gpg ] https://repo.mongodb.org/apt/ubuntu noble/mongodb-org/8.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-8.0.list
```

```bash
sudo apt update && sudo apt install -y mongodb-org && sudo systemctl enable --now mongod
```

Use o codename **`noble`** mesmo no Ubuntu 26.04: o repositório do `resolute` existe e
responde, mas não contém o `mongodb-org` — o `apt install` falha depois de um `apt
update` que passou sem erro.

O Superset **não roda em Python 3.13+**, por isso Docker:

```bash
sudo docker run -d --name superset --network host -e SUPERSET_SECRET_KEY="$(openssl rand -base64 42)" apache/superset:6.1.0
```

Com `--network host`, ajuste `SUPERSET_DB_HOST=localhost` no `.env`; com rede bridge,
mantenha `172.17.0.1` — dentro do contêiner, `localhost` é o próprio contêiner e
`host.docker.internal` não resolve nesta máquina.
</details>

## Trabalhando em equipe

Cada pessoa trabalha na sua branch e abre PR para a `main`:

```bash
git checkout -b feat/minha-parte && git push -u origin feat/minha-parte
```

Commits semânticos: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`.

**Nunca commite o `.env`** — está no `.gitignore`, e cada pessoa tem a sua senha local.
Variável nova entra no `.env.example` sem valor, para os outros saberem que existe.

> A seção 12 do enunciado avisa que **qualquer integrante** pode ser chamado a explicar
> **qualquer parte**. Dividir o trabalho não dispensa entender o todo — as decisões
> acima são o roteiro mínimo de estudo.

## Armadilhas já resolvidas

| Onde | O problema | Onde está resolvido |
|---|---|---|
| CSV | vírgula sem aspas quebra o parse | `csv_bem_formado()` valida antes |
| Ingestão | reprocessar duplica, em silêncio | `ON CONFLICT` em toda carga |
| Git | `core.autocrlf` troca CRLF por LF e o arquivo versionado deixa de bater com a origem | `.gitattributes` com `-text` nas fontes |
| Superset → Postgres | `localhost` aponta para o próprio contêiner | `172.17.0.1` via `SUPERSET_DB_HOST` |
| Superset API | POST exige CSRF com o cookie da mesma sessão | cliente do toolkit mantém cookie jar |
| Dashboard | vincular gráfico não o posiciona | `montar_dashboard()` grava `position_json` |
| Dashboard | `native_filter_configuration` fixo em `[]` | segundo PUT em `src/dashboard/montar.py` |
| pgvector | índice `l2_ops` não serve consulta `<=>` | `vector_cosine_ops` no DDL |
| pgvector | `criar_indice()` do toolkit gera nome inválido com tabela qualificada por schema | índice criado no `sql/criar_banco.sql` |
| URI SQLAlchemy | senha com `#` trunca a URI | `uri_sqlalchemy()` faz percent-encode |
| psql | pager trava scripts com várias consultas | use `-P pager=off` |
