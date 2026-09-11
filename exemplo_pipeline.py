"""Pipeline de referência — prova que o toolkit funciona ponta a ponta.

    python exemplo_pipeline.py            # ingestão + KPIs
    python exemplo_pipeline.py --superset # cria também o dashboard

Faz o percurso completo das aulas sobre dados de exemplo:
  CSV + JSON  ->  PostgreSQL (colunas + JSONB)  ->  embeddings (pgvector)
              ->  KPIs  ->  dashboard no Superset

Quando o desafio chegar, copie este arquivo e troque os dados e os KPIs.
"""

import argparse

from toolkit import ingestao, kpis, vetorial
from toolkit.db import consultar, executar

PREFIXO = 'ex_'   # prefixo próprio, para não colidir com as tabelas das aulas


def etapa_ingestao() -> None:
    print('\n[1/4] INGESTÃO')

    ok, msg = ingestao.csv_bem_formado('dados/exemplo_vendas.csv')
    print(f'  validação do CSV: {msg}')
    if not ok:
        raise SystemExit('  CSV malformado — corrija antes de ingerir')

    ingestao.ingerir_arquivo('dados/exemplo_vendas.csv',
                             f'{PREFIXO}vendas', pk='id')
    ingestao.ingerir_json_bruto('dados/exemplo_eventos.json',
                                f'{PREFIXO}eventos', chave='evento_id')


def etapa_vetorial() -> None:
    print('\n[2/4] EMBEDDINGS')
    linhas = consultar(f'SELECT id, produto || \' — \' || categoria AS texto '
                       f'FROM {PREFIXO}vendas')
    vetorial.criar_tabela_vetorial(f'{PREFIXO}vendas_vetor')
    n = vetorial.indexar_textos(f'{PREFIXO}vendas_vetor',
                                [(reg['id'], reg['texto']) for reg in linhas])
    print(f'  {n} itens indexados (384 dimensões)')

    achados = vetorial.buscar(f'{PREFIXO}vendas_vetor', 'equipamento de informática', 3)
    for a in achados:
        print(f"    sim={a['similaridade']:.3f}  {a['conteudo']}")


def etapa_kpis() -> dict:
    print('\n[3/4] INDICADORES')
    t = f'{PREFIXO}vendas'
    r = consultar(f'SELECT SUM(valor) s, AVG(valor) m, COUNT(*) n FROM {t}')[0]

    ind = {'receita': float(r['s'] or 0),
           'ticket': float(r['m'] or 0),
           'vendas': int(r['n'] or 0),
           'taxa_aprovadas': kpis.taxa(t, 'status', 'aprovada')}

    kpis.exibir('Receita total', ind['receita'], ' R$')
    kpis.exibir('Ticket médio', ind['ticket'], ' R$')
    kpis.exibir('Total de vendas', ind['vendas'])
    kpis.exibir('Taxa de aprovação', ind['taxa_aprovadas'], ' %')

    kpis.exibir_tabela(kpis.distribuicao(t, 'categoria'), 'Por categoria')
    kpis.exibir_tabela(kpis.distribuicao(t, 'regiao'), 'Por região')
    return ind


def etapa_superset() -> None:
    print('\n[4/4] DASHBOARD')
    from toolkit import superset as sup

    s = sup.Superset()
    db = s.garantir_banco('PostgreSQL - desafio')
    ds = s.garantir_dataset(f'{PREFIXO}vendas', db)
    print(f'  banco={db}  dataset={ds}')

    receita = sup.m_simples('valor', 'SUM', 'Receita')
    ticket  = sup.m_simples('valor', 'AVG', 'Ticket médio')

    def novo(nome, spec):
        viz, params = spec
        return s.criar_grafico(nome, viz, ds, params)

    c_receita = novo('EX — Receita Total', sup.kpi(receita, 'soma das vendas'))
    c_ticket  = novo('EX — Ticket Médio', sup.kpi(ticket, 'média por venda'))
    c_qtd     = novo('EX — Total de Vendas', sup.kpi(sup.CONTAGEM, 'transações', ',d'))
    c_cat     = novo('EX — Receita por Categoria', sup.barras('categoria', receita))
    c_reg     = novo('EX — Vendas por Região', sup.rosca('regiao', sup.CONTAGEM))
    c_tempo   = novo('EX — Evolução da Receita', sup.linha('data_venda', receita))
    c_tab     = novo('EX — Detalhamento', sup.tabela(['categoria'],
                                                     [receita, ticket, sup.CONTAGEM]))

    dash = s.montar_dashboard('Painel do Desafio — Exemplo', [
        [(c_receita, 4), (c_ticket, 4), (c_qtd, 4)],
        [(c_cat, 6), (c_reg, 6)],
        [(c_tempo, 6), (c_tab, 6)],
    ])
    print(f'\n  http://localhost:8088/superset/dashboard/{dash}/')


def limpar() -> None:
    for t in (f'{PREFIXO}vendas_vetor', f'{PREFIXO}vendas', f'{PREFIXO}eventos'):
        executar(f'DROP TABLE IF EXISTS {t}')
    print('tabelas de exemplo removidas')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--superset', action='store_true', help='criar o dashboard')
    ap.add_argument('--limpar', action='store_true', help='apagar as tabelas ex_*')
    args = ap.parse_args()

    if args.limpar:
        limpar()
        return

    etapa_ingestao()
    etapa_vetorial()
    etapa_kpis()
    if args.superset:
        etapa_superset()
    print('\nPipeline concluído.')


if __name__ == '__main__':
    main()
