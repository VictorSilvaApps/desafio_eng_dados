"""Conexão com PostgreSQL e MongoDB, credenciais no .env."""

import os
from pathlib import Path
from urllib.parse import quote

import psycopg2
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / '.env')

DB_HOST     = os.getenv('DB_HOST', 'localhost')
DB_NAME     = os.getenv('DB_NAME', 'meu_banco_de_dados')
DB_USER     = os.getenv('DB_USER', 'victor')
DB_PASSWORD = os.getenv('DB_PASSWORD')

MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
MONGO_DB  = os.getenv('MONGO_DB', 'desafio')


def conectar():
    """Conexão psycopg2. Use sempre como context manager."""
    if not DB_PASSWORD:
        raise RuntimeError('DB_PASSWORD não definida — confira o .env')
    return psycopg2.connect(host=DB_HOST, database=DB_NAME,
                            user=DB_USER, password=DB_PASSWORD)


def uri_sqlalchemy(host: str | None = None) -> str:
    """URI no formato que o SQLAlchemy/Superset espera.

    A senha vai percent-encoded. Isto não é preciosismo: uma senha com
    '#', '@' ou '/' quebra a URI silenciosamente — o '#' inicia o
    fragmento e o parser passa a ler o resto como nome de host.
    """
    return (f'postgresql://{DB_USER}:{quote(DB_PASSWORD or "", safe="")}'
            f'@{host or DB_HOST}:5432/{DB_NAME}')


def conectar_mongo():
    """Cliente MongoDB. Import tardio para não exigir pymongo sem uso."""
    from pymongo import MongoClient
    return MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)[MONGO_DB]


def consultar(sql: str, params=None) -> list[dict]:
    """Executa SELECT e devolve lista de dicionários."""
    with conectar() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, linha, strict=True)) for linha in cur.fetchall()]


def executar(sql: str, params=None) -> None:
    """Executa DDL/DML sem retorno."""
    with conectar() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
