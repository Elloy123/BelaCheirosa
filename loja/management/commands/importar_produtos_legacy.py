import sqlite3
from pathlib import Path
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from loja.models import Categoria, Produto


class Command(BaseCommand):
    help = "Importa produtos do banco legado loja_bela_cheirosa.db"

    def add_arguments(self, parser):
        parser.add_argument(
            "--db-path",
            type=str,
            default=str(Path(__file__).resolve().parents[4] / "loja_bela_cheirosa.db"),
            help="Caminho do banco legado SQLite",
        )

    def handle(self, *args, **options):
        db_path = Path(options["db_path"])
        if not db_path.exists():
            self.stdout.write(self.style.ERROR(f"Banco legado não encontrado: {db_path}"))
            return

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT codigo, produto, categoria, observacao, preco_venda, custo_unitario,
                   quantidade_inicial, estoque_minimo
            FROM produtos
            """
        ).fetchall()

        created = 0
        updated = 0
        for row in rows:
            nome = (row["produto"] or "").strip()
            if not nome:
                continue
            cat_nome = (row["categoria"] or "Outros").strip() or "Outros"
            cat_slug = slugify(cat_nome) or "outros"
            categoria = Categoria.objects.filter(nome=cat_nome[:120]).first()
            if not categoria:
                categoria = Categoria.objects.filter(slug=cat_slug).first()
            if not categoria:
                categoria = Categoria.objects.create(
                    nome=cat_nome[:120],
                    slug=cat_slug,
                )

            base_slug = slugify(nome) or "produto"
            slug = base_slug
            i = 2
            while Produto.objects.exclude(codigo=row["codigo"] or "").filter(slug=slug).exists():
                slug = f"{base_slug}-{i}"
                i += 1

            defaults = {
                "categoria": categoria,
                "nome": nome[:200],
                "slug": slug,
                "descricao": (row["observacao"] or "")[:2000],
                "preco": float(row["preco_venda"] or 0),
                "custo": float(row["custo_unitario"] or 0),
                "estoque": int(row["quantidade_inicial"] or 0),
                "estoque_minimo": int(row["estoque_minimo"] or 5),
                "ativo": True,
            }

            obj, was_created = Produto.objects.update_or_create(
                codigo=(row["codigo"] or "").strip(),
                defaults=defaults,
            )
            if was_created:
                created += 1
            else:
                updated += 1

        conn.close()
        self.stdout.write(self.style.SUCCESS(f"Importação concluída. Criados: {created}, Atualizados: {updated}"))
