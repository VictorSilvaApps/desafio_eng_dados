"""Validação e classificação de registros (RF03).

Cada validador é uma **função pura**: recebe um registro (e, quando a
regra exige, os conjuntos de identificadores válidos) e devolve
`(classificacao, motivo)`. Não abre arquivo, não fala com banco, não
depende de ordem. É isso que permite testá-los com registros sintéticos
em `tests/` — e é assim que a equipe demonstra a validação, porque os
três arquivos de entrada estão limpos e os contadores nascem zerados.

Classificações: `valido`, `invalido`, `incompleto`, `duplicado`.

**Precedência**: primeiro as regras intrínsecas (campo ausente, formato,
domínio, faixa, referência); só um registro que passou em todas elas é
avaliado quanto a duplicidade. Um registro quebrado *e* repetido é
reportado como quebrado, porque é esse o defeito que precisa de conserto.

Duas armadilhas deste conjunto de dados, já tratadas aqui:

1. `avaliacao_atribuida` é `null` em 644 das 1000 interações e isso é
   **correto** — só há nota quando o usuário avaliou. Não é campo ausente.
2. Duplicidade de comentário **não** se detecta pelo texto: só existem 22
   textos distintos em 1000 registros. A chave é `(usuario_id, conteudo_id)`.
"""

from collections import Counter
from datetime import date, datetime

# ── domínios, extraídos do enunciado e conferidos contra os arquivos ──
TIPOS = {'Curso', 'Vídeo', 'Artigo', 'Podcast'}
NIVEIS = {'Básico', 'Intermediário', 'Avançado'}
CATEGORIAS = {
    'Banco de Dados', 'Business Intelligence', 'Ciência de Dados',
    'DevOps & Cloud', 'Engenharia de Dados', 'Inteligência Artificial',
    'Programação & Software', 'Segurança & Governança',
}
TIPOS_INTERACAO = {
    'visualização', 'início', 'conclusão', 'curtida',
    'avaliação', 'compartilhamento',
}

VALIDO, INVALIDO, INCOMPLETO, DUPLICADO = 'valido', 'invalido', 'incompleto', 'duplicado'

OBRIGATORIOS = {
    'catalogo': ('conteudo_id', 'titulo', 'tipo', 'categoria', 'nivel',
                 'carga_horaria_min', 'data_publicacao', 'descricao', 'autor'),
    # `avaliacao_atribuida` fica de fora de propósito: ver armadilha 1.
    'interacoes': ('usuario_id', 'conteudo_id', 'tipo_interacao', 'data_hora',
                   'tempo_consumido', 'percentual_conclusao'),
    'comentarios': ('usuario_id', 'conteudo_id', 'avaliacao', 'comentario',
                    'tags', 'data'),
}

CHAVE_DUPLICIDADE = {
    'catalogo': ('conteudo_id',),
    'interacoes': ('usuario_id', 'conteudo_id', 'tipo_interacao', 'data_hora'),
    'comentarios': ('usuario_id', 'conteudo_id'),
}


# ── auxiliares ────────────────────────────────────────────────
def _ausentes(reg: dict, campos) -> list[str]:
    """Campos que faltam ou vieram vazios. `None` só conta se for obrigatório."""
    faltando = []
    for c in campos:
        if c not in reg:
            faltando.append(c)
        elif reg[c] is None or (isinstance(reg[c], str) and not reg[c].strip()):
            faltando.append(c)
        elif isinstance(reg[c], (list, tuple)) and not reg[c]:
            faltando.append(c)
    return faltando


def _inteiro(valor) -> int | None:
    try:
        n = int(str(valor).strip())
    except (TypeError, ValueError):
        return None
    return n


def _decimal(valor) -> float | None:
    try:
        return float(str(valor).strip())
    except (TypeError, ValueError):
        return None


def _data_iso(valor) -> date | None:
    try:
        return date.fromisoformat(str(valor).strip())
    except (TypeError, ValueError):
        return None


