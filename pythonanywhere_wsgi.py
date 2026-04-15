"""WSGI entrypoint for PythonAnywhere.

Use this file path in the PythonAnywhere Web tab:
/home/<seu_usuario>/.../belacheirosa_web/pythonanywhere_wsgi.py
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
    except Exception:
        pass

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "belacheirosa_web.settings")

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
