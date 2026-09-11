"""Testes do tratamento e da padronização (RF04).

Mesma lógica dos testes de validação: os arquivos reais já estão
padronizados, então a prova de que a padronização funciona são registros
sintéticos sujos — espaço sobrando, caixa trocada, data em outra grafia.
"""

from datetime import date, datetime

from src.ingestao.tratamento import (
    derivar_categorias,
    derivar_usuarios,
    tratar,
    tratar_comentario,
    tratar_conteudo,
    tratar_interacao,
)
from src.ingestao.validacao import VALIDO


def test_espacos_das_pontas_e_internos_sao_removidos():
    limpo = tratar_conteudo({
        'conteudo_id': ' 7 ', 'titulo': '  Banco   de    Dados  ',
        'tipo': 'Curso', 'categoria': 'Banco de Dados', 'nivel': 'Básico',
        'carga_horaria_min': ' 90 ', 'data_publicacao': '2025-03-06',
        'descricao': '  texto  com   espaços  ', 'autor': ' Equipe FIC ',
    })
    assert limpo['titulo'] == 'Banco de Dados'
    assert limpo['descricao'] == 'texto com espaços'
    assert limpo['autor'] == 'Equipe FIC'
    assert limpo['conteudo_id'] == 7
    assert limpo['carga_horaria_min'] == 90


def test_categoricos_voltam_para_a_forma_canonica():
    limpo = tratar_conteudo({
        'conteudo_id': '1', 'titulo': 'x', 'tipo': '  VÍDEO ',
        'categoria': 'inteligência artificial', 'nivel': 'bÁsIcO',
        'carga_horaria_min': '10', 'data_publicacao': '2025-01-01',
        'descricao': 'd', 'autor': 'a',
    })
    assert limpo['tipo'] == 'Vídeo'
    assert limpo['categoria'] == 'Inteligência Artificial'
    assert limpo['nivel'] == 'Básico'


def test_datas_convergem_para_um_formato_unico():
    """O formato básico do ISO (`20250306`) é aceito na validação e sai
    daqui como `date`, igual ao que veio em formato estendido."""
    base = {'conteudo_id': '1', 'titulo': 'x', 'tipo': 'Curso',
            'categoria': 'Banco de Dados', 'nivel': 'Básico',
            'carga_horaria_min': '10', 'descricao': 'd', 'autor': 'a'}
    basico = tratar_conteudo(base | {'data_publicacao': '20250306'})
    estendido = tratar_conteudo(base | {'data_publicacao': '2025-03-06'})
    assert basico['data_publicacao'] == estendido['data_publicacao'] == date(2025, 3, 6)


def test_tipos_numericos_sao_convertidos():
    limpo = tratar_interacao({
        'usuario_id': '10', 'conteudo_id': '1', 'tipo_interacao': 'visualização',
        'data_hora': '2026-03-21T10:54:52', 'tempo_consumido': '28',
        'percentual_conclusao': '42.5', 'avaliacao_atribuida': '4',
    })
    assert limpo['usuario_id'] == 10
    assert limpo['tempo_consumido'] == 28.0
    assert limpo['percentual_conclusao'] == 42.5
    assert limpo['avaliacao_atribuida'] == 4.0
    assert limpo['data_hora'] == datetime(2026, 3, 21, 10, 54, 52)


def test_ausencia_de_nota_continua_ausente():
    """Padronizar não pode inventar valor: `null` vira `None`, não zero."""
    limpo = tratar_interacao({
        'usuario_id': 10, 'conteudo_id': 1, 'tipo_interacao': 'visualização',
        'data_hora': '2026-03-21T10:54:52', 'tempo_consumido': 28,
        'percentual_conclusao': 42.5, 'avaliacao_atribuida': None,
    })
    assert limpo['avaliacao_atribuida'] is None


