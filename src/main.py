"""Orquestrador do pipeline (RF01).

    python -m src.main              # roda tudo, sem argumento obrigatório
    python -m src.main --ajuda      # o que dá para fazer
    python -m src.main --ate carga  # para depois de uma etapa

As etapas rodam em ordem de dependência e cada uma é cronometrada pelo
registro do RF14. Uma etapa que quebra interrompe o pipeline — seguir em
cima de etapa quebrada só produz erro mais adiante, num lugar onde a causa
já não é visível.
"""

import argparse
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from .carga import mongo, postgres
from .config import Config
from .dashboard import montar as montar_dashboard
from .ingestao import leitura, tratamento, validacao
from .ingestao import resumo as resumo_mod
from .log import Registro
from .recomendacao import motor
from .vetorial import busca, embeddings

ETAPAS = ('leitura', 'validacao', 'tratamento', 'carga', 'mongo',
          'embeddings', 'busca', 'recomendacao', 'dashboard')


def argumentos(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog='python -m src.main',
        description='Pipeline do Desafio 1 — ingestão, PostgreSQL, MongoDB, '
                    'embeddings, recomendação e dashboard.',
        add_help=False)
    p.add_argument('-h', '--help', '--ajuda', action='help',
                   help='mostra esta mensagem e sai')
    p.add_argument('--ate', choices=ETAPAS, metavar='ETAPA',
                   help=f'para depois desta etapa ({", ".join(ETAPAS)})')
    p.add_argument('--config', help='caminho de um config.yaml alternativo')
    return p.parse_args(argv)


def _deve_parar(etapa: str, ate: str | None) -> bool:
    return bool(ate) and ETAPAS.index(etapa) >= ETAPAS.index(ate)


