"""Carga no PostgreSQL (RF06).

**Por que não usamos `toolkit.ingestao.inserir_df` aqui.** Ele abre a
própria conexão a cada chamada, então cada tabela viraria uma transação
independente: uma falha ao carregar `interacao` deixaria `categoria`,
`usuario` e `conteudo` já gravados. O RF06 exige carga em transação, com
rollback quando algo quebra no meio. Por isso a inserção acontece toda
sobre **um único cursor**, com o mesmo `execute_values` que o toolkit usa
por dentro, e a conexão continua vindo de `toolkit.db.conectar`.

A ordem de carga respeita as chaves estrangeiras: categoria e usuario
primeiro, conteudo depois, interacao por último.
"""

from contextlib import closing
from pathlib import Path

from psycopg2.extras import execute_values

from toolkit.db import conectar

from ..log import Registro

RAIZ = Path(__file__).resolve().parent.parent.parent
DDL = RAIZ / 'sql' / 'criar_banco.sql'
VIEWS = RAIZ / 'sql' / 'consultas.sql'

# Ordem de carga = ordem das dependências de chave estrangeira.
ORDEM = ('categoria', 'usuario', 'conteudo', 'interacao')

CONFLITO = {
    'categoria': 'categoria_id',
    'usuario': 'usuario_id',
    'conteudo': 'conteudo_id',
    'interacao': 'usuario_id, conteudo_id, tipo_interacao, data_hora',
}


def aplicar_ddl(schema: str, registro: Registro) -> None:
    """Executa sql/criar_banco.sql. Idempotente."""
    sql = DDL.read_text(encoding='utf-8')
    try:
        with closing(conectar()) as conn, conn, conn.cursor() as cur:
            cur.execute(sql)
    except Exception as erro:
        registro.falha('persistencia', str(DDL), erro,
                       'DDL não aplicou — confira se a extensão vector existe '
                       'no banco (a criação dela exige superusuário)')
        raise
    registro._anunciar(f'schema {schema} criado/conferido a partir de {DDL.name}')


def aplicar_views(registro: Registro) -> None:
    """Executa sql/consultas.sql (RF12). Roda depois da carga.

    As views são `CREATE OR REPLACE`, então aplicar de novo só atualiza a
    definição — nenhum dado é tocado.
    """
    try:
        with closing(conectar()) as conn, conn, conn.cursor() as cur:
            cur.execute(VIEWS.read_text(encoding='utf-8'))
    except Exception as erro:
        registro.falha('persistencia', str(VIEWS), erro,
                       'as views dependem das tabelas carregadas — confira se '
                       'a carga terminou antes desta etapa')
        raise
    registro._anunciar(f'views de métricas e KPIs aplicadas ({VIEWS.name})')


def _inserir(cur, tabela: str, registros: list[dict], conflito: str) -> int:
    """INSERT ... ON CONFLICT DO UPDATE sobre um cursor já aberto.

    O `ON CONFLICT` é o que torna a carga idempotente: rodar o pipeline
    duas vezes atualiza as linhas em vez de duplicá-las.
    """
    if not registros:
        return 0
    colunas = list(registros[0])
    chaves = {c.strip() for c in conflito.split(',')}
    sets = ', '.join(f'{c} = EXCLUDED.{c}' for c in colunas if c not in chaves)

    sql = (f'INSERT INTO {tabela} ({", ".join(colunas)}) VALUES %s '
           f'ON CONFLICT ({conflito}) ' +
           (f'DO UPDATE SET {sets}' if sets else 'DO NOTHING'))

    execute_values(cur, sql,
                   [tuple(r[c] for c in colunas) for r in registros],
                   page_size=500)
    return len(registros)


def carregar(schema: str, tabelas: dict[str, list[dict]],
             registro: Registro, resumo) -> dict[str, int]:
    """Carrega todas as tabelas numa única transação (RF06).

    Se qualquer tabela falhar, nenhuma é gravada — o `with conn` do
    psycopg2 faz commit no fim do bloco e rollback se houver exceção.
    """
    carregados: dict[str, int] = {}
    try:
        with closing(conectar()) as conn, conn, conn.cursor() as cur:
            cur.execute(f'SET search_path TO {schema}, public')
            for tabela in ORDEM:
                n = _inserir(cur, tabela, tabelas.get(tabela, []), CONFLITO[tabela])
                carregados[tabela] = n
                resumo.carregado('postgresql', tabela, n)
                registro._anunciar(f'{tabela}: {n} registros carregados')
    except Exception as erro:
        registro.falha('persistencia', 'carga no PostgreSQL', erro,
                       'a transação inteira foi revertida — nenhuma tabela '
                       'ficou parcialmente carregada')
        raise
    return carregados


def preparar_tabelas(conteudos: list[dict], interacoes: list[dict],
                     categorias: list[dict], usuarios: list[dict]) -> dict:
    """Converte os registros tratados no formato exato de cada tabela.

    O catálogo guarda `categoria` como texto; a tabela `conteudo` guarda
    `categoria_id`. A troca acontece aqui, uma vez, com o mapa vindo da
    dimensão recém-derivada.
    """
    id_por_nome = {c['nome']: c['categoria_id'] for c in categorias}

    linhas_conteudo = []
    for c in conteudos:
        linha = {k: v for k, v in c.items() if k != 'categoria'}
        linha['categoria_id'] = id_por_nome[c['categoria']]
        linhas_conteudo.append(linha)

    return {
        'categoria': categorias,
        'usuario': usuarios,
        'conteudo': linhas_conteudo,
        'interacao': interacoes,
    }
