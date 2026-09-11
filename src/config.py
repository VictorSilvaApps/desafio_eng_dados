"""Carrega o config.yaml e as credenciais do .env (RF01).

A separação é proposital: o `config.yaml` guarda o que a equipe inteira
precisa enxergar e versionar (caminhos, limiares, nomes de consulta); o
`.env` guarda só segredo, e não vai para o Git.
"""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / '.env')


class Config:
    """Acesso aos parâmetros do pipeline.

    Caminhos vêm resolvidos em absoluto a partir da raiz do repositório,
    para o pipeline rodar igual de qualquer diretório.
    """

    def __init__(self, caminho: Path | str | None = None):
        self.caminho = Path(caminho or RAIZ / 'config.yaml')
        if not self.caminho.exists():
            raise FileNotFoundError(
                f'config não encontrado: {self.caminho}\n'
                f'Esperado na raiz do repositório, junto do README.')
        self.dados = yaml.safe_load(self.caminho.read_text(encoding='utf-8'))

        self.schema = self.dados['banco']['schema']
        self.modelo = self.dados['vetorial']['modelo']
        self.dimensoes = self.dados['vetorial']['dimensoes']

    # ── caminhos ──────────────────────────────────────────────
    def fonte(self, nome: str) -> Path:
        """Caminho absoluto de uma das 3 fontes."""
        return RAIZ / self.dados['fontes'][nome]

    @property
    def fontes(self) -> dict[str, Path]:
        return {nome: RAIZ / rel for nome, rel in self.dados['fontes'].items()}

    @property
    def processados(self) -> Path:
        p = RAIZ / self.dados['saida']['processados']
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def artefatos(self) -> Path:
        p = RAIZ / self.dados['saida']['artefatos']
        p.mkdir(parents=True, exist_ok=True)
        return p

    # ── seções ────────────────────────────────────────────────
    @property
    def recomendacao(self) -> dict:
        return self.dados['recomendacao']

    @property
    def vetorial(self) -> dict:
        return self.dados['vetorial']

    @property
    def painel(self) -> dict:
        return self.dados['dashboard']

    @property
    def colecao_mongo(self) -> str:
        return self.dados['mongo']['colecao']

    def tabela(self, nome: str) -> str:
        """Nome qualificado pelo schema, como o SQL precisa receber."""
        return f'{self.schema}.{nome}'

    # ── segredos (nunca impressos) ────────────────────────────
    @staticmethod
    def segredo(chave: str, padrao: str | None = None) -> str | None:
        return os.getenv(chave, padrao)

    def conferir_segredos(self) -> list[str]:
        """Devolve a lista de variáveis obrigatórias que faltam no .env."""
        return [c for c in ('DB_HOST', 'DB_NAME', 'DB_USER', 'DB_PASSWORD')
                if not os.getenv(c)]
