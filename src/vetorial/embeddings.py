"""Geração dos embeddings do catálogo (RF08).

O texto de cada conteúdo é `título. descrição` — as descrições têm entre
286 e 348 caracteres, tamanho bom para o modelo, e o título acrescenta os
termos que a descrição às vezes não repete.

`toolkit.vetorial.indexar_textos` faz o trabalho: gera os vetores com o
modelo em cache e grava com `ON CONFLICT DO UPDATE`, então rodar duas
vezes atualiza em vez de duplicar — que é o que o RF08 exige.

**Duas coisas que o toolkit não faz e são feitas aqui:**

1. `indexar_textos` grava `id`, `conteudo` e `embedding`, mas não a coluna
   `modelo`. O RF08 exige registrar qual modelo produziu cada vetor, então
   o `UPDATE` logo depois preenche `modelo` e `gerado_em`.
2. `toolkit.vetorial.criar_indice` **não** é chamado de propósito: ele
   monta o nome do índice interpolando o nome da tabela, e com a tabela
   qualificada pelo schema (`desafio.conteudo_embedding`) o nome sairia
   `idx_desafio.conteudo_embedding_embedding` — identificador inválido,
   por causa do ponto. O índice HNSW já é criado pelo `sql/criar_banco.sql`,
   com `vector_cosine_ops`, casando com o operador `<=>` da consulta.
"""

from toolkit.db import consultar, executar
from toolkit.vetorial import indexar_textos

from ..log import Registro


def texto_do_conteudo(conteudo: dict) -> str:
    return f'{conteudo["titulo"]}. {conteudo["descricao"]}'


def gerar(tabela: str, conteudos: list[dict], modelo: str,
          registro: Registro, resumo) -> int:
    """Gera e grava um embedding por conteúdo válido."""
    itens = [(c['conteudo_id'], texto_do_conteudo(c)) for c in conteudos]
    if not itens:
        registro.falha('embedding', tabela, 'nenhum conteúdo válido para indexar')
        return 0

    try:
        n = indexar_textos(tabela, itens, modelo=modelo)
        # RF08: registrar o modelo que produziu os vetores.
        executar(f'UPDATE {tabela} SET modelo = %s, gerado_em = now() '
                 f'WHERE modelo IS DISTINCT FROM %s', (modelo, modelo))
    except Exception as erro:
        registro.falha('embedding', tabela, erro)
        raise

    resumo.carregado('pgvector', tabela.split('.')[-1], n)
    registro._anunciar(f'{n} embeddings gravados com o modelo {modelo}')
    return n


def conferir(tabela: str, esperado: int, registro: Registro) -> dict:
    """Confere o que ficou gravado: total, dimensão e modelo registrado."""
    linha = consultar(f"""
        SELECT COUNT(*)                        AS total,
               COUNT(DISTINCT modelo)          AS modelos,
               MIN(modelo)                     AS modelo,
               MIN(vector_dims(embedding))     AS dimensoes,
               COUNT(*) FILTER (WHERE embedding IS NULL) AS sem_vetor
          FROM {tabela}
    """)[0]

    if linha['total'] != esperado:
        registro.falha('embedding', tabela,
                       f'gravados {linha["total"]}, esperados {esperado}',
                       'algum conteúdo válido ficou sem vetor — confira se a '
                       'lista de entrada veio filtrada')
    return linha
