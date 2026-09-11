"""Resumo da ingestão em JSON (RF05).

O requisito nomeia oito informações: lidos, válidos, inválidos,
incompletos, duplicados, corrigidos, carregados por banco e tempo total.
Todas aparecem em `totais`, e `por_fonte` abre cada uma delas por arquivo
— é o recorte que responde "de onde veio o problema" sem abrir o log.
"""

import json
import time
from datetime import UTC, datetime
from pathlib import Path

CHAVES = ('lidos', 'validos', 'invalidos', 'incompletos',
          'duplicados', 'corrigidos')


class Resumo:
    """Acumula os números da ingestão e grava o JSON do RF05."""

    def __init__(self):
        self.inicio = time.perf_counter()
        self.por_fonte: dict[str, dict[str, int]] = {}
        self.motivos: dict[str, dict[str, int]] = {}
        self.carregados: dict[str, dict[str, int]] = {}

    def fonte(self, nome: str, lidos: int, contagem: dict[str, int],
              corrigidos: int, motivos: dict[str, int] | None = None) -> None:
        """Registra os números de uma fonte. `contagem` vem de validacao.contar."""
        self.por_fonte[nome] = {
            'lidos': lidos,
            'validos': contagem['valido'],
            'invalidos': contagem['invalido'],
            'incompletos': contagem['incompleto'],
            'duplicados': contagem['duplicado'],
            'corrigidos': corrigidos,
        }
        if motivos:
            self.motivos[nome] = motivos

    def carregado(self, banco: str, tabela: str, registros: int) -> None:
        """Quantos registros entraram em cada tabela de cada banco."""
        self.carregados.setdefault(banco, {})[tabela] = registros

    @property
    def totais(self) -> dict[str, int]:
        return {c: sum(f[c] for f in self.por_fonte.values()) for c in CHAVES}

    def montar(self) -> dict:
        return {
            'gerado_em': datetime.now(UTC).astimezone().isoformat(timespec='seconds'),
            'tempo_total_s': round(time.perf_counter() - self.inicio, 2),
            'totais': self.totais,
            'por_fonte': self.por_fonte,
            'motivos_dos_nao_validos': self.motivos,
            'carregados_por_banco': self.carregados,
        }

    def gravar(self, caminho: Path) -> Path:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(json.dumps(self.montar(), indent=2, ensure_ascii=False),
                           encoding='utf-8')
        return caminho

    def exibir(self) -> None:
        """Mesmo conteúdo do JSON, em tabela, para o console."""
        dados = self.montar()
        largura = max(len(f) for f in self.por_fonte) if self.por_fonte else 10

        print(f'\n  {"fonte":<{largura}} ' +
              ' '.join(f'{c:>11}' for c in CHAVES))
        print('  ' + '─' * (largura + 1 + 12 * len(CHAVES)))
        for nome, f in self.por_fonte.items():
            print(f'  {nome:<{largura}} ' +
                  ' '.join(f'{f[c]:>11}' for c in CHAVES))
        print('  ' + '─' * (largura + 1 + 12 * len(CHAVES)))
        t = dados['totais']
        print(f'  {"TOTAL":<{largura}} ' + ' '.join(f'{t[c]:>11}' for c in CHAVES))

        for banco, tabelas in dados['carregados_por_banco'].items():
            carga = ', '.join(f'{t}={n}' for t, n in tabelas.items())
            print(f'\n  carregado em {banco}: {carga}')
        print(f'\n  tempo total da ingestão: {dados["tempo_total_s"]}s')