def _datahora_iso(valor) -> datetime | None:
    try:
        return datetime.fromisoformat(str(valor).strip())
    except (TypeError, ValueError):
        return None


# ── validadores, um por fonte ─────────────────────────────────
def validar_conteudo(reg: dict) -> tuple[str, str | None]:
    """Valida um registro do catálogo."""
    if faltando := _ausentes(reg, OBRIGATORIOS['catalogo']):
        return INCOMPLETO, f'campos obrigatórios ausentes: {", ".join(faltando)}'

    if (cid := _inteiro(reg['conteudo_id'])) is None or cid <= 0:
        return INVALIDO, f'conteudo_id inválido: {reg["conteudo_id"]!r}'
    if reg['tipo'] not in TIPOS:
        return INVALIDO, f'tipo fora do domínio: {reg["tipo"]!r}'
    if reg['categoria'] not in CATEGORIAS:
        return INVALIDO, f'categoria fora do domínio: {reg["categoria"]!r}'
    if reg['nivel'] not in NIVEIS:
        return INVALIDO, f'nivel fora do domínio: {reg["nivel"]!r}'
    if (carga := _inteiro(reg['carga_horaria_min'])) is None:
        return INVALIDO, f'carga_horaria_min não é inteiro: {reg["carga_horaria_min"]!r}'
    if carga <= 0:
        return INVALIDO, f'carga_horaria_min não positiva: {carga}'
    if _data_iso(reg['data_publicacao']) is None:
        return INVALIDO, f'data_publicacao fora do ISO 8601: {reg["data_publicacao"]!r}'
    return VALIDO, None


def validar_interacao(reg: dict, ids_conteudo: set[int],
                      ids_usuario: set[int] | None = None) -> tuple[str, str | None]:
    """Valida uma interação. `ids_conteudo` vem do catálogo já validado."""
    if faltando := _ausentes(reg, OBRIGATORIOS['interacoes']):
        return INCOMPLETO, f'campos obrigatórios ausentes: {", ".join(faltando)}'

    uid, cid = _inteiro(reg['usuario_id']), _inteiro(reg['conteudo_id'])
    if uid is None or uid <= 0:
        return INVALIDO, f'usuario_id inválido: {reg["usuario_id"]!r}'
    if cid is None or cid <= 0:
        return INVALIDO, f'conteudo_id inválido: {reg["conteudo_id"]!r}'
    if cid not in ids_conteudo:
        return INVALIDO, f'conteudo_id {cid} não existe no catálogo'
    if ids_usuario is not None and uid not in ids_usuario:
        return INVALIDO, f'usuario_id {uid} não existe'
    if reg['tipo_interacao'] not in TIPOS_INTERACAO:
        return INVALIDO, f'tipo_interacao fora do domínio: {reg["tipo_interacao"]!r}'
    if _datahora_iso(reg['data_hora']) is None:
        return INVALIDO, f'data_hora fora do ISO 8601: {reg["data_hora"]!r}'

    if (tempo := _decimal(reg['tempo_consumido'])) is None:
        return INVALIDO, f'tempo_consumido não é numérico: {reg["tempo_consumido"]!r}'
    if tempo < 0:
        return INVALIDO, f'tempo_consumido negativo: {tempo}'
    if (pct := _decimal(reg['percentual_conclusao'])) is None:
        return INVALIDO, f'percentual_conclusao não é numérico: {reg["percentual_conclusao"]!r}'
    if not 0 <= pct <= 100:
        return INVALIDO, f'percentual_conclusao fora de 0–100: {pct}'

    # Numérico incompatível com o categórico: o RF03 pede esta checagem.
    if reg['tipo_interacao'] == 'conclusão' and pct != 100:
        return INVALIDO, f'interação de conclusão com percentual_conclusao {pct}, esperado 100'

    # `null` aqui é legítimo (só há nota quando houve avaliação).
    nota = reg.get('avaliacao_atribuida')
    if nota is not None:
        if (n := _decimal(nota)) is None:
            return INVALIDO, f'avaliacao_atribuida não é numérica: {nota!r}'
        if not 1 <= n <= 5:
            return INVALIDO, f'avaliacao_atribuida fora de 1–5: {n}'
    return VALIDO, None


