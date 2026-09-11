"""Ingestão de CSV, JSON e Excel para o PostgreSQL.

Cada função aqui já resolve um problema que apareceu nas aulas:

- CSV com vírgula dentro do campo  -> csv.DictReader respeita as aspas
- reingestão duplicando registros  -> ON CONFLICT obrigatório
- JSON aninhado                    -> JSONB, ou colunas extraídas
- tipos vindo tudo como texto      -> inferência opcional via pandas
"""

import csv
import json
from pathlib import Path

from psycopg2.extras import Json, execute_values

from .db import conectar

# Mapa simples de tipo pandas -> tipo PostgreSQL, para criar tabelas
# a partir de um arquivo sem escrever o DDL na mão.
TIPOS = {
    'int64': 'BIGINT', 'Int64': 'BIGINT',
    'float64': 'DOUBLE PRECISION',
    'bool': 'BOOLEAN',
    'datetime64[ns]': 'TIMESTAMP', 'datetime64[us]': 'TIMESTAMP',
}


def ler_tabela(caminho: str | Path):
    """Lê CSV, TSV, Excel ou JSON para um DataFrame."""
    import pandas as pd
    p = Path(caminho)
    suf = p.suffix.lower()
    if suf in ('.csv', '.txt'):
        return pd.read_csv(p)
    if suf == '.tsv':
        return pd.read_csv(p, sep='\t')
    if suf in ('.xlsx', '.xls'):
        return pd.read_excel(p)
    if suf == '.json':
        return pd.read_json(p)
    raise ValueError(f'extensão não suportada: {suf}')


def criar_tabela_de_df(df, tabela: str, pk: str | None = None) -> str:
    """Gera e executa o CREATE TABLE a partir dos tipos do DataFrame."""
    colunas = []
    for nome, dtype in df.dtypes.items():
        tipo = TIPOS.get(str(dtype), 'TEXT')
        if pk and nome == pk:
            tipo += ' PRIMARY KEY'
        colunas.append(f'    {nome} {tipo}')
    ddl = f'CREATE TABLE IF NOT EXISTS {tabela} (\n' + ',\n'.join(colunas) + '\n)'
    with conectar() as conn, conn.cursor() as cur:
        cur.execute(ddl)
    return ddl


def inserir_df(df, tabela: str, conflito: str | None = None,
               atualizar: bool = True) -> int:
    """Insere um DataFrame na tabela.

    `conflito` é a coluna (ou colunas separadas por vírgula) que torna a
    ingestão idempotente. Sem ela, reprocessar o mesmo arquivo duplica
    tudo — silenciosamente, se não houver constraint.
    """
    cols = list(df.columns)
    registros = [tuple(None if v != v else v for v in linha)   # NaN -> NULL
                 for linha in df.itertuples(index=False, name=None)]

    sql = f"INSERT INTO {tabela} ({', '.join(cols)}) VALUES %s"
    if conflito:
        if atualizar:
            sets = ', '.join(f'{c} = EXCLUDED.{c}' for c in cols
                             if c not in conflito.split(','))
            sql += f' ON CONFLICT ({conflito}) DO UPDATE SET {sets}'
        else:
            sql += f' ON CONFLICT ({conflito}) DO NOTHING'

    with conectar() as conn, conn.cursor() as cur:
        execute_values(cur, sql, registros, page_size=500)
    return len(registros)


def ingerir_arquivo(caminho: str | Path, tabela: str,
                    pk: str | None = None, conflito: str | None = None) -> int:
    """Atalho: lê o arquivo, cria a tabela e insere. Devolve nº de linhas."""
    df = ler_tabela(caminho)
    criar_tabela_de_df(df, tabela, pk)
    n = inserir_df(df, tabela, conflito or pk)
    print(f'  {Path(caminho).name} -> {tabela}: {n} linhas, '
          f'{len(df.columns)} colunas')
    return n


def ingerir_json_bruto(caminho: str | Path, tabela: str,
                       chave: str | None = None) -> int:
    """Guarda cada objeto JSON inteiro numa coluna JSONB (schema-on-read).

    `chave` é o campo do documento que serve de identificador natural.
    Sem ele não há como deduplicar, e reprocessar duplica os registros.
    """
    dados = json.loads(Path(caminho).read_text(encoding='utf-8'))
    if isinstance(dados, dict):
        dados = [dados]

    with conectar() as conn, conn.cursor() as cur:
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {tabela} (
                id    SERIAL PRIMARY KEY,
                chave TEXT UNIQUE,
                dados JSONB
            )""")
        linhas = [(str(d.get(chave)) if chave else json.dumps(d, sort_keys=True),
                   Json(d)) for d in dados]
        execute_values(
            cur,
            f'INSERT INTO {tabela} (chave, dados) VALUES %s '
            f'ON CONFLICT (chave) DO UPDATE SET dados = EXCLUDED.dados',
            linhas, page_size=500)

    print(f'  {Path(caminho).name} -> {tabela}: {len(linhas)} documentos (JSONB)')
    return len(linhas)


def csv_bem_formado(caminho: str | Path) -> tuple[bool, str]:
    """Confere se todas as linhas do CSV têm o mesmo nº de campos.

    O CSV da Aula 08 tinha uma vírgula sem aspas no meio de uma
    descrição, e o desempacotamento estourava. Vale checar antes.
    """
    with open(caminho, encoding='utf-8') as f:
        linhas = list(csv.reader(f))
    if not linhas:
        return False, 'arquivo vazio'
    esperado = len(linhas[0])
    for i, linha in enumerate(linhas[1:], 2):
        if len(linha) != esperado:
            return False, (f'linha {i} tem {len(linha)} campos, '
                           f'cabeçalho tem {esperado} — provável vírgula '
                           f'sem aspas')
    return True, f'{len(linhas)-1} linhas, {esperado} campos'
