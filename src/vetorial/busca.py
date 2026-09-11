"""Busca semântica (RF09).

`toolkit.vetorial.buscar` devolve `id`, `conteudo`, `distancia` e
`similaridade` — o suficiente para ordenar, mas não para apresentar. O
RF09 pede posição, id, título, categoria, tipo e similaridade, então a
função daqui enriquece o resultado com um JOIN no catálogo.

O `limite` vem do `config.yaml`, como o requisito exige.
"""

import json
from pathlib import Path

from toolkit.db import consultar
from toolkit.vetorial import buscar

from ..log import Registro

# Quantos candidatos buscar além do limite, para sobrar margem depois da
# deduplicação por título.
FOLGA = 5


def buscar_conteudos(tabela_embedding: str, tabela_conteudo: str,
                     tabela_categoria: str, consulta: str,
                     limite: int = 5, modelo: str | None = None) -> list[dict]:
    """Busca por similaridade e devolve os campos que o RF09 pede.

    **Sobre a deduplicação por título.** O catálogo tem 811 títulos
    distintos em 1000 conteúdos, e 612 descrições distintas: 124 registros
    repetem o par (título, descrição) com id, autor, carga e às vezes nível
    diferentes. São conteúdos legítimos e distintos — dois instrutores
    tratando do mesmo tema —, e por isso **não** são rejeitados na
    validação nem deixam de receber embedding.

    Mas o embedding é feito de título + descrição, como o RF08 determina.
    Quando os dois coincidem, os vetores ficam idênticos e o resultado
    traz a mesma linha três vezes, com a mesma similaridade. Isso não
    informa nada a quem lê. Então a busca pede mais candidatos do que
    precisa e mantém só o melhor de cada título.
    """
    quantos = limite * FOLGA
    achados = (buscar(tabela_embedding, consulta, quantos, modelo) if modelo
               else buscar(tabela_embedding, consulta, quantos))
    if not achados:
        return []

    ids = [a['id'] for a in achados]
    detalhes = {d['conteudo_id']: d for d in consultar(f"""
        SELECT c.conteudo_id, c.titulo, c.tipo, c.nivel, cat.nome AS categoria
          FROM {tabela_conteudo} c
          JOIN {tabela_categoria} cat ON cat.categoria_id = c.categoria_id
         WHERE c.conteudo_id = ANY(%s)
    """, (ids,))}

    resultado, titulos = [], set()
    for achado in achados:                       # já vem ordenado por distância
        d = detalhes.get(achado['id'], {})
        titulo = d.get('titulo')
        if titulo in titulos:
            continue
        titulos.add(titulo)
        resultado.append({
            'posicao': len(resultado) + 1,
            'conteudo_id': achado['id'],
            'titulo': titulo,
            'categoria': d.get('categoria'),
            'tipo': d.get('tipo'),
            'nivel': d.get('nivel'),
            'similaridade': achado['similaridade'],
            'distancia': achado['distancia'],
        })
        if len(resultado) >= limite:
            break
    return resultado


def demonstrar(tabela_embedding: str, tabela_conteudo: str,
               tabela_categoria: str, consultas: list[str], limite: int,
               destino: Path, registro: Registro) -> Path:
    """Roda as 3 consultas exigidas pelo RF09 e salva a saída."""
    saida = {}
    for texto in consultas:
        achados = buscar_conteudos(tabela_embedding, tabela_conteudo,
                                   tabela_categoria, texto, limite)
        saida[texto] = achados

        registro._anunciar(f'consulta: "{texto}"')
        for a in achados:
            registro._anunciar(
                f'  {a["posicao"]}. [{a["similaridade"]:.4f}] '
                f'{a["titulo"]}  ({a["categoria"]} · {a["tipo"]})')

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(saida, indent=2, ensure_ascii=False),
                       encoding='utf-8')
    return destino
