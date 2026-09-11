"""Carga e consultas no MongoDB (RF07).

**O que foi para o Mongo e por quê.** Só os comentários. Eles são o único
dado do desafio com forma de documento: texto livre de tamanho variável
mais um array de tags. Num modelo relacional, `tags` exigiria uma tabela
de associação e um JOIN para a pergunta mais comum ("quais comentários
têm a tag X"); no Mongo é um índice sobre array e uma consulta direta.

O que **não** foi: catálogo, interações e recomendações. Esses são fatos
estruturados, de schema fixo, que precisam de chave estrangeira,
integridade referencial e agregação com JOIN — exatamente o que o
PostgreSQL faz melhor.

Cada documento carrega `categoria` e `tipo` do conteúdo, copiados do
catálogo. É desnormalização deliberada: sem ela, a quinta operação do
RF07 (agregar quantidade por categoria) precisaria de dado que só existe
no outro banco.
"""

from ..log import Registro

CHAVE = '_id'


def _documento(comentario: dict, conteudo: dict) -> dict:
    """Monta o documento a partir do comentário tratado + dados do conteúdo.

    O `_id` é determinístico: reprocessar o mesmo comentário sobrescreve
    o documento em vez de criar outro. A validação já garantiu que o par
    (usuario_id, conteudo_id) é único entre os registros carregados.
    """
    return {
        '_id': f'{comentario["usuario_id"]}-{comentario["conteudo_id"]}',
        'usuario_id': comentario['usuario_id'],
        'conteudo_id': comentario['conteudo_id'],
        'avaliacao': comentario['avaliacao'],
        'comentario': comentario['comentario'],
        'tags': comentario['tags'],
        'data': comentario['data'].isoformat(),
        # desnormalizado do catálogo, para a agregação do RF07
        'categoria': conteudo['categoria'],
        'tipo': conteudo['tipo'],
        'titulo': conteudo['titulo'],
    }


def carregar(colecao_nome: str, comentarios: list[dict], conteudos: list[dict],
             registro: Registro, resumo) -> int:
    """Operação 1 do RF07: inserir os comentários. Idempotente."""
    from pymongo import ReplaceOne

    from toolkit.db import conectar_mongo

    por_id = {c['conteudo_id']: c for c in conteudos}
    try:
        bd = conectar_mongo()
        colecao = bd[colecao_nome]

        operacoes = [
            ReplaceOne({CHAVE: doc[CHAVE]}, doc, upsert=True)
            for doc in (_documento(c, por_id[c['conteudo_id']])
                        for c in comentarios
                        if c['conteudo_id'] in por_id)
        ]
        if operacoes:
            colecao.bulk_write(operacoes, ordered=False)

        colecao.create_index('conteudo_id')
        colecao.create_index('tags')
        colecao.create_index('avaliacao')

        total = colecao.count_documents({})
    except Exception as erro:
        registro.falha('conexao', f'mongodb/{colecao_nome}', erro)
        raise

    resumo.carregado('mongodb', colecao_nome, len(operacoes))
    registro._anunciar(f'{colecao_nome}: {len(operacoes)} documentos '
                       f'({total} na coleção)')
    return len(operacoes)


# ── as outras quatro operações do RF07 ────────────────────────
def comentarios_do_conteudo(colecao_nome: str, conteudo_id: int) -> list[dict]:
    """Operação 2: todos os comentários de um conteúdo."""
    from toolkit.db import conectar_mongo
    return list(conectar_mongo()[colecao_nome]
                .find({'conteudo_id': conteudo_id})
                .sort('data', -1))


def por_tag(colecao_nome: str, tag: str, limite: int = 10) -> list[dict]:
    """Operação 3: localizar por tag. O índice sobre array resolve direto."""
    from toolkit.db import conectar_mongo
    return list(conectar_mongo()[colecao_nome]
                .find({'tags': tag.casefold()})
                .limit(limite))


def por_nota(colecao_nome: str, minimo: int = 1, maximo: int = 5,
             limite: int = 10) -> list[dict]:
    """Operação 4: filtrar por faixa de nota."""
    from toolkit.db import conectar_mongo
    return list(conectar_mongo()[colecao_nome]
                .find({'avaliacao': {'$gte': minimo, '$lte': maximo}})
                .limit(limite))


def quantidade_por_categoria(colecao_nome: str) -> list[dict]:
    """Operação 5: agregar quantidade e nota média por categoria."""
    from toolkit.db import conectar_mongo
    return list(conectar_mongo()[colecao_nome].aggregate([
        {'$group': {
            '_id': '$categoria',
            'comentarios': {'$sum': 1},
            'nota_media': {'$avg': '$avaliacao'},
            'insatisfeitos': {'$sum': {'$cond': [{'$lte': ['$avaliacao', 2]}, 1, 0]}},
        }},
        {'$project': {
            '_id': 0, 'categoria': '$_id', 'comentarios': 1,
            'nota_media': {'$round': ['$nota_media', 2]}, 'insatisfeitos': 1,
        }},
        {'$sort': {'comentarios': -1}},
    ]))


def demonstrar(colecao_nome: str, registro: Registro) -> dict:
    """Roda as cinco operações e devolve as saídas, para evidência do RF07."""
    agregado = quantidade_por_categoria(colecao_nome)
    exemplo = agregado[0]['categoria'] if agregado else None

    saidas = {
        '2_comentarios_do_conteudo_1': comentarios_do_conteudo(colecao_nome, 1),
        '3_por_tag_lgpd': por_tag(colecao_nome, 'lgpd', limite=5),
        '4_notas_baixas_1_a_2': por_nota(colecao_nome, 1, 2, limite=5),
        '5_quantidade_por_categoria': agregado,
    }
    registro._anunciar(
        f'RF07: 5 operações executadas — {len(agregado)} categorias agregadas'
        + (f', maior volume em {exemplo}' if exemplo else ''))
    return saidas
