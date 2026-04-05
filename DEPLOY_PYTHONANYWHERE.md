# Deploy no PythonAnywhere

## Primeiro deploy (mais rapido)

No Bash Console do PythonAnywhere:

```bash
cd ~
git clone https://github.com/Elloy123/BelaCheirosa.git belacheirosa_web
cd belacheirosa_web
bash pythonanywhere_first_deploy.sh
```

Depois edite o arquivo `.env`:

```bash
nano ~/belacheirosa_web/.env
```

Exemplo:

```env
DJANGO_SECRET_KEY=troque-por-uma-chave-segura
DEBUG=False
ALLOWED_HOSTS=Elloy123.pythonanywhere.com
CSRF_TRUSTED_ORIGINS=https://Elloy123.pythonanywhere.com
LOJA_WHATSAPP=5593991512300
```

## Configuracao no painel Web do PythonAnywhere

1. Crie o Web App (Manual, Python 3.11).
2. Configure Virtualenv:
   - `/home/<usuario>/belacheirosa_web/.venv`
3. Configure WSGI file:
   - `/home/<usuario>/belacheirosa_web/pythonanywhere_wsgi.py`
4. Configure static:
   - URL: `/static/`
   - Dir: `/home/<usuario>/belacheirosa_web/staticfiles`
5. Configure media:
   - URL: `/media/`
   - Dir: `/home/<usuario>/belacheirosa_web/media`
6. Clique em Reload.

## Atualizacoes futuras

Quando fizer push novo no GitHub:

```bash
cd ~/belacheirosa_web
git pull
bash pythonanywhere_reload.sh
```

Depois clique em Reload no painel Web.
