"""Testes do motor de validação (RF03).

**Por que estes testes existem.** As três fontes do desafio estão limpas:
zero órfãos, zero duplicatas exatas, zero datas fora do ISO, zero valores
fora de faixa. Rodar os validadores sobre elas produz um resumo com todos
os contadores em zero — indistinguível de uma validação que não foi
implementada.

Então a prova de que a validação funciona são estes registros sintéticos:
um por regra do RF03, cada um quebrado de um jeito específico. Nenhum
arquivo de entrada é modificado; o enunciado exige preservá-los.

Os dois últimos testes são de regressão: protegem contra as duas
armadilhas que produzem números errados neste conjunto de dados.
"""

import pytest

from src.ingestao.validacao import (
    DUPLICADO,
    INCOMPLETO,
    INVALIDO,
    VALIDO,
    classificar,
    contar,
    validar_comentario,
    validar_conteudo,
    validar_interacao,
)

IDS_CONTEUDO = {1, 2, 3}
IDS_USUARIO = {10, 20}


# ── modelos válidos, copiados da forma real dos arquivos ──────
def conteudo(**mudancas) -> dict:
    base = {
        'conteudo_id': '1',
        'titulo': 'Introdução a Bancos de Dados',
        'tipo': 'Curso',
        'categoria': 'Banco de Dados',
        'nivel': 'Básico',
        'carga_horaria_min': '120',
        'data_publicacao': '2025-03-06',
        'descricao': 'Curso introdutório sobre modelagem e consultas.',
        'autor': 'Equipe FIC',
    }
    return base | mudancas


def interacao(**mudancas) -> dict:
    base = {
        'usuario_id': 10,
        'conteudo_id': 1,
        'tipo_interacao': 'visualização',
        'data_hora': '2026-03-21T10:54:52',
        'tempo_consumido': 28,
        'percentual_conclusao': 42.5,
        'avaliacao_atribuida': None,
    }
    return base | mudancas


def comentario(**mudancas) -> dict:
    base = {
        'usuario_id': 10,
        'conteudo_id': 1,
        'avaliacao': 5,
        'comentario': 'Conteúdo claro e objetivo.',
        'tags': ['lgpd', 'essencial', 'didatico'],
        'data': '2026-03-02',
    }
    return base | mudancas


# ── linha de base: o registro íntegro passa ───────────────────
def test_registro_integro_e_valido():
    assert validar_conteudo(conteudo())[0] == VALIDO
    assert validar_interacao(interacao(), IDS_CONTEUDO)[0] == VALIDO
    assert validar_comentario(comentario(), IDS_CONTEUDO)[0] == VALIDO


# ── uma regra do RF03 por teste ───────────────────────────────
@pytest.mark.parametrize('campo', ['titulo', 'tipo', 'categoria', 'nivel',
                                   'carga_horaria_min', 'data_publicacao',
                                   'descricao', 'autor'])
def test_campo_obrigatorio_ausente_e_incompleto(campo):
    classificacao, motivo = validar_conteudo(conteudo(**{campo: ''}))
    assert classificacao == INCOMPLETO
    assert campo in motivo


def test_campo_obrigatorio_faltando_na_chave_e_incompleto():
    reg = conteudo()
    del reg['autor']
    classificacao, motivo = validar_conteudo(reg)
    assert classificacao == INCOMPLETO
    assert 'autor' in motivo


@pytest.mark.parametrize('valor', ['0', '-5', 'abc', ''])
def test_identificador_invalido(valor):
    classificacao, _ = validar_conteudo(conteudo(conteudo_id=valor))
    assert classificacao in (INVALIDO, INCOMPLETO)


@pytest.mark.parametrize('valor', ['06/03/2025', '2025-13-01', '2025-02-30',
                                   'ontem', '2025/03/06'])
def test_data_fora_do_iso_e_invalida(valor):
    classificacao, motivo = validar_conteudo(conteudo(data_publicacao=valor))
    assert classificacao == INVALIDO
    assert 'data_publicacao' in motivo


def test_data_no_formato_basico_do_iso_e_aceita():
    """`20250306` é ISO 8601 válido (formato básico), e o Python aceita
    desde a 3.11. Quem rejeitasse estaria errado: o RF04 pede converter
    para formato único, não recusar uma grafia legítima. A conversão é
    coberta em tests/test_tratamento.py."""
    assert validar_conteudo(conteudo(data_publicacao='20250306'))[0] == VALIDO


@pytest.mark.parametrize('campo,valor', [
    ('tipo', 'Webinar'),
    ('nivel', 'Expert'),
    ('categoria', 'Marketing Digital'),
])
def test_categorico_fora_do_dominio_e_invalido(campo, valor):
    classificacao, motivo = validar_conteudo(conteudo(**{campo: valor}))
    assert classificacao == INVALIDO
    assert campo in motivo


