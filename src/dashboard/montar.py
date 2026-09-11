"""Dashboard no Superset (RF13).

Composição mínima que o requisito exige: 3 cartões de indicador, 1 gráfico
de barras, 1 gráfico de linhas e **2 filtros interativos**.

**Sobre os filtros.** `toolkit.superset.montar_dashboard` grava
`native_filter_configuration: []` fixo — ele monta o layout, mas não cria
filtro nativo nenhum. Em vez de alterar o toolkit (que é compartilhado com
as outras aulas e não deve mudar por causa deste desafio), os filtros são
acrescentados **por cima**, num segundo PUT que relê o `json_metadata`
gravado e só substitui a chave dos filtros. O layout continua sendo
responsabilidade do toolkit; os filtros, deste módulo.

**Por que os três cartões saem de `vw_dashboard_interacoes`** e não da
`vw_indicadores_gerais`: filtro nativo só alcança gráfico cujo dataset
tem a coluna filtrada. Com os cartões apoiados no fato desnormalizado,
mexer no filtro de categoria muda os três números junto com os gráficos —
que é o comportamento que alguém espera de um painel.

**Justificativa de cada gráfico** (o RF13 cobra isso):

- *cartão* para valor único de acompanhamento — não há dimensão a comparar;
- *barras* para comparar categorias entre si — comprimento é a forma mais
  precisa de comparar grandeza;
- *linhas* para série temporal — a continuidade da linha comunica
  tendência, que é a pergunta que se faz de uma data.
"""

import json
import urllib.request
from pathlib import Path

from toolkit.superset import Superset, barras, kpi, linha, m_sql

from ..log import Registro

# Views que viram dataset no Superset.
FATO = 'vw_dashboard_interacoes'
KPI_CONCLUSAO = 'vw_kpi_taxa_conclusao'
KPI_COBERTURA = 'vw_kpi_cobertura_catalogo'

TAXA_CONCLUSAO = (
    "ROUND(100.0 * COUNT(*) FILTER (WHERE tipo_interacao = 'conclusão') "
    "/ NULLIF(COUNT(*) FILTER (WHERE tipo_interacao = 'início'), 0), 1)"
)


def _filtro(indice: int, nome: str, coluna: str, dataset_id: int,
            graficos: list[int]) -> dict:
    """Monta um filtro nativo do tipo seleção."""
    return {
        'id': f'NATIVE_FILTER-desafio-{indice}',
        'name': nome,
        'filterType': 'filter_select',
        'type': 'NATIVE_FILTER',
        'description': f'Filtra o painel por {nome.lower()}.',
        'targets': [{'datasetId': dataset_id, 'column': {'name': coluna}}],
        'defaultDataMask': {'extraFormData': {}, 'filterState': {},
                            'ownState': {}},
        'controlValues': {'multiSelect': True, 'enableEmptyFilter': False,
                          'defaultToFirstItem': False, 'inverseSelection': False,
                          'searchAllOptions': False},
        'cascadeParentIds': [],
        'scope': {'rootPath': ['ROOT_ID'], 'excluded': []},
        'chartsInScope': graficos,
        'tabsInScope': [],
    }


def adicionar_filtros(cliente: Superset, dash_id: int, dataset_id: int,
                      graficos: list[int], registro: Registro) -> int:
    """Acrescenta os 2 filtros interativos ao dashboard já montado.

    Relê o `json_metadata` que o toolkit gravou e substitui apenas
    `native_filter_configuration`, preservando `chart_configuration` e o
    resto — sobrescrever o metadata inteiro desfaria o layout.
    """
    atual = cliente.get(f'/api/v1/dashboard/{dash_id}').get('result', {})
    try:
        meta = json.loads(atual.get('json_metadata') or '{}')
    except json.JSONDecodeError:
        meta = {}

    meta['native_filter_configuration'] = [
        _filtro(1, 'Categoria', 'categoria', dataset_id, graficos),
        _filtro(2, 'Nível', 'nivel', dataset_id, graficos),
    ]

    resposta = cliente.put(f'/api/v1/dashboard/{dash_id}',
                           {'json_metadata': json.dumps(meta)})
    if '_erro' in resposta:
        registro.falha('persistencia', f'dashboard/{dash_id}',
                       str(resposta)[:200],
                       'os filtros não foram gravados — confira se o dataset '
                       'do fato tem as colunas categoria e nivel')
        return 0
    registro._anunciar('2 filtros interativos adicionados (Categoria, Nível)')
    return 2