def test_tags_ficam_em_caixa_baixa_sem_repeticao():
    limpo = tratar_comentario({
        'usuario_id': 10, 'conteudo_id': 1, 'avaliacao': 5,
        'comentario': 'ok', 'tags': [' LGPD ', 'lgpd', 'Essencial'],
        'data': '2026-03-02',
    })
    assert limpo['tags'] == ['essencial', 'lgpd']


def test_reordenar_tags_nao_conta_como_correcao():
    """As tags saem ordenadas para o resultado ser determinístico, mas
    ordenar não é consertar. Contar a reordenação inflava o contador para
    834 dos 994 comentários, sendo que nenhum tinha defeito — nem
    maiúscula, nem espaço, nem tag repetida."""
    classificados = [{'classificacao': VALIDO, 'motivo': None, 'registro': {
        'usuario_id': 10, 'conteudo_id': 1, 'avaliacao': 5,
        'comentario': 'ok', 'tags': ['lgpd', 'anonimizacao', 'essencial'],
        'data': '2026-03-02'}}]
    tratados, corrigidos = tratar('comentarios', classificados)
    assert tratados[0]['tags'] == ['anonimizacao', 'essencial', 'lgpd']
    assert corrigidos == 0


def test_tag_com_maiuscula_ainda_conta_como_correcao():
    classificados = [{'classificacao': VALIDO, 'motivo': None, 'registro': {
        'usuario_id': 10, 'conteudo_id': 1, 'avaliacao': 5,
        'comentario': 'ok', 'tags': ['LGPD', 'lgpd'], 'data': '2026-03-02'}}]
    tratados, corrigidos = tratar('comentarios', classificados)
    assert tratados[0]['tags'] == ['lgpd']
    assert corrigidos == 1


def test_apenas_validos_seguem_e_corrigidos_conta_o_que_mudou():
    classificados = [
        {'classificacao': VALIDO, 'motivo': None, 'registro': {
            'usuario_id': 10, 'conteudo_id': 1, 'avaliacao': 5,
            'comentario': '  texto   sujo  ', 'tags': ['A'], 'data': '2026-03-02'}},
        {'classificacao': VALIDO, 'motivo': None, 'registro': {
            'usuario_id': 20, 'conteudo_id': 2, 'avaliacao': 4,
            'comentario': 'texto limpo', 'tags': ['b'], 'data': '2026-03-03'}},
        {'classificacao': 'invalido', 'motivo': 'x', 'registro': {}},
    ]
    tratados, corrigidos = tratar('comentarios', classificados)
    assert len(tratados) == 2      # o inválido não entra na carga
    assert corrigidos == 1         # só o primeiro precisou de limpeza


def test_usuarios_sao_derivados_das_duas_fontes():
    """A tabela `usuario` não tem fonte própria (lacuna G1): sai dos
    identificadores referenciados nas interações e nos comentários."""
    interacoes = [
        {'usuario_id': 1, 'data_hora': datetime(2026, 1, 5, 10, 0)},
        {'usuario_id': 1, 'data_hora': datetime(2026, 3, 5, 10, 0)},
    ]
    comentarios = [{'usuario_id': 2, 'data': date(2026, 2, 1)}]
    usuarios = derivar_usuarios(interacoes, comentarios)

    assert [u['usuario_id'] for u in usuarios] == [1, 2]
    assert usuarios[0]['primeira_atividade'] == datetime(2026, 1, 5, 10, 0)
    assert usuarios[0]['ultima_atividade'] == datetime(2026, 3, 5, 10, 0)


def test_categorias_derivadas_sao_unicas_e_numeradas():
    conteudos = [{'categoria': 'Inteligência Artificial'},
                 {'categoria': 'Banco de Dados'},
                 {'categoria': 'Inteligência Artificial'}]
    assert derivar_categorias(conteudos) == [
        {'categoria_id': 1, 'nome': 'Banco de Dados'},
        {'categoria_id': 2, 'nome': 'Inteligência Artificial'},
    ]
