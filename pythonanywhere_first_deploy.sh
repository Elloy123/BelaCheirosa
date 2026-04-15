#!/bin/bash
set -e

APP_DIR="$HOME/belacheirosa_web"

if [ ! -d "$APP_DIR" ]; then
  echo "Erro: pasta $APP_DIR nao encontrada. Clone o repositorio antes."
  exit 1
fi

cd "$APP_DIR"

if [ ! -d ".venv" ]; then
  python3.11 -m venv .venv
fi

source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f ".env" ] && [ -f ".env.pythonanywhere.example" ]; then
  cp .env.pythonanywhere.example .env
  echo "Arquivo .env criado com base no exemplo. Edite antes de continuar em producao."
fi

python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check

echo "Primeiro deploy preparado."
echo "Agora configure no painel Web do PythonAnywhere:"
echo "- Virtualenv: /home/<usuario>/belacheirosa_web/.venv"
echo "- WSGI file: /home/<usuario>/belacheirosa_web/pythonanywhere_wsgi.py"
echo "- Static: /static/ -> /home/<usuario>/belacheirosa_web/staticfiles"
echo "- Media: /media/ -> /home/<usuario>/belacheirosa_web/media"
echo "Depois clique em Reload."
