"""Leitura das três fontes (RF02).

**Por que não usamos `pandas` aqui.** O RF03 manda validar formato de data,
faixa de número e campo ausente. O pandas converte tudo isso na hora da
leitura: uma data malformada vira `NaT`, um número inválido vira `NaN`, e
`null` vira `NaN` igual a campo ausente. Quando o validador recebesse o
dado, o defeito que ele deveria encontrar já teria sido apagado — e a
distinção entre "ausente" e "nulo" some, justamente a que separa os 644
`avaliacao_atribuida` legítimos de um campo faltando.

Então a leitura entrega `list[dict]` com os valores **como estão no
arquivo**, e o pandas entra depois, na carga (`src/carga/postgres.py`),
onde o `toolkit` já resolve tipos e `ON CONFLICT`.

O `csv_bem_formado` do toolkit continua sendo usado: ele pega vírgula sem
aspas antes de o `DictReader` desalinhar as colunas silenciosamente.
"""

import csv
import json
from pathlib import Path

from toolkit.ingestao import csv_bem_formado

from ..log import Registro


def ler_csv(caminho: Path) -> list[dict]:
    """Lê CSV preservando tudo como texto.

    `utf-8-sig` porque um CSV exportado do Excel começa com BOM, e o BOM
    gruda no nome da primeira coluna: viraria `﻿conteudo_id`.
    """
    ok, detalhe = csv_bem_formado(caminho)
    if not ok:
        raise ValueError(f'{caminho.name}: {detalhe}')
    with open(caminho, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def ler_json(caminho: Path) -> list[dict]:
    """Lê JSON de lista de objetos, sem coerção de tipo."""
    dados = json.loads(caminho.read_text(encoding='utf-8'))
    return dados if isinstance(dados, list) else [dados]


def ler_fonte(caminho: Path) -> list[dict]:
    return ler_csv(caminho) if caminho.suffix.lower() == '.csv' else ler_json(caminho)


def ler_fontes(fontes: dict[str, Path], registro: Registro) -> dict[str, list[dict]]:
    """Lê as três fontes, anunciando nome e contagem de cada uma (RF02)."""
    lidos: dict[str, list[dict]] = {}
    for nome, caminho in fontes.items():
        try:
            registros = ler_fonte(caminho)
        except Exception as erro:
            registro.falha('leitura', caminho.name, erro)
            raise
        lidos[nome] = registros
        registro.arquivo(caminho, len(registros))
    return lidos
