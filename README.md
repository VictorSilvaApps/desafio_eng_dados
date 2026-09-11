# Desafio de Engenharia de Dados — Toolkit da Equipe

Base comum para o desafio: ingestão, armazenamento (relacional, JSONB e vetorial),
cálculo de indicadores e dashboards no Superset. Reúne o que foi visto nas Aulas 1–11,
com as armadilhas de cada uma já resolvidas por padrão.

## Começando

```bash
git clone <url-deste-repo> && cd desafio_eng_dados && bash setup.sh
```

O `setup.sh` cria o venv, instala as dependências e **diz o que está faltando** —
ele não instala serviço nenhum com `sudo`, isso fica a seu critério.

Depois, preencha a senha do banco:

```bash
nano .env      # DB_PASSWORD=
```

E confirme que funciona:

```bash
source .venv/bin/activate && python exemplo_pipeline.py
```

## Serviços necessários

| Serviço | Obrigatório | Como instalar (Ubuntu) |
|---|---|---|
| PostgreSQL 18 | sim | `sudo apt install postgresql postgresql-contrib` |
| pgvector | se houver busca semântica | `sudo apt install postgresql-18-pgvector` |
| MongoDB | só se o desafio pedir NoSQL | repositório oficial — veja abaixo |
| Apache Superset | para os dashboards | Docker — veja abaixo |

<details>
<summary>Instalação do PostgreSQL e criação do usuário</summary>

```bash
sudo apt install -y postgresql postgresql-contrib postgresql-18-pgvector
```

```bash
sudo -u postgres psql -c "CREATE USER seu_usuario;" -c "CREATE DATABASE meu_banco_de_dados OWNER seu_usuario;"
```

```bash
sudo -u postgres psql -c '\password seu_usuario'
```

```bash
sudo -u postgres psql -d meu_banco_de_dados -c 'CREATE EXTENSION vector;'
```

Duas coisas que não são óbvias: desde o PostgreSQL 15 o `GRANT ALL ON DATABASE` **não**
dá permissão de criar tabelas — é preciso ser dono do banco (por isso o `OWNER` acima).
E a extensão `vector` exige superusuário para ser criada, mesmo sendo usada depois por
usuário comum.
</details>

<details>
<summary>Instalação do MongoDB</summary>

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
responde, mas contém só 1 pacote — o `mongodb-org` não está lá, e o `apt install` falha
com "package not found" depois de um `apt update` que passou sem erro.

Se o serviço não subir em kernel 6.19+, o pacote define
`GLIBC_TUNABLES=glibc.pthread.rseq=0` na unit, e é essa variável que dispara a recusa:

```bash
sudo mkdir -p /etc/systemd/system/mongod.service.d && printf '[Service]\nUnsetEnvironment=GLIBC_TUNABLES\n' | sudo tee /etc/systemd/system/mongod.service.d/kernel.conf && sudo systemctl daemon-reload && sudo systemctl restart mongod
```
</details>

<details>
<summary>Instalação do Superset</summary>

O Superset **não roda em Python 3.13+** — a 6.1.0 suporta 3.10 a 3.12. Por isso Docker:

```bash
sudo apt install -y docker.io && sudo systemctl enable --now docker && sudo usermod -aG docker $USER
```

```bash
sudo docker run -d --name superset --network host -e SUPERSET_SECRET_KEY="$(openssl rand -base64 42)" apache/superset:6.1.0
```

```bash
sudo docker exec -it superset superset fab create-admin --username admin --firstname Admin --lastname User --email admin@example.com --password admin
```

```bash
sudo docker exec superset superset db upgrade && sudo docker exec superset superset init
```

Acesse <http://localhost:8088> com `admin`/`admin`. Se usar `--network host`, ajuste
`SUPERSET_DB_HOST=localhost` no `.env`; com rede bridge, mantenha `172.17.0.1`.
</details>

## Trabalhando em equipe

Cada pessoa trabalha na sua branch e abre PR para a `main`:

```bash
git checkout -b feat/minha-parte && git push -u origin feat/minha-parte
```

Commits semânticos: `feat:` nova funcionalidade, `fix:` correção, `docs:` documentação,
`chore:` manutenção, `refactor:` reestruturação sem mudança de comportamento.

**Nunca commite o `.env`** — ele está no `.gitignore`, e cada pessoa tem a sua senha
local. Se precisar adicionar uma variável nova, acrescente ao `.env.example` (sem valor)
para os outros saberem que ela existe.

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

## Verificação rápida do ambiente

```bash
python -c "
from toolkit.db import consultar
print('postgres:', consultar('SELECT version()')[0]['version'][:40])
"
```

```bash
python -c "
from toolkit.superset import Superset
print('superset:', 'ok' if Superset().token else 'falhou')
"
```

## Origem

Construído ao longo das Aulas 1 a 11 de Engenharia de Dados do FIC DEV IA. Os
roteiros completos de cada aula ficam nos projetos individuais; aqui está só o que
é reutilizável no desafio.
