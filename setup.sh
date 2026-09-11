#!/usr/bin/env bash
# ============================================================
# setup.sh — prepara o ambiente numa máquina nova
#   bash setup.sh
#
# Não instala serviço nenhum com sudo: apenas cria o venv, instala
# as dependências Python e confere o que está faltando.
# ============================================================
set -euo pipefail

cd "$(dirname "$0")"

echo '==> Python'
python3 --version

echo '==> Ambiente virtual'
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip

echo '==> Dependências'
# O torch vem do índice CPU: a build padrão do PyPI arrasta ~3 GB de
# bibliotecas CUDA, inúteis em máquina sem GPU.
.venv/bin/pip install -q --index-url https://download.pytorch.org/whl/cpu \
    "torch==2.13.0+cpu"
.venv/bin/pip install -q -r requirements.txt

echo '==> Configuração'
if [ ! -f .env ]; then
    cp .env.example .env
    chmod 600 .env
    echo '    .env criado a partir do exemplo — PREENCHA DB_PASSWORD'
else
    echo '    .env já existe'
fi

echo
echo '==> Serviços necessários'
verificar() {
    printf '    %-28s ' "$1"
    if eval "$2" >/dev/null 2>&1; then echo 'OK'; else echo "FALTA — $3"; fi
}
verificar 'PostgreSQL (5432)' \
    "bash -c '</dev/tcp/localhost/5432'" \
    'sudo apt install postgresql postgresql-contrib'
verificar 'pgvector' \
    "ls /usr/lib/postgresql/*/lib/vector.so" \
    'sudo apt install postgresql-18-pgvector'
verificar 'MongoDB (27017)' \
    "bash -c '</dev/tcp/localhost/27017'" \
    'opcional — veja o README'
verificar 'Superset (8088)' \
    "curl -sf --max-time 5 http://localhost:8088/health" \
    'opcional — veja o README'

echo
echo 'Pronto. Ative o ambiente e rode o pipeline de referência:'
echo '    source .venv/bin/activate'
echo '    python exemplo_pipeline.py'
