"""Tratamento e padronização (RF04).

Entra `list[dict]` com valores como estavam no arquivo; sai `list[dict]`
com tipo Python correto e texto normalizado, pronto para a carga.

Os arquivos de `dados/brutos/` **não são tocados** — estão inclusive com
permissão de leitura apenas (444). Todo resultado vai para
`dados/processados/`.

O contador `corrigidos` do RF05 conta registros que a padronização
realmente alterou. Nestes três arquivos ele tende a ficar baixo, porque
os dados já vêm limpos; ele existe para o dia em que não vierem.
"""

import csv
import json
from datetime import date, datetime
from pathlib import Path

from .validacao import CATEGORIAS, NIVEIS, TIPOS, TIPOS_INTERACAO, VALIDO

# Domínio canônico indexado por forma normalizada: permite aceitar
# "VÍDEO", " vídeo " ou "Vídeo" e gravar sempre "Vídeo".
_CANONICO = {
    'tipo': {v.casefold(): v for v in TIPOS},
    'nivel': {v.casefold(): v for v in NIVEIS},
    'categoria': {v.casefold(): v for v in CATEGORIAS},
    'tipo_interacao': {v.casefold(): v for v in TIPOS_INTERACAO},
}


def _texto(valor) -> str:
    """Remove espaços das pontas e colapsa espaços internos repetidos."""
    return ' '.join(str(valor).split())


def _padronizar(campo: str, valor) -> str:
    """Devolve a forma canônica do categórico, ou o texto limpo."""
    limpo = _texto(valor)
    return _CANONICO[campo].get(limpo.casefold(), limpo)


def _data(valor) -> date:
    return date.fromisoformat(_texto(valor))


def _datahora(valor) -> datetime:
    return datetime.fromisoformat(_texto(valor))


# ── um tratador por fonte ─────────────────────────────────────
def tratar_conteudo(reg: dict) -> dict:
    return {
        'conteudo_id': int(reg['conteudo_id']),
        'titulo': _texto(reg['titulo']),
        'tipo': _padronizar('tipo', reg['tipo']),
        'categoria': _padronizar('categoria', reg['categoria']),
        'nivel': _padronizar('nivel', reg['nivel']),
        'carga_horaria_min': int(reg['carga_horaria_min']),
        'data_publicacao': _data(reg['data_publicacao']),
        'descricao': _texto(reg['descricao']),
        'autor': _texto(reg['autor']),
    }


def tratar_interacao(reg: dict) -> dict:
    nota = reg.get('avaliacao_atribuida')
    return {
        'usuario_id': int(reg['usuario_id']),
        'conteudo_id': int(reg['conteudo_id']),
        'tipo_interacao': _padronizar('tipo_interacao', reg['tipo_interacao']),
        'data_hora': _datahora(reg['data_hora']),
        'tempo_consumido': float(reg['tempo_consumido']),
        'percentual_conclusao': float(reg['percentual_conclusao']),
        # Continua nulo de propósito: ausência de nota é informação.
        'avaliacao_atribuida': None if nota is None else float(nota),
    }


def tratar_comentario(reg: dict) -> dict:
    return {
        'usuario_id': int(reg['usuario_id']),
        'conteudo_id': int(reg['conteudo_id']),
        'avaliacao': int(reg['avaliacao']),
        'comentario': _texto(reg['comentario']),
        # Tags em caixa baixa: são rótulos, e "LGPD" e "lgpd" são a mesma tag.
        'tags': sorted({_texto(t).casefold() for t in reg['tags']}),
        'data': _data(reg['data']),
    }


TRATADORES = {
    'catalogo': tratar_conteudo,
    'interacoes': tratar_interacao,
    'comentarios': tratar_comentario,
}


