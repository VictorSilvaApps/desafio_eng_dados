"""Motor de recomendação (RF10) e persistência (RF11).

Fórmula do enunciado:

    Pontuação = ( (Ivis + Icur) / 2 ) * 100 * Iconc

**Ivis — índice de visualizações.** O enunciado aceita duas definições:
similaridade vetorial via pgvector, ou proporção de tempo consumido na
mesma categoria. Usamos a vetorial: monta-se o centroide dos embeddings
dos conteúdos com que o usuário interagiu e compara-se por cosseno com o
embedding do candidato. Reaproveita o RF08 e resolve o *cold start* —
375 conteúdos não têm interação nenhuma, e a similaridade textual existe
para os 1000. Para usuário sem histórico, cai-se para a definição
alternativa (proporção de tempo por categoria), registrada no log.

Os vetores são gravados normalizados (`normalize_embeddings=True` no
toolkit), então o produto escalar **é** a similaridade de cosseno. O
cálculo é feito em numpy, numa multiplicação de matriz de 150×384 por
384×1000: o mesmo número que o `<=>` do pgvector daria, de uma vez só,
em vez de 150 mil consultas.

**Icur — índice de curtidas e avaliações.** Aqui o enunciado é ambíguo:
pede "a proporção de sinais positivos do usuário na categoria do
candidato" sem dizer sobre o que é a proporção. As duas leituras
possíveis dão resultados muito diferentes:

  (a) positivos na categoria / positivos do usuário em todas as
      categorias — vira uma distribuição que soma 1, então com 8
      categorias a média fica em 0,125 e quase toda pontuação cairia
      abaixo de 40, classificando tudo como Negativo;
  (b) positivos na categoria / sinais do usuário naquela categoria —
      uma taxa de aprovação dentro da categoria, que varia de 0 a 1 e
      discrimina de verdade.

Adotamos **(b)**. Decisão de equipe registrada no README, como as de G1
a G8 do levantamento.

**Iconc — filtro binário.** 0 se o usuário já concluiu o conteúdo, 1 caso
contrário. Zera a pontuação, como o enunciado determina.

**Classificação.** O enunciado escreve a faixa "Estável" como
`40 > Pontuação < 70`, impossível de satisfazer. Cruzando com as outras
duas faixas, a intenção é `40 < P < 70` (decisão G3).
"""

import json
from datetime import datetime

import numpy as np

from toolkit.db import conectar, consultar

from ..log import Registro

# Interações que indicam consumo, e portanto entram no centroide do usuário.
CONSUMO = ('visualização', 'início', 'conclusão')


def _vetor(texto: str) -> np.ndarray:
    """pgvector devolve o vetor como texto '[0.1,0.2,...]', que é JSON válido."""
    return np.asarray(json.loads(texto), dtype=np.float32)


def carregar_estado(tabelas: dict[str, str], colecao_mongo: str,
                    nota_minima: int, registro: Registro) -> dict:
    """Lê do PostgreSQL e do MongoDB tudo que o cálculo precisa.

    Os sinais positivos vêm dos dois bancos: curtidas e notas altas estão
    nas interações (PostgreSQL), e as avaliações dos comentários estão no
    MongoDB. É o momento em que os dois armazenamentos se encontram.
    """
    embeddings = consultar(
        f'SELECT id, embedding FROM {tabelas["embedding"]} ORDER BY id')
    conteudos = consultar(f"""
        SELECT c.conteudo_id, c.titulo, cat.nome AS categoria
          FROM {tabelas["conteudo"]} c
          JOIN {tabelas["categoria"]} cat ON cat.categoria_id = c.categoria_id
         ORDER BY c.conteudo_id
    """)
    interacoes = consultar(f"""
        SELECT usuario_id, conteudo_id, tipo_interacao,
               tempo_consumido, avaliacao_atribuida
          FROM {tabelas["interacao"]}
    """)

    # Avaliações dos comentários: enriquecem muito o Icur (791 notas >= 4
    # contra 89 avaliações nas interações). Se o Mongo estiver fora, o
    # motor continua com os sinais do PostgreSQL — degradado, não parado.
    comentarios = []
    try:
        from toolkit.db import conectar_mongo
        comentarios = list(conectar_mongo()[colecao_mongo].find(
            {}, {'_id': 0, 'usuario_id': 1, 'conteudo_id': 1, 'avaliacao': 1}))
    except Exception as erro:
        registro.falha('conexao', f'mongodb/{colecao_mongo}', erro,
                       'o motor segue só com os sinais do PostgreSQL; o Icur '
                       'fica mais pobre, mas a recomendação não para')

    return {
        'ids': [e['id'] for e in embeddings],
        'matriz': np.vstack([_vetor(e['embedding']) for e in embeddings]),
        'categoria_por_conteudo': {c['conteudo_id']: c['categoria'] for c in conteudos},
        'titulo_por_conteudo': {c['conteudo_id']: c['titulo'] for c in conteudos},
        'interacoes': interacoes,
        'comentarios': comentarios,
        'nota_minima': nota_minima,
    }


