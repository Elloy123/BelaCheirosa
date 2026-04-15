"""Comando para fazer backup do banco de dados SQLite."""

import sqlite3
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
	help = "Gera um arquivo de backup SQL do banco de dados SQLite."

	def add_arguments(self, parser):
		parser.add_argument(
			"--output",
			type=str,
			default=None,
			help="Caminho do arquivo de saída (padrão: backup_belacheirosa_YYYYMMDD_HHMMSS.sql na pasta raiz do projeto).",
		)

	def handle(self, *args, **options):
		db_path = settings.DATABASES["default"]["NAME"]
		if not Path(str(db_path)).exists():
			self.stderr.write(self.style.ERROR(f"Banco de dados não encontrado: {db_path}"))
			return

		output_path = options["output"]
		if not output_path:
			ts = datetime.now().strftime("%Y%m%d_%H%M%S")
			output_path = Path(settings.BASE_DIR) / f"backup_belacheirosa_{ts}.sql"

		output_path = Path(output_path)

		conn = sqlite3.connect(str(db_path))
		try:
			with output_path.open("w", encoding="utf-8") as f:
				for linha in conn.iterdump():
					f.write(linha + "\n")
		finally:
			conn.close()

		self.stdout.write(self.style.SUCCESS(f"Backup gerado em: {output_path}"))
