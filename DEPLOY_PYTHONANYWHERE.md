# Deploy no PythonAnywhere

## 1) Enviar o projeto para o servidor
No Bash Console do PythonAnywhere:

```bash
cd ~
git clone <url-do-seu-repositorio> belacheirosa_web
cd belacheirosa_web
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 2) Configurar variaveis de ambiente
Crie um arquivo `.env` (ou use variaveis no WSGI) com base em `.env.pythonanywhere.example`.

Exemplo minimo:

```env
DJANGO_SECRET_KEY=sua-chave-segura
DEBUG=False
ALLOWED_HOSTS=seuusuario.pythonanywhere.com
CSRF_TRUSTED_ORIGINS=https://seuusuario.pythonanywhere.com
LOJA_WHATSAPP=5593991512300
```

## 3) Migrar banco e coletar arquivos estaticos
Ainda no Bash:

```bash
cd ~/belacheirosa_web
source .venv/bin/activate
python manage.py migrate
python manage.py collectstatic --noinput
```

## 4) Configurar Web App no painel do PythonAnywhere
1. Crie um novo Web App (Manual configuration, Python 3.11).
2. Virtualenv:
   - `/home/<seu_usuario>/belacheirosa_web/.venv`
3. WSGI file:
   - aponte para: `/home/<seu_usuario>/belacheirosa_web/pythonanywhere_wsgi.py`
4. Static files:
   - URL: `/static/`
   - Directory: `/home/<seu_usuario>/belacheirosa_web/staticfiles`
5. Media files:
   - URL: `/media/`
   - Directory: `/home/<seu_usuario>/belacheirosa_web/media`

## 5) Carregar variaveis no WSGI (se usar arquivo .env)
No arquivo WSGI, acima da linha `application = ...`, carregue as variaveis:

```python
from dotenv import load_dotenv
load_dotenv('/home/<seu_usuario>/belacheirosa_web/.env')
```

Se usar esse trecho, instale:

```bash
pip install python-dotenv
```

## 6) Reiniciar app
No painel Web do PythonAnywhere, clique em **Reload**.

## 7) Verificacao rapida
- Abra o dominio `.pythonanywhere.com`.
- Acesse `/admin/`.
- Teste a pagina inicial e os CSS.

## Observacoes
- Para facilitar atualizacoes, use Git + `git pull` no servidor.
- Depois de atualizar codigo: rode `migrate`, `collectstatic` e clique em **Reload**.