def _perfis(estado: dict) -> dict[int, dict]:
    """Agrega, por usuário: consumo, conclusões, sinais e tempo por categoria."""
    categoria = estado['categoria_por_conteudo']
    perfis: dict[int, dict] = {}

    def perfil(uid):
        return perfis.setdefault(uid, {
            'consumidos': set(), 'concluidos': set(),
            'sinais': {}, 'positivos': {}, 'tempo': {},
        })

    for i in estado['interacoes']:
        p = perfil(i['usuario_id'])
        cat = categoria.get(i['conteudo_id'])
        if cat is None:
            continue

        if i['tipo_interacao'] in CONSUMO:
            p['consumidos'].add(i['conteudo_id'])
        if i['tipo_interacao'] == 'conclusão':
            p['concluidos'].add(i['conteudo_id'])

        p['tempo'][cat] = p['tempo'].get(cat, 0.0) + float(i['tempo_consumido'] or 0)
        p['sinais'][cat] = p['sinais'].get(cat, 0) + 1

        nota = i['avaliacao_atribuida']
        positivo = (i['tipo_interacao'] == 'curtida'
                    or (nota is not None and float(nota) >= estado['nota_minima']))
        if positivo:
            p['positivos'][cat] = p['positivos'].get(cat, 0) + 1

    for c in estado['comentarios']:
        cat = categoria.get(c['conteudo_id'])
        if cat is None:
            continue
        p = perfil(c['usuario_id'])
        p['sinais'][cat] = p['sinais'].get(cat, 0) + 1
        if int(c['avaliacao']) >= estado['nota_minima']:
            p['positivos'][cat] = p['positivos'].get(cat, 0) + 1

    return perfis


def _classificar(pontuacao: float, iconc: int,
                 limiar_positivo: float, limiar_negativo: float) -> str:
    """Faixas do RF10, com a correção da faixa impossível (G3)."""
    if iconc == 0 or pontuacao <= limiar_negativo:
        return 'Negativo'
    if pontuacao >= limiar_positivo:
        return 'Positivo'
    return 'Estável'          # limiar_negativo < P < limiar_positivo


