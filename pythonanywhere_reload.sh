#!/bin/bash
set -e

cd "$(dirname "$0")"
source .venv/bin/activate

python manage.py migrate
python manage.py collectstatic --noinput

echo "Atualizacao concluida. Agora clique em Reload no painel Web do PythonAnywhere."
