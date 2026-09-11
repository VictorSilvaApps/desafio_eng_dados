"""Registro estruturado de execução (RF14).

O requisito pede oito coisas: início e término, arquivos processados,
registros lidos, registros rejeitados, falhas de conexão, falhas de
embedding, falhas de persistência e tempo de cada etapa. E pede mais uma,
que é a que realmente importa: o registro precisa permitir identificar a
**origem e a causa provável** de cada problema.

Por isso toda falha guarda três campos além da mensagem: em que etapa
aconteceu, sobre qual objeto (arquivo, tabela, id) e qual a causa
provável — um palpite escrito por quem conhece a armadilha, não o
traceback cru. Um traceback diz `OperationalError`; o campo `causa`
diz "PostgreSQL não está aceitando conexão em localhost:5432".
"""

import json
import time
import traceback
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

# As categorias de falha que o RF14 nomeia. `leitura` e `validacao` são
# extras nossos: sem elas, um arquivo ilegível cairia em "outra".
CATEGORIAS = ('conexao', 'embedding', 'persistencia', 'leitura', 'validacao', 'outra')

# Causas prováveis por tipo de erro. Poupa a equipe de reabrir o traceback
# durante a apresentação.
PISTAS = {
    'OperationalError': 'banco não está aceitando conexão — confira o serviço e o host/porta do .env',
    'UndefinedTable': 'tabela não existe — rode sql/criar_banco.sql antes da carga',
    'UndefinedColumn': 'coluna não existe — o DDL e o DataFrame divergiram',
    'UniqueViolation': 'identificador repetido — falta ON CONFLICT ou a chave está errada',
    'ForeignKeyViolation': 'referência para registro inexistente — carregue a tabela pai primeiro',
    'ServerSelectionTimeoutError': 'MongoDB não respondeu — confira se o mongod está ativo',
    'FileNotFoundError': 'arquivo não encontrado — confira os caminhos em config.yaml',
    'OutOfMemoryError': 'memória insuficiente para o lote de embeddings — reduza o tamanho do lote',
}


def _agora() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec='seconds')


class Registro:
    """Acumula os eventos da execução e grava um JSON ao final."""

    def __init__(self, caminho: Path | str):
        self.caminho = Path(caminho)
        self.inicio = time.perf_counter()
        self.eventos = {
            'inicio': _agora(),
            'termino': None,
            'duracao_s': None,
            'arquivos_processados': [],
            'registros_lidos': {},
            'registros_rejeitados': {},
            'falhas': [],
            'etapas': [],
        }
        self._anunciar(f'início da execução em {self.eventos["inicio"]}')

    # ── saída no console ──────────────────────────────────────
    @staticmethod
    def _anunciar(texto: str, nivel: str = 'info') -> None:
        marca = {'info': '  ', 'etapa': '▶ ', 'erro': '✗ ', 'ok': '✓ '}[nivel]
        print(f'{marca}{texto}', flush=True)

    # ── as oito categorias do RF14 ────────────────────────────
    def arquivo(self, caminho: Path | str, registros: int) -> None:
        """Arquivo processado + quantos registros vieram dele."""
        nome = Path(caminho).name
        self.eventos['arquivos_processados'].append(
            {'arquivo': nome, 'caminho': str(caminho), 'registros': registros})
        self.eventos['registros_lidos'][nome] = registros
        self._anunciar(f'{nome}: {registros} registros lidos')

    def rejeitados(self, fonte: str, motivos: dict[str, int]) -> None:
        """Registros não-válidos de uma fonte, agrupados por motivo."""
        if not motivos:
            return
        self.eventos['registros_rejeitados'][fonte] = motivos
        total = sum(motivos.values())
        self._anunciar(f'{fonte}: {total} registros não-válidos')
        for motivo, n in sorted(motivos.items(), key=lambda kv: -kv[1]):
            self._anunciar(f'    {n:>4}x  {motivo}')

    def falha(self, categoria: str, origem: str, erro: BaseException | str,
              causa: str | None = None) -> None:
        """Registra uma falha com origem e causa provável.

        `categoria` precisa ser uma de CATEGORIAS — o RF14 exige separar
        conexão, embedding e persistência, e um campo livre viraria sopa.
        """
        if categoria not in CATEGORIAS:
            raise ValueError(f'categoria inválida: {categoria!r}; use {CATEGORIAS}')

        tipo = type(erro).__name__ if isinstance(erro, BaseException) else 'Erro'
        self.eventos['falhas'].append({
            'quando': _agora(),
            'categoria': categoria,
            'origem': origem,
            'tipo': tipo,
            'mensagem': str(erro).strip(),
            'causa_provavel': causa or PISTAS.get(tipo, 'sem pista registrada'),
            'traceback': (traceback.format_exc().splitlines()[-3:]
                          if isinstance(erro, BaseException) else None),
        })
        self._anunciar(f'falha de {categoria} em {origem}: {erro}', 'erro')

    @contextmanager
    def etapa(self, nome: str):
        """Cronometra uma etapa principal e registra se ela quebrou."""
        self._anunciar(nome, 'etapa')
        t0 = time.perf_counter()
        estado = 'ok'
        try:
            yield self
        except Exception:
            estado = 'falhou'
            raise
        finally:
            s = round(time.perf_counter() - t0, 2)
            self.eventos['etapas'].append(
                {'etapa': nome, 'duracao_s': s, 'estado': estado})
            self._anunciar(f'{nome} — {estado} em {s}s',
                           'ok' if estado == 'ok' else 'erro')

    # ── encerramento ──────────────────────────────────────────
    def encerrar(self) -> Path:
        self.eventos['termino'] = _agora()
        self.eventos['duracao_s'] = round(time.perf_counter() - self.inicio, 2)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.caminho.write_text(
            json.dumps(self.eventos, indent=2, ensure_ascii=False), encoding='utf-8')

        n_falhas = len(self.eventos['falhas'])
        self._anunciar(
            f'término em {self.eventos["duracao_s"]}s, {n_falhas} falha(s) — '
            f'registro em {self.caminho}',
            'erro' if n_falhas else 'ok')
        return self.caminho

    @property
    def houve_falha(self) -> bool:
        return bool(self.eventos['falhas'])