def calcular(estado: dict, parametros: dict, registro: Registro) -> list[dict]:
    """Gera as recomendações de todos os usuários."""
    ids = estado['ids']
    matriz = estado['matriz']
    posicao_do_id = {cid: i for i, cid in enumerate(ids)}
    categoria = estado['categoria_por_conteudo']
    titulo_por_conteudo = estado['titulo_por_conteudo']
    categorias_dos_candidatos = np.array([categoria.get(c, '') for c in ids])

    top_n = parametros['top_n']
    lim_pos = parametros['limiar_positivo']
    lim_neg = parametros['limiar_negativo']

    perfis = _perfis(estado)
    recomendacoes, sem_historico = [], 0
    distribuicao = {'Positivo': 0, 'Estável': 0, 'Negativo': 0}

    for uid, p in sorted(perfis.items()):
        # ── Ivis ──────────────────────────────────────────────
        indices = [posicao_do_id[c] for c in p['consumidos'] if c in posicao_do_id]
        if indices:
            centroide = matriz[indices].mean(axis=0)
            norma = np.linalg.norm(centroide)
            centroide = centroide / norma if norma else centroide
            # Vetores normalizados: produto escalar = cosseno.
            ivis = np.clip(matriz @ centroide, 0.0, 1.0)
        else:
            # Sem histórico de consumo: cai para a definição alternativa do
            # enunciado — proporção do tempo consumido na mesma categoria.
            sem_historico += 1
            tempo_total = sum(p['tempo'].values())
            proporcao = ({c: t / tempo_total for c, t in p['tempo'].items()}
                         if tempo_total else {})
            ivis = np.array([proporcao.get(c, 0.0) for c in categorias_dos_candidatos],
                            dtype=np.float32)

        # ── Icur ──────────────────────────────────────────────
        taxa = {cat: p['positivos'].get(cat, 0) / n
                for cat, n in p['sinais'].items() if n}
        icur = np.array([taxa.get(c, 0.0) for c in categorias_dos_candidatos],
                        dtype=np.float32)

        # ── Iconc e pontuação ─────────────────────────────────
        iconc = np.array([0 if c in p['concluidos'] else 1 for c in ids],
                         dtype=np.float32)
        pontuacoes = ((ivis + icur) / 2) * 100 * iconc

        # Distribuição sobre TODOS os candidatos, não só sobre o top_n.
        # É ela que mostra que a faixa do RF10 discrimina: a lista final
        # sai quase toda Positiva porque é o topo do ranking, por
        # construção — olhar só para ela esconderia o comportamento real.
        negativo = (iconc == 0) | (pontuacoes <= lim_neg)
        positivo = ~negativo & (pontuacoes >= lim_pos)
        distribuicao['Negativo'] += int(negativo.sum())
        distribuicao['Positivo'] += int(positivo.sum())
        distribuicao['Estável'] += int((~negativo & ~positivo).sum())

        # Os melhores primeiro. A folga cobre os que serão descartados por
        # classificação Negativo e os que caem na deduplicação por título.
        ordem = np.argsort(-pontuacoes)[:top_n * 6]

        posicao, titulos_ja_sugeridos = 0, set()
        for idx in ordem:
            pontuacao = float(pontuacoes[idx])
            classificacao = _classificar(pontuacao, int(iconc[idx]), lim_pos, lim_neg)
            if classificacao == 'Negativo':
                continue          # descartado da lista de sugestões

            # O catálogo repete título em 189 dos 1000 conteúdos (811
            # títulos distintos), com id, autor e carga diferentes. São
            # conteúdos legítimos, mas título + descrição iguais geram
            # embeddings iguais, e a lista sairia com a mesma sugestão
            # repetida. Sugerimos o melhor exemplar de cada título.
            titulo = titulo_por_conteudo.get(ids[idx])
            if titulo in titulos_ja_sugeridos:
                continue
            titulos_ja_sugeridos.add(titulo)

            posicao += 1
            recomendacoes.append({
                'usuario_id': uid,
                'conteudo_id': ids[idx],
                'pontuacao': round(pontuacao, 2),
                'posicao': posicao,
                'classificacao': classificacao,
            })
            if posicao >= top_n:
                break

    if sem_historico:
        registro._anunciar(f'{sem_historico} usuários sem histórico de consumo '
                           f'usaram o Ivis alternativo (proporção por categoria)')

    total = sum(distribuicao.values())
    faixas = ' · '.join(f'{k} {v} ({100 * v / total:.1f}%)'
                        for k, v in distribuicao.items())
    registro._anunciar(f'classificação de {total} pares usuário×conteúdo: {faixas}')
    registro._anunciar(f'{len(recomendacoes)} recomendações geradas para '
                       f'{len(perfis)} usuários')
    return recomendacoes


def persistir(tabela: str, recomendacoes: list[dict], registro: Registro,
              resumo) -> int:
    """Grava as recomendações (RF11), com data/hora única para o lote."""


    from contextlib import closing

    from psycopg2.extras import execute_values

    gerado_em = datetime.now().replace(microsecond=0)
    linhas = [(r['usuario_id'], r['conteudo_id'], r['pontuacao'],
               r['posicao'], r['classificacao'], gerado_em)
              for r in recomendacoes]

    try:
        with closing(conectar()) as conn, conn, conn.cursor() as cur:
            # Mantém apenas o lote atual de recomendações.
            # Se o pipeline for executado novamente, não acumula duplicados.
            cur.execute(f'DELETE FROM {tabela}')
            if linhas:
                execute_values(cur, f"""
                    INSERT INTO {tabela}
                        (usuario_id, conteudo_id, pontuacao, posicao,
                         classificacao, gerado_em)
                    VALUES %s
                    ON CONFLICT (usuario_id, conteudo_id, gerado_em) DO UPDATE
                       SET pontuacao = EXCLUDED.pontuacao,
                           posicao = EXCLUDED.posicao,
                           classificacao = EXCLUDED.classificacao
                """, linhas, page_size=500)
    except Exception as erro:
        registro.falha('persistencia', tabela, erro)
        raise

    resumo.carregado('postgresql', tabela.split('.')[-1], len(linhas))
    registro._anunciar(f'{len(linhas)} recomendações gravadas '
                       f'(lote {gerado_em.isoformat()})')
    return len(linhas)


def amostra(recomendacoes: list[dict], estado: dict, quantos: int = 5) -> list[dict]:
    """Primeiras recomendações de um usuário, para evidência do RF10."""
    if not recomendacoes:
        return []
    primeiro = recomendacoes[0]['usuario_id']
    titulo = estado['titulo_por_conteudo']
    return [{**r, 'titulo': titulo.get(r['conteudo_id']),
             'categoria': estado['categoria_por_conteudo'].get(r['conteudo_id'])}
            for r in recomendacoes
            if r['usuario_id'] == primeiro][:quantos]
