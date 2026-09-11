"""Cliente da API do Superset e construtor de dashboards.

Três coisas que custaram a descobrir e estão resolvidas aqui:

1. CSRF — o token só vale com o cookie de sessão que o gerou, por isso
   o cliente mantém um cookie jar.
2. O Superset roda em contêiner: para alcançar o PostgreSQL do host ele
   usa o gateway do Docker (172.17.0.1), não 'localhost'.
3. Vincular um gráfico ao dashboard NÃO o posiciona. É preciso gravar
   `position_json` (com o `uuid` de cada gráfico) e declarar os gráficos
   em `chart_configuration` no `json_metadata`.
"""

import http.cookiejar
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .db import uri_sqlalchemy

BASE = os.getenv('SUPERSET_URL', 'http://localhost:8088')
USUARIO = os.getenv('SUPERSET_USER', 'admin')
SENHA = os.getenv('SUPERSET_PASS', 'admin')
DB_HOST_CONTAINER = os.getenv('SUPERSET_DB_HOST', '172.17.0.1')

LARGURA_GRADE = 12
ALTURA_KPI = 40
ALTURA_GRAFICO = 52


class Superset:
    def __init__(self, base=BASE, usuario=USUARIO, senha=SENHA):
        self.base = base
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))
        self.token = self._req('/api/v1/security/login', {
            'username': usuario, 'password': senha,
            'provider': 'db', 'refresh': True})['access_token']
        self.csrf = self._req('/api/v1/security/csrf_token/')['result']

    def _req(self, path, data=None, method=None):
        h = {'Content-Type': 'application/json'}
        if getattr(self, 'token', None):
            h['Authorization'] = f'Bearer {self.token}'
        if getattr(self, 'csrf', None):
            h['X-CSRFToken'] = self.csrf
            h['Referer'] = self.base
        req = urllib.request.Request(
            self.base + path,
            method=method or ('POST' if data is not None else 'GET'),
            data=json.dumps(data).encode() if data is not None else None,
            headers=h)
        try:
            with self.opener.open(req, timeout=90) as r:
                corpo = r.read()
                return json.loads(corpo) if corpo else {}
        except urllib.error.HTTPError as e:
            texto = e.read().decode('utf8', 'replace')
            try:
                return {'_erro': e.code, **json.loads(texto)}
            except Exception:
                return {'_erro': e.code, '_corpo': texto[:400]}

    get = lambda self, p: self._req(p)                      # noqa: E731
    post = lambda self, p, d: self._req(p, d)               # noqa: E731
    put = lambda self, p, d: self._req(p, d, method='PUT')  # noqa: E731

    def achar(self, recurso: str, campo: str, valor: str):
        q = urllib.parse.quote(json.dumps(
            {'filters': [{'col': campo, 'opr': 'eq', 'value': valor}]}))
        res = self.get(f'/api/v1/{recurso}/?q={q}').get('result') or []
        return res[0]['id'] if res else None

    # ── blocos de construção ─────────────────────────────────
    def garantir_banco(self, nome='PostgreSQL - desafio') -> int:
        existe = self.achar('database', 'database_name', nome)
        if existe:
            return existe
        r = self.post('/api/v1/database/', {
            'database_name': nome,
            'sqlalchemy_uri': uri_sqlalchemy(DB_HOST_CONTAINER),
            'expose_in_sqllab': True})
        return r.get('id')

    def garantir_dataset(self, tabela: str, db_id: int, schema='public') -> int:
        for d in self.get('/api/v1/dataset/?q=(page_size:500)').get('result', []):
            if (d['table_name'] == tabela
                    and d.get('database', {}).get('id') == db_id):
                return d['id']
        r = self.post('/api/v1/dataset/',
                      {'database': db_id, 'schema': schema, 'table_name': tabela})
        return r.get('id')

    def criar_grafico(self, nome: str, viz: str, ds_id: int, params: dict) -> int:
        existe = self.achar('chart', 'slice_name', nome)
        if existe:
            return existe
        params = {'datasource': f'{ds_id}__table', 'viz_type': viz,
                  'row_limit': 1000, **params}
        r = self.post('/api/v1/chart/', {
            'slice_name': nome, 'viz_type': viz,
            'datasource_id': ds_id, 'datasource_type': 'table',
            'params': json.dumps(params)})
        if '_erro' in r:
            print(f'  ! {nome}: {str(r)[:140]}')
            return 0
        return r['id']

    def montar_dashboard(self, titulo: str, linhas: list[list[tuple[int, int]]]) -> int:
        """`linhas` = [[(chart_id, largura), ...], ...], largura somando 12."""
        dash = self.achar('dashboard', 'dashboard_title', titulo)
        if not dash:
            dash = self.post('/api/v1/dashboard/',
                             {'dashboard_title': titulo, 'published': True}).get('id')

        todos = [c for linha in linhas for c, _ in linha if c]
        for cid in todos:
            self.put(f'/api/v1/chart/{cid}', {'dashboards': [dash]})

        pos = {
            'DASHBOARD_VERSION_KEY': 'v2',
            'ROOT_ID': {'type': 'ROOT', 'id': 'ROOT_ID', 'children': ['GRID_ID']},
            'GRID_ID': {'type': 'GRID', 'id': 'GRID_ID', 'children': [],
                        'parents': ['ROOT_ID']},
            'HEADER_ID': {'type': 'HEADER', 'id': 'HEADER_ID',
                          'meta': {'text': titulo}},
        }
        for i, linha in enumerate(linhas, 1):
            rid = f'ROW-{dash}-{i}'
            pos['GRID_ID']['children'].append(rid)
            pos[rid] = {'type': 'ROW', 'id': rid, 'children': [],
                        'meta': {'background': 'BACKGROUND_TRANSPARENT'},
                        'parents': ['ROOT_ID', 'GRID_ID']}
            altura = ALTURA_KPI if i == 1 else ALTURA_GRAFICO
            for cid, largura in linha:
                if not cid:
                    continue
                info = self.get(f'/api/v1/chart/{cid}').get('result', {})
                key = f'CHART-explore-{cid}-1'
                pos[rid]['children'].append(key)
                pos[key] = {
                    'type': 'CHART', 'id': key, 'children': [],
                    'meta': {'chartId': cid, 'width': largura, 'height': altura,
                             'sliceName': info.get('slice_name', ''),
                             'uuid': info.get('uuid', '')},
                    'parents': ['ROOT_ID', 'GRID_ID', rid]}

        meta = {
            'chart_configuration': {
                str(c): {'id': c,
                         'crossFilters': {'scope': 'global', 'chartsInScope': []}}
                for c in todos},
            'global_chart_configuration': {
                'scope': {'rootPath': ['ROOT_ID'], 'excluded': []},
                'chartsInScope': todos},
            'native_filter_configuration': [],
            'expand_all_slices': False, 'timed_refresh_immune_slices': [],
            'default_filters': '{}', 'expanded_slices': {}, 'refresh_frequency': 0,
        }
        self.put(f'/api/v1/dashboard/{dash}',
                 {'position_json': json.dumps(pos), 'json_metadata': json.dumps(meta)})
        return dash


