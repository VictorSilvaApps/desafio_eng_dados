"""Cálculo e exibição de indicadores.

As fórmulas seguem as da Aula 11 (Exercício Extra), que são o vocabulário
padrão de dashboard operacional: taxa de conclusão, tempo médio,
aderência a prazo, satisfação, backlog e concentração.
"""

from .db import consultar


def taxa(tabela: str, coluna: str, valor: str, rotulo: str = 'taxa_pct') -> float:
    """Percentual de linhas onde `coluna = valor`."""
    r = consultar(f"""
        SELECT ROUND(COUNT(*) FILTER (WHERE {coluna} = %s) * 100.0
                     / NULLIF(COUNT(*), 0), 2) AS {rotulo}
          FROM {tabela}""", (valor,))
    return float(r[0][rotulo] or 0)


def media(tabela: str, coluna: str, onde: str = '') -> float:
    """Média, ignorando NULL. Devolve 0 se não houver linhas."""
    filtro = f'WHERE {onde}' if onde else ''
    r = consultar(f'SELECT ROUND(AVG({coluna})::numeric, 2) AS m '
                  f'FROM {tabela} {filtro}')
    return float(r[0]['m'] or 0)


def tempo_medio_dias(tabela: str, inicio: str, fim: str, onde: str = '') -> float:
    """Diferença média entre duas datas, em dias."""
    filtro = f'AND {onde}' if onde else ''
    r = consultar(f"""
        SELECT ROUND(AVG({fim} - {inicio})::numeric, 1) AS dias
          FROM {tabela} WHERE {fim} IS NOT NULL {filtro}""")
    return float(r[0]['dias'] or 0)


def distribuicao(tabela: str, coluna: str, ordenar_por_volume: bool = True,
                 ignorar_nulos: bool = True) -> list[dict]:
    """Contagem e participação percentual por categoria.

    `ignorar_nulos` é True por padrão de propósito: agregar sobre coluna
    opcional sem filtrar transforma o ausente numa categoria, e o balde
    'null' costuma virar a maior barra do gráfico.
    """
    filtro = f'WHERE {coluna} IS NOT NULL' if ignorar_nulos else ''
    ordem = 'total DESC' if ordenar_por_volume else f'{coluna}'
    return consultar(f"""
        SELECT {coluna}::text AS categoria,
               COUNT(*) AS total,
               ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS participacao_pct
          FROM {tabela} {filtro}
         GROUP BY {coluna} ORDER BY {ordem}""")


def exibir(titulo: str, valor, sufixo: str = '', largura: int = 52) -> None:
    """Imprime um KPI em formato de cartão."""
    v = f'{valor:,.2f}'.replace(',', '·').replace('.', ',').replace('·', '.') \
        if isinstance(valor, float) else str(valor)
    print(f'  {titulo:<{largura - 16}} {v + sufixo:>14}')


def exibir_tabela(linhas: list[dict], titulo: str = '') -> None:
    """Imprime uma lista de dicionários como tabela alinhada."""
    if not linhas:
        print(f'  {titulo}: (sem dados)')
        return
    if titulo:
        print(f'\n  {titulo}')
    cols = list(linhas[0].keys())
    larg = {c: max(len(str(c)), max(len(str(reg.get(c, ''))) for reg in linhas))
            for c in cols}
    print('    ' + '  '.join(f'{c:<{larg[c]}}' for c in cols))
    print('    ' + '  '.join('-' * larg[c] for c in cols))
    for reg in linhas:
        print('    ' + '  '.join(f'{str(reg.get(c, "")):<{larg[c]}}' for c in cols))