def executar(args: argparse.Namespace) -> int:
    cfg = Config(args.config)
    registro = Registro(cfg.artefatos / 'execucao.json')
    resumo = resumo_mod.Resumo()

    if faltando := cfg.conferir_segredos():
        registro.falha('conexao', '.env',
                       f'variáveis ausentes: {", ".join(faltando)}',
                       'copie .env.example para .env e preencha DB_PASSWORD')
        registro.encerrar()
        return 1

    tabelas = {n: cfg.tabela(n) for n in
               ('categoria', 'usuario', 'conteudo', 'interacao',
                'conteudo_embedding', 'recomendacao')}

    # ── 1. leitura (RF02) ─────────────────────────────────────
    with registro.etapa('leitura das fontes'):
        fontes = leitura.ler_fontes(cfg.fontes, registro)
    if _deve_parar('leitura', args.ate):
        return _encerrar(registro, resumo, cfg)

    # ── 2. validação (RF03) ───────────────────────────────────
    with registro.etapa('validação e classificação'):
        classificados = {'catalogo': validacao.classificar('catalogo',
                                                           fontes['catalogo'])}
        # Os ids válidos do catálogo são a referência das outras duas fontes.
        ids_conteudo = {int(c['registro']['conteudo_id'])
                        for c in classificados['catalogo']
                        if c['classificacao'] == validacao.VALIDO}

        for nome in ('interacoes', 'comentarios'):
            classificados[nome] = validacao.classificar(
                nome, fontes[nome], ids_conteudo=ids_conteudo)

        for nome, itens in classificados.items():
            registro.rejeitados(nome, validacao.motivos(itens))
    if _deve_parar('validacao', args.ate):
        return _encerrar(registro, resumo, cfg)

    # ── 3. tratamento (RF04) e resumo (RF05) ──────────────────
    with registro.etapa('tratamento e padronização'):
        tratados = {}
        for nome, itens in classificados.items():
            tratados[nome], corrigidos = tratamento.tratar(nome, itens)
            resumo.fonte(nome, len(fontes[nome]), validacao.contar(itens),
                         corrigidos, validacao.motivos(itens))
            destino = tratamento.gravar(cfg.processados, nome, tratados[nome])
            registro._anunciar(f'{nome}: {len(tratados[nome])} tratados -> {destino.name}')

        categorias = tratamento.derivar_categorias(tratados['catalogo'])
        usuarios = tratamento.derivar_usuarios(tratados['interacoes'],
                                               tratados['comentarios'])
        registro._anunciar(f'derivados: {len(categorias)} categorias, '
                           f'{len(usuarios)} usuários')
    if _deve_parar('tratamento', args.ate):
        return _encerrar(registro, resumo, cfg)

    # ── 4. PostgreSQL (RF06) + views (RF12) ───────────────────
    with registro.etapa('carga no PostgreSQL'):
        postgres.aplicar_ddl(cfg.schema, registro)
        linhas = postgres.preparar_tabelas(tratados['catalogo'],
                                           tratados['interacoes'],
                                           categorias, usuarios)
        postgres.carregar(cfg.schema, linhas, registro, resumo)
        postgres.aplicar_views(registro)
    if _deve_parar('carga', args.ate):
        return _encerrar(registro, resumo, cfg)

    # ── 5. MongoDB (RF07) ─────────────────────────────────────
    with registro.etapa('carga no MongoDB'):
        mongo.carregar(cfg.colecao_mongo, tratados['comentarios'],
                       tratados['catalogo'], registro, resumo)
        mongo.demonstrar(cfg.colecao_mongo, registro)
    if _deve_parar('mongo', args.ate):
        return _encerrar(registro, resumo, cfg)

    # ── 6. embeddings (RF08) ──────────────────────────────────
    with registro.etapa('geração dos embeddings'):
        n = embeddings.gerar(tabelas['conteudo_embedding'], tratados['catalogo'],
                             cfg.modelo, registro, resumo)
        conferencia = embeddings.conferir(tabelas['conteudo_embedding'], n, registro)
        registro._anunciar(f'conferência: {conferencia["total"]} vetores de '
                           f'{conferencia["dimensoes"]} dimensões, modelo '
                           f'{conferencia["modelo"]}')
    if _deve_parar('embeddings', args.ate):
        return _encerrar(registro, resumo, cfg)

    # ── 7. busca semântica (RF09) ─────────────────────────────
    with registro.etapa('busca semântica'):
        busca.demonstrar(tabelas['conteudo_embedding'], tabelas['conteudo'],
                         tabelas['categoria'],
                         cfg.vetorial['consultas_demonstracao'],
                         cfg.vetorial['limite_busca'],
                         cfg.artefatos / 'buscas.json', registro)
    if _deve_parar('busca', args.ate):
        return _encerrar(registro, resumo, cfg)

    # ── 8. recomendação (RF10, RF11) ──────────────────────────
    with registro.etapa('recomendação'):
        estado = motor.carregar_estado(
            {'embedding': tabelas['conteudo_embedding'],
             'conteudo': tabelas['conteudo'],
             'categoria': tabelas['categoria'],
             'interacao': tabelas['interacao']},
            cfg.colecao_mongo,
            cfg.recomendacao['avaliacao_positiva_minima'], registro)
        recomendacoes = motor.calcular(estado, cfg.recomendacao, registro)
        motor.persistir(tabelas['recomendacao'], recomendacoes, registro, resumo)

        for r in motor.amostra(recomendacoes, estado):
            registro._anunciar(f'  usuário {r["usuario_id"]} · {r["posicao"]}º '
                               f'[{r["pontuacao"]:.1f} {r["classificacao"]}] '
                               f'{r["titulo"]}')
    if _deve_parar('recomendacao', args.ate):
        return _encerrar(registro, resumo, cfg)

    # ── 9. dashboard (RF13) ───────────────────────────────────
    with registro.etapa('dashboard no Superset'):
        montar_dashboard.montar(
            cfg.schema, cfg.painel['titulo'], cfg.painel['nome_banco_superset'],
            cfg.artefatos.parent / 'dashboard' / 'desafio_1.zip', registro)

    return _encerrar(registro, resumo, cfg)


def _encerrar(registro: Registro, resumo, cfg: Config) -> int:
    """Grava o resumo do RF05 e o registro do RF14."""
    caminho = resumo.gravar(cfg.artefatos / 'resumo_ingestao.json')
    resumo.exibir()
    registro._anunciar(f'resumo da ingestão em {caminho}')
    registro.encerrar()
    return 1 if registro.houve_falha else 0


def main(argv=None) -> int:
    args = argumentos(argv)
    try:
        return executar(args)
    except KeyboardInterrupt:
        print('\n  interrompido pelo usuário')
        return 130


if __name__ == '__main__':
    sys.exit(main())