def exportar(cliente: Superset, dash_id: int, destino: Path,
             registro: Registro) -> Path | None:
    """Baixa o export do dashboard (.zip), entregável da seção 11.

    Não usa `cliente._req` porque aquele método faz `json.loads` da
    resposta, e aqui o corpo é um ZIP binário.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        f'{cliente.base}/api/v1/dashboard/export/?q=!({dash_id})',
        headers={'Authorization': f'Bearer {cliente.token}',
                 'X-CSRFToken': cliente.csrf, 'Referer': cliente.base})
    try:
        with cliente.opener.open(req, timeout=90) as r:
            destino.write_bytes(r.read())
    except Exception as erro:
        registro.falha('persistencia', 'export do dashboard', erro,
                       'o painel existe no Superset, mas o arquivo de export '
                       'não foi gravado — dá para exportar pela UI')
        return None

    registro._anunciar(f'dashboard exportado para {destino} '
                       f'({destino.stat().st_size // 1024} KB)')
    return destino


def montar(schema: str, titulo: str, nome_banco: str, destino_export: Path,
           registro: Registro) -> dict:
    """Cria datasets, gráficos, dashboard e filtros. Idempotente."""
    try:
        cliente = Superset()
    except Exception as erro:
        registro.falha('conexao', 'superset', erro,
                       'Superset não respondeu em SUPERSET_URL — confira se o '
                       'contêiner está de pé')
        raise

    db_id = cliente.garantir_banco(nome_banco)
    if not db_id:
        registro.falha('conexao', 'superset/database', 'não obteve database_id',
                       'o Superset precisa alcançar o PostgreSQL em '
                       'SUPERSET_DB_HOST (172.17.0.1 quando em contêiner), '
                       'não em localhost')
        raise RuntimeError('database do Superset não pôde ser criado')

    ds_fato = cliente.garantir_dataset(FATO, db_id, schema=schema)
    ds_conclusao = cliente.garantir_dataset(KPI_CONCLUSAO, db_id, schema=schema)
    ds_cobertura = cliente.garantir_dataset(KPI_COBERTURA, db_id, schema=schema)
    registro._anunciar(f'datasets: {FATO}={ds_fato}, '
                       f'{KPI_CONCLUSAO}={ds_conclusao}, '
                       f'{KPI_COBERTURA}={ds_cobertura}')

    # ── 3 cartões de indicador ────────────────────────────────
    viz, params = kpi(m_sql('COUNT(*)', 'Interações'), 'total de interações', ',d')
    c1 = cliente.criar_grafico('Desafio 1 — Interações', viz, ds_fato, params)

    viz, params = kpi(m_sql(TAXA_CONCLUSAO, 'Taxa de conclusão'),
                      'conclusões ÷ inícios (%)', ',.1f')
    c2 = cliente.criar_grafico('Desafio 1 — Taxa de conclusão', viz, ds_fato, params)

    viz, params = kpi(m_sql('COUNT(DISTINCT conteudo_id)', 'Conteúdos'),
                      'conteúdos com engajamento', ',d')
    c3 = cliente.criar_grafico('Desafio 1 — Conteúdos alcançados', viz, ds_fato, params)

    # ── 1 gráfico de barras ───────────────────────────────────
    viz, params = barras('categoria',
                         m_sql('ROUND(100.0 * SUM(conclusoes) / '
                               'NULLIF(SUM(inicios), 0), 1)',
                               'Taxa de conclusão (%)'))
    c4 = cliente.criar_grafico('Desafio 1 — Conclusão por categoria',
                               viz, ds_conclusao, params)

    # ── 1 gráfico de linhas ───────────────────────────────────
    viz, params = linha('data_hora', m_sql('COUNT(*)', 'Interações'),
                        serie='tipo_interacao')
    c5 = cliente.criar_grafico('Desafio 1 — Interações por dia',
                               viz, ds_fato, params)

    # ── extra: cobertura do catálogo (KPI 2 em barras) ────────
    viz, params = barras('categoria',
                         m_sql('ROUND(100.0 * SUM(com_interacao) / '
                               'NULLIF(SUM(conteudos), 0), 1)',
                               'Cobertura (%)'))
    c6 = cliente.criar_grafico('Desafio 1 — Cobertura do catálogo',
                               viz, ds_cobertura, params)

    graficos = [g for g in (c1, c2, c3, c4, c5, c6) if g]
    if len(graficos) < 5:
        registro.falha('persistencia', 'superset/charts',
                       f'apenas {len(graficos)} gráficos criados',
                       'o RF13 exige 3 cartões + barras + linhas; confira o '
                       'log da API acima para ver qual falhou')

    dash = cliente.montar_dashboard(titulo, [
        [(c1, 4), (c2, 4), (c3, 4)],      # linha 1: os três cartões
        [(c5, 12)],                        # linha 2: série temporal
        [(c4, 6), (c6, 6)],                # linha 3: as duas barras
    ])

    filtros = adicionar_filtros(cliente, dash, ds_fato, graficos, registro)
    arquivo = exportar(cliente, dash, destino_export, registro)

    registro._anunciar(f'dashboard "{titulo}" em {cliente.base}/superset/'
                       f'dashboard/{dash}/')
    return {'dashboard_id': dash, 'graficos': graficos, 'filtros': filtros,
            'export': str(arquivo) if arquivo else None,
            'url': f'{cliente.base}/superset/dashboard/{dash}/'}