def validar_comentario(reg: dict, ids_conteudo: set[int],
                       ids_usuario: set[int] | None = None) -> tuple[str, str | None]:
    """Valida um comentário."""
    if faltando := _ausentes(reg, OBRIGATORIOS['comentarios']):
        return INCOMPLETO, f'campos obrigatórios ausentes: {", ".join(faltando)}'

    uid, cid = _inteiro(reg['usuario_id']), _inteiro(reg['conteudo_id'])
    if uid is None or uid <= 0:
        return INVALIDO, f'usuario_id inválido: {reg["usuario_id"]!r}'
    if cid is None or cid <= 0:
        return INVALIDO, f'conteudo_id inválido: {reg["conteudo_id"]!r}'
    if cid not in ids_conteudo:
        return INVALIDO, f'conteudo_id {cid} não existe no catálogo'
    if ids_usuario is not None and uid not in ids_usuario:
        return INVALIDO, f'usuario_id {uid} não existe'
    if (nota := _inteiro(reg['avaliacao'])) is None:
        return INVALIDO, f'avaliacao não é inteiro: {reg["avaliacao"]!r}'
    if not 1 <= nota <= 5:
        return INVALIDO, f'avaliacao fora de 1–5: {nota}'
    if _data_iso(reg['data']) is None:
        return INVALIDO, f'data fora do ISO 8601: {reg["data"]!r}'
    if not isinstance(reg['tags'], (list, tuple)):
        return INVALIDO, f'tags deveria ser lista, veio {type(reg["tags"]).__name__}'
    return VALIDO, None


VALIDADORES = {
    'catalogo': validar_conteudo,
    'interacoes': validar_interacao,
    'comentarios': validar_comentario,
}


# ── classificação de uma fonte inteira ────────────────────────
def _chave(reg: dict, campos: tuple[str, ...]) -> tuple:
    return tuple(str(reg.get(c)) for c in campos)


def classificar(fonte: str, registros: list[dict], **contexto) -> list[dict]:
    """Classifica todos os registros de uma fonte.

    Devolve, para cada registro e na mesma ordem, um dicionário com
    `classificacao`, `motivo` e o próprio `registro`. Duplicidade é
    avaliada por último e só sobre quem passou nas regras intrínsecas —
    a primeira ocorrência fica válida, as seguintes viram `duplicado`.
    """
    validador = VALIDADORES[fonte]
    campos_chave = CHAVE_DUPLICIDADE[fonte]

    resultado, vistas = [], set()
    for reg in registros:
        classificacao, motivo = validador(reg, **contexto)
        if classificacao == VALIDO:
            k = _chave(reg, campos_chave)
            if k in vistas:
                classificacao = DUPLICADO
                motivo = f'repetido em {"+".join(campos_chave)}: {"|".join(k)}'
            else:
                vistas.add(k)
        resultado.append({'classificacao': classificacao, 'motivo': motivo,
                          'registro': reg})
    return resultado


def contar(classificados: list[dict]) -> dict[str, int]:
    """Contagem por classificação, com as quatro chaves sempre presentes."""
    c = Counter(r['classificacao'] for r in classificados)
    return {k: c.get(k, 0) for k in (VALIDO, INVALIDO, INCOMPLETO, DUPLICADO)}


def motivos(classificados: list[dict]) -> dict[str, int]:
    """Motivos dos não-válidos, agrupados e contados.

    O valor concreto sai da mensagem para os motivos agruparem: cem datas
    diferentes e malformadas viram uma linha só, não cem.
    """
    c = Counter(r['motivo'].split(':')[0]
                for r in classificados
                if r['classificacao'] != VALIDO and r['motivo'])
    return dict(c)
