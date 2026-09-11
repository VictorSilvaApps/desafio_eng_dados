"""Embeddings e busca vetorial com pgvector.

O modelo padrão é o mesmo das Aulas 16/17 (384 dimensões), já em cache.
Para imagem ou busca multimodal, use MODELO_CLIP (512 dimensões).
"""

from .db import conectar

MODELO_TEXTO = 'paraphrase-multilingual-MiniLM-L12-v2'   # 384 dims
MODELO_CLIP  = 'clip-ViT-B-32'                           # 512 dims, texto+imagem
DIMENSOES = {MODELO_TEXTO: 384, MODELO_CLIP: 512}

_modelos: dict = {}


def obter_modelo(nome: str = MODELO_TEXTO):
    if nome not in _modelos:
        from sentence_transformers import SentenceTransformer
        print(f'  carregando {nome}...')
        _modelos[nome] = SentenceTransformer(nome)
    return _modelos[nome]


def vetor_sql(v) -> str:
    """Formato textual que o pgvector aceita: '[0.1,0.2,...]'."""
    return '[' + ','.join(f'{float(x):.6f}' for x in v) + ']'


def criar_tabela_vetorial(tabela: str, modelo: str = MODELO_TEXTO,
                          colunas_extra: str = '') -> None:
    """Cria tabela com coluna `embedding` do tamanho certo do modelo."""
    dims = DIMENSOES[modelo]
    extra = f',\n    {colunas_extra}' if colunas_extra else ''
    with conectar() as conn, conn.cursor() as cur:
        cur.execute('CREATE EXTENSION IF NOT EXISTS vector')
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {tabela} (
                id        INT PRIMARY KEY,
                conteudo  TEXT,
                embedding vector({dims}){extra}
            )""")


def indexar_textos(tabela: str, itens: list[tuple[int, str]],
                   modelo: str = MODELO_TEXTO) -> int:
    """Gera embeddings e grava. `itens` = [(id, texto), ...]."""
    m = obter_modelo(modelo)
    ids, textos = zip(*itens, strict=True)
    embs = m.encode(list(textos), normalize_embeddings=True,
                    show_progress_bar=len(textos) > 50)

    with conectar() as conn, conn.cursor() as cur:
        for i, texto, emb in zip(ids, textos, embs, strict=True):
            cur.execute(f"""
                INSERT INTO {tabela} (id, conteudo, embedding)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                   SET conteudo = EXCLUDED.conteudo,
                       embedding = EXCLUDED.embedding
            """, (i, texto, vetor_sql(emb)))
    return len(itens)


def buscar(tabela: str, consulta: str, limite: int = 5,
           modelo: str = MODELO_TEXTO) -> list[dict]:
    """Busca semântica por distância cosseno."""
    emb = obter_modelo(modelo).encode(consulta, normalize_embeddings=True)
    with conectar() as conn, conn.cursor() as cur:
        cur.execute(f"""
            SELECT id, conteudo, embedding <=> %s AS distancia
              FROM {tabela} ORDER BY distancia ASC LIMIT %s
        """, (vetor_sql(emb), limite))
        return [{'id': i, 'conteudo': c, 'distancia': round(d, 4),
                 'similaridade': round(1 - d, 4)}
                for i, c, d in cur.fetchall()]


def criar_indice(tabela: str, metrica: str = 'cosseno') -> str:
    """Cria índice HNSW.

    O operador do índice PRECISA casar com o da consulta: um índice
    vector_l2_ops simplesmente não é usado por uma busca com <=>.
    Em tabelas pequenas o planejador ignora o índice de qualquer forma —
    isso é ele acertando, não defeito.
    """
    ops = {'cosseno': 'vector_cosine_ops',
           'euclidiana': 'vector_l2_ops',
           'escalar': 'vector_ip_ops'}[metrica]
    sql = (f'CREATE INDEX IF NOT EXISTS idx_{tabela}_embedding '
           f'ON {tabela} USING hnsw (embedding {ops})')
    with conectar() as conn, conn.cursor() as cur:
        cur.execute(sql)
    return sql