# ── atalhos para métricas e tipos de gráfico comuns ──────────
def m_sql(expr: str, rotulo: str) -> dict:
    return {'expressionType': 'SQL', 'sqlExpression': expr, 'label': rotulo}


def m_simples(coluna: str, agregacao: str, rotulo: str) -> dict:
    return {'expressionType': 'SIMPLE', 'aggregate': agregacao,
            'label': rotulo, 'column': {'column_name': coluna}}


CONTAGEM = m_sql('COUNT(*)', 'Total')


def kpi(metrica: dict, legenda: str = '', formato: str = ',.2f') -> tuple:
    return 'big_number_total', {'metric': metrica, 'subheader': legenda,
                                'y_axis_format': formato}


def medidor(metrica: dict, minimo=0, maximo=100) -> tuple:
    return 'gauge_chart', {'metric': metrica, 'groupby': [],
                           'min_val': minimo, 'max_val': maximo,
                           'number_format': ',.1f', 'value_formatter': '{value}%',
                           'show_progress': True, 'intervals': '60,80,100',
                           'interval_color_indices': '3,2,1'}


def barras(dimensao: str, metrica: dict, horizontal=False, decrescente=True) -> tuple:
    return 'echarts_timeseries_bar', {
        'x_axis': dimensao, 'metrics': [metrica], 'groupby': [],
        'orientation': 'horizontal' if horizontal else 'vertical',
        'x_axis_sort_asc': not decrescente}


def linha(dimensao_tempo: str, metrica: dict, serie: str | None = None) -> tuple:
    return 'echarts_timeseries_line', {
        'x_axis': dimensao_tempo, 'time_grain_sqla': 'P1D',
        'metrics': [metrica], 'groupby': [serie] if serie else []}


def rosca(dimensao: str, metrica: dict) -> tuple:
    return 'pie', {'groupby': [dimensao], 'metric': metrica, 'donut': True,
                   'innerRadius': 45, 'show_labels': True,
                   'label_type': 'key_percent'}


def tabela(dimensoes: list[str], metricas: list[dict]) -> tuple:
    return 'table', {'query_mode': 'aggregate', 'groupby': dimensoes,
                     'metrics': metricas}
