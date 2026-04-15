# Bela Cheirosa - Loja Django

Sistema comercial com:
- Catalogo online
- Carrinho e checkout via WhatsApp
- Painel comercial (vendas, pedidos, estoque, clientes)
- Fiado e boletos com parcelas e data real de pagamento

## Deploy rapido no PythonAnywhere

### 1) No PythonAnywhere (Bash)

```bash
cd ~
git clone https://github.com/Elloy123/BelaCheirosa.git belacheirosa_web
cd belacheirosa_web
bash pythonanywhere_first_deploy.sh
```

### 2) Edite o arquivo .env

```bash
nano ~/belacheirosa_web/.env
```

Valores minimos:

```env
DJANGO_SECRET_KEY=troque-por-uma-chave-segura
DEBUG=False
ALLOWED_HOSTS=Elloy123.pythonanywhere.com
CSRF_TRUSTED_ORIGINS=https://Elloy123.pythonanywhere.com
LOJA_WHATSAPP=5593991512300
```

### 3) Configure o Web App (painel PythonAnywhere)
- Virtualenv: /home/<usuario>/belacheirosa_web/.venv
- WSGI file: /home/<usuario>/belacheirosa_web/pythonanywhere_wsgi.py
- Static mapping: /static/ -> /home/<usuario>/belacheirosa_web/staticfiles
- Media mapping: /media/ -> /home/<usuario>/belacheirosa_web/media

### 4) Clique em Reload

## Atualizacao de codigo

Sempre que fizer push novo no GitHub, no PythonAnywhere rode:

```bash
cd ~/belacheirosa_web
git pull
bash pythonanywhere_reload.sh
```

Depois clique em Reload no painel Web.
