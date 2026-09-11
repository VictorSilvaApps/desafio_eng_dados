# Ambiente pronto para o Desafio de Engenharia de Dados

Toolkit reutilizável com tudo o que as Aulas 1–11 cobriram, já instalado, testado
e com as armadilhas conhecidas resolvidas por padrão.

```bash
cd ~/Projetos/desafio_eng_dados && source .venv/bin/activate
```

## Estado dos serviços

| Serviço | Estado | Acesso |
|---|---|---|
| PostgreSQL 18.6 + pgvector 0.8.1 | ativo | `victor@localhost:5432/meu_banco_de_dados` |
| MongoDB 8.0.29 | ativo | `localhost:27017` |
| Apache Superset | ativo | <http://localhost:8088> — `admin`/`admin` |

Tudo já está no `.env` (modo 600, fora do Git).

## Pipeline de referência

Roda de ponta a ponta e serve de molde:

```bash
python exemplo_pipeline.py             # ingestão + embeddings + KPIs
python exemplo_pipeline.py --superset  # cria também o dashboard
python exemplo_pipeline.py --limpar    # remove as tabelas ex_*
```

Testado: 10 vendas e 4 eventos ingeridos, 10 embeddings de 384 dimensões, busca
semântica funcionando, 4 KPIs, e um dashboard de 7 gráficos montado pela API.

## O toolkit

### `toolkit/ingestao.py` — dados entrando

```python
from toolkit import ingestao

ok, msg = ingestao.csv_bem_formado('dados/x.csv')      # valide ANTES
ingestao.ingerir_arquivo('dados/x.csv', 'tabela', pk='id')   # CSV/TSV/XLSX/JSON
ingestao.ingerir_json_bruto('dados/y.json', 'tab_raw', chave='id')  # JSONB
```

Cria a tabela inferindo tipos do arquivo, converte `NaN` em `NULL` e usa
`ON CONFLICT` sempre — reprocessar o mesmo arquivo atualiza, não duplica.

### `toolkit/vetorial.py` — busca semântica

```python
from toolkit import vetorial

vetorial.criar_tabela_vetorial('produtos_vec')                    # 384 dims
vetorial.indexar_textos('produtos_vec', [(1, 'notebook'), ...])
vetorial.buscar('produtos_vec', 'computador portátil', limite=5)
vetorial.criar_indice('produtos_vec', 'cosseno')                  # HNSW
```

Use `MODELO_CLIP` (512 dims) se o desafio envolver imagens.

### `toolkit/kpis.py` — indicadores

```python
from toolkit import kpis

kpis.taxa('chamados', 'status', 'Concluído')       # percentual
kpis.media('vendas', 'valor')                      # média, ignora NULL
kpis.tempo_medio_dias('t', 'abertura', 'conclusao')
kpis.distribuicao('vendas', 'regiao')              # contagem + participação %
kpis.exibir('Receita', 15498.79, ' R$')
kpis.exibir_tabela(linhas, 'Por categoria')
```

### `toolkit/superset.py` — gráficos e dashboard pela API

```python
from toolkit import superset as sup

s  = sup.Superset()
db = s.garantir_banco()
ds = s.garantir_dataset('minha_tabela', db)

receita = sup.m_simples('valor', 'SUM', 'Receita')
c1 = s.criar_grafico('Receita', *sup.kpi(receita, 'total'), ds_id=ds)

s.montar_dashboard('Meu Painel', [
    [(c1, 4), (c2, 4), (c3, 4)],    # linha de KPIs
    [(c4, 6), (c5, 6)],             # gráficos
])
```

Atalhos prontos: `kpi()`, `medidor()`, `barras()`, `linha()`, `rosca()`, `tabela()`.

## Armadilhas já resolvidas

Cada uma custou tempo em alguma aula. O toolkit lida com elas por padrão:

| Onde | O problema | Solução embutida |
|---|---|---|
| CSV | vírgula sem aspas no campo quebra o parse | `csv_bem_formado()` valida antes |
| Ingestão | reprocessar duplica, às vezes em silêncio | `ON CONFLICT` obrigatório |
| Agregações | `AVG` de coluna vazia devolve `NULL` e estoura a formatação | `NULLIF` e checagem de `None` |
| Gráficos | agregar coluna opcional cria a categoria "null" | `distribuicao()` ignora nulos |
| URI SQLAlchemy | senha com `#` trunca a URI silenciosamente | `uri_sqlalchemy()` faz percent-encode |
| Superset → Postgres | `localhost` aponta para o próprio contêiner | usa `172.17.0.1` (gateway do Docker) |
| Superset API | POST exige CSRF com o cookie da mesma sessão | cliente mantém cookie jar |
| Dashboard | vincular gráfico não o posiciona; abre vazio | `montar_dashboard()` grava `position_json` + `chart_configuration` |
| pgvector | índice `l2_ops` não serve consulta `<=>` | `criar_indice()` casa operador e métrica |
| psql | pager trava scripts com várias consultas | use `-P pager=off` |

## Quando o desafio chegar

1. Coloque os arquivos em `dados/`.
2. Copie `exemplo_pipeline.py` para `desafio.py`.
3. Troque os nomes de tabela, os KPIs e os gráficos.
4. Rode. Se aparecer algo novo, o toolkit é só um ponto de partida — edite à vontade.

Consulte também os projetos anteriores, que têm os roteiros completos de cada aula:

```
~/Projetos/eng_dados_aula01/   PostgreSQL, usuário, acesso externo
~/Projetos/eng_dados_aula02/   ingestão CSV/JSON com psycopg2
~/Projetos/eng_dados_aula03/   JSONB e MongoDB
~/Projetos/eng_dados_aula04/   pgvector e busca vetorial
~/Projetos/eng_dados_aula08/   pipeline de recomendação
~/Projetos/eng_dados_superset/ gráficos, KPIs e dashboards
~/Projetos/eng_dados_extra_clip/ busca multimodal com CLIP
```

## Verificação rápida do ambiente

```bash
python -c "
from toolkit.db import consultar
from toolkit.superset import Superset
print('postgres:', consultar('SELECT version()')[0]['version'][:30])
print('superset:', 'ok' if Superset().token else 'falhou')
"
```