def _mudou(original: dict, tratado: dict) -> bool:
    """Diz se a padronização alterou algum valor (contador `corrigidos`).

    A comparação é feita contra o valor **cru**, sem normalizar o lado
    esquerdo — normalizar os dois lados apagaria exatamente a diferença
    que se quer medir, e o contador viveria zerado.

    Converter `'10'` em `10` não conta como correção: isso é leitura de
    tipo, não conserto. Conta o que mudou o conteúdo: espaço sobrando,
    caixa trocada, grafia de data, tag repetida.
    """
    for campo, novo in tratado.items():
        if campo not in original:
            continue
        antigo = original[campo]
        if antigo is None or novo is None:
            if antigo is not novo:
                return True
            continue

        if isinstance(novo, (date, datetime)):
            if str(antigo).strip() != novo.isoformat():
                return True
        elif isinstance(novo, (list, tuple)):
            # Compara conteúdo, não ordem. As tags saem ordenadas para o
            # resultado ser determinístico, mas reordenar não é consertar:
            # contar isso como correção marcava 834 dos 994 comentários,
            # quando na verdade nenhum deles tinha defeito algum (nenhuma
            # tag com maiúscula, espaço sobrando ou repetição).
            if sorted(str(t) for t in antigo) != list(novo):
                return True
        elif isinstance(novo, (int, float)) and not isinstance(novo, bool):
            try:
                if float(str(antigo).strip()) != float(novo):
                    return True
            except (TypeError, ValueError):
                return True
        elif str(antigo) != str(novo):
            return True
    return False


def tratar(fonte: str, classificados: list[dict]) -> tuple[list[dict], int]:
    """Trata os registros válidos de uma fonte.

    Devolve `(tratados, corrigidos)`. Só registros classificados como
    `valido` seguem — inválidos, incompletos e duplicados ficam de fora
    da carga, mas continuam contabilizados no resumo do RF05.
    """
    tratador = TRATADORES[fonte]
    tratados, corrigidos = [], 0
    for item in classificados:
        if item['classificacao'] != VALIDO:
            continue
        limpo = tratador(item['registro'])
        corrigidos += _mudou(item['registro'], limpo)
        tratados.append(limpo)
    return tratados, corrigidos


# ── entidades derivadas ───────────────────────────────────────
def derivar_categorias(conteudos: list[dict]) -> list[dict]:
    """Tabela `categoria` a partir dos valores distintos do catálogo."""
    nomes = sorted({c['categoria'] for c in conteudos})
    return [{'categoria_id': i, 'nome': nome} for i, nome in enumerate(nomes, 1)]


def derivar_usuarios(interacoes: list[dict], comentarios: list[dict]) -> list[dict]:
    """Tabela `usuario` derivada dos identificadores referenciados (G1).

    Nenhuma das três fontes traz dados de usuário — só o `usuario_id`.
    O RF06 exige a entidade, então ela é derivada daqui, com a data da
    primeira e da última atividade como colunas úteis. Decisão registrada
    no README.
    """
    atividade: dict[int, list[datetime]] = {}
    for i in interacoes:
        atividade.setdefault(i['usuario_id'], []).append(i['data_hora'])
    for c in comentarios:
        atividade.setdefault(c['usuario_id'], []).append(
            datetime.combine(c['data'], datetime.min.time()))

    return [{'usuario_id': uid,
             'primeira_atividade': min(datas),
             'ultima_atividade': max(datas)}
            for uid, datas in sorted(atividade.items())]


# ── gravação ──────────────────────────────────────────────────
def _serializavel(valor):
    return valor.isoformat() if isinstance(valor, (date, datetime)) else valor


def gravar(destino: Path, nome: str, registros: list[dict]) -> Path:
    """Grava os tratados em `dados/processados/` (RF04).

    CSV para o catálogo (tabular), JSON para o resto — comentários têm
    lista de tags, que num CSV viraria texto e precisaria ser reparseada.
    """
    destino.mkdir(parents=True, exist_ok=True)
    if not registros:
        raise ValueError(f'nada para gravar em {nome}')

    tem_lista = any(isinstance(v, (list, tuple)) for v in registros[0].values())
    if tem_lista:
        caminho = destino / f'{nome}.json'
        caminho.write_text(
            json.dumps([{k: _serializavel(v) for k, v in r.items()} for r in registros],
                       indent=2, ensure_ascii=False),
            encoding='utf-8')
    else:
        caminho = destino / f'{nome}.csv'
        with open(caminho, 'w', encoding='utf-8', newline='') as f:
            # `lineterminator='\n'`: o csv escreve CRLF por padrão (RFC 4180),
            # e com `core.autocrlf=input` o git grava LF no blob. O arquivo
            # versionado passaria a divergir do gerado — aparecendo como
            # sempre modificado em quem tem outra configuração de autocrlf.
            escritor = csv.DictWriter(f, fieldnames=list(registros[0]),
                                      lineterminator='\n')
            escritor.writeheader()
            escritor.writerows({k: _serializavel(v) for k, v in r.items()}
                               for r in registros)
    return caminho