@pytest.mark.parametrize('valor', [-10, -1])
def test_numerico_negativo_e_invalido(valor):
    classificacao, motivo = validar_conteudo(conteudo(carga_horaria_min=str(valor)))
    assert classificacao == INVALIDO
    assert 'carga_horaria_min' in motivo

    classificacao, motivo = validar_interacao(
        interacao(tempo_consumido=valor), IDS_CONTEUDO)
    assert classificacao == INVALIDO
    assert 'tempo_consumido' in motivo


@pytest.mark.parametrize('valor', [0, 6, 7, -1, 10])
def test_avaliacao_fora_da_faixa_e_invalida(valor):
    classificacao, motivo = validar_comentario(
        comentario(avaliacao=valor), IDS_CONTEUDO)
    assert classificacao == INVALIDO
    assert 'avaliacao' in motivo

    classificacao, motivo = validar_interacao(
        interacao(avaliacao_atribuida=valor), IDS_CONTEUDO)
    assert classificacao == INVALIDO
    assert 'avaliacao_atribuida' in motivo


def test_percentual_conclusao_fora_de_0_100_e_invalido():
    for valor in (-0.1, 100.1, 150):
        classificacao, motivo = validar_interacao(
            interacao(percentual_conclusao=valor), IDS_CONTEUDO)
        assert classificacao == INVALIDO
        assert 'percentual_conclusao' in motivo


def test_referencia_a_conteudo_inexistente_e_invalida():
    classificacao, motivo = validar_interacao(
        interacao(conteudo_id=999), IDS_CONTEUDO)
    assert classificacao == INVALIDO
    assert '999' in motivo

    classificacao, motivo = validar_comentario(
        comentario(conteudo_id=999), IDS_CONTEUDO)
    assert classificacao == INVALIDO
    assert '999' in motivo


def test_referencia_a_usuario_inexistente_e_invalida():
    classificacao, motivo = validar_interacao(
        interacao(usuario_id=77), IDS_CONTEUDO, IDS_USUARIO)
    assert classificacao == INVALIDO
    assert '77' in motivo


def test_numerico_incompativel_com_o_categorico():
    """Interação de conclusão precisa ter percentual 100."""
    classificacao, motivo = validar_interacao(
        interacao(tipo_interacao='conclusão', percentual_conclusao=30.0),
        IDS_CONTEUDO)
    assert classificacao == INVALIDO
    assert 'conclusão' in motivo


def test_tags_em_formato_errado_e_invalido():
    classificacao, motivo = validar_comentario(
        comentario(tags='lgpd,essencial'), IDS_CONTEUDO)
    assert classificacao == INVALIDO
    assert 'tags' in motivo


# ── duplicidade ───────────────────────────────────────────────
def test_repetido_e_marcado_como_duplicado_a_partir_da_segunda_ocorrencia():
    registros = [comentario(), comentario(), comentario(usuario_id=20)]
    resultado = classificar('comentarios', registros, ids_conteudo=IDS_CONTEUDO)
    assert [r['classificacao'] for r in resultado] == [VALIDO, DUPLICADO, VALIDO]
    assert contar(resultado) == {'valido': 2, 'invalido': 0,
                                 'incompleto': 0, 'duplicado': 1}


def test_registro_quebrado_e_repetido_e_reportado_como_quebrado():
    """Precedência: a regra intrínseca vence a duplicidade."""
    quebrado = comentario(avaliacao=9)
    resultado = classificar('comentarios', [quebrado, quebrado],
                            ids_conteudo=IDS_CONTEUDO)
    assert [r['classificacao'] for r in resultado] == [INVALIDO, INVALIDO]


# ── regressão: as duas armadilhas deste conjunto de dados ─────
def test_avaliacao_atribuida_nula_nao_e_incompleta():
    """São 644 das 1000 interações, e a ausência é semanticamente correta:
    só existe nota quando o usuário avaliou. Contar como incompleto
    inflaria o contador em 64%."""
    classificacao, motivo = validar_interacao(
        interacao(avaliacao_atribuida=None), IDS_CONTEUDO)
    assert classificacao == VALIDO, motivo


def test_duplicidade_nao_e_detectada_pelo_texto_do_comentario():
    """Só existem 22 textos distintos em 1000 registros — o dado sintético
    recicla frases. Detectar duplicidade por texto marcaria ~978 registros.
    A chave é o par (usuario_id, conteudo_id)."""
    mesmo_texto = 'Conteúdo claro e objetivo.'
    registros = [
        comentario(usuario_id=10, conteudo_id=1, comentario=mesmo_texto),
        comentario(usuario_id=20, conteudo_id=2, comentario=mesmo_texto),
        comentario(usuario_id=10, conteudo_id=3, comentario=mesmo_texto),
    ]
    resultado = classificar('comentarios', registros, ids_conteudo=IDS_CONTEUDO)
    assert all(r['classificacao'] == VALIDO for r in resultado)
