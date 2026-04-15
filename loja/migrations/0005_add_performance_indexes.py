from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("loja", "0004_alter_contapagar_options_contapagar_data_pagamento_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="contapagar",
            name="data_pagamento",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name="contapagar",
            name="grupo_referencia",
            field=models.CharField(blank=True, db_index=True, default="", max_length=40),
        ),
        migrations.AlterField(
            model_name="contapagar",
            name="status",
            field=models.CharField(
                choices=[("pendente", "Pendente"), ("pago", "Pago"), ("parcial", "Parcial")],
                db_index=True,
                default="pendente",
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="contapagar",
            name="vencimento",
            field=models.DateField(db_index=True),
        ),
        migrations.AlterField(
            model_name="fiadoconta",
            name="status",
            field=models.CharField(
                choices=[("pendente", "Pendente"), ("pago", "Pago"), ("parcial", "Parcial")],
                db_index=True,
                default="pendente",
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="fiadoconta",
            name="vencimento",
            field=models.DateField(db_index=True),
        ),
        migrations.AlterField(
            model_name="pedido",
            name="status",
            field=models.CharField(
                choices=[("pendente", "Pendente"), ("concluido", "Concluído"), ("cancelado", "Cancelado")],
                db_index=True,
                default="pendente",
                max_length=15,
            ),
        ),
        migrations.AlterField(
            model_name="produto",
            name="ativo",
            field=models.BooleanField(db_index=True, default=True),
        ),
        migrations.AlterField(
            model_name="produto",
            name="codigo",
            field=models.CharField(blank=True, db_index=True, default="", max_length=60),
        ),
        migrations.AlterField(
            model_name="produto",
            name="nome",
            field=models.CharField(db_index=True, max_length=200),
        ),
        migrations.AlterField(
            model_name="venda",
            name="data",
            field=models.DateTimeField(db_index=True, default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name="venda",
            name="forma_pagamento",
            field=models.CharField(
                choices=[
                    ("dinheiro", "Dinheiro"),
                    ("pix", "PIX"),
                    ("cartao_debito", "Cartão Débito"),
                    ("cartao_credito", "Cartão Crédito"),
                    ("fiado", "Fiado"),
                ],
                db_index=True,
                default="dinheiro",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="venda",
            name="status",
            field=models.CharField(
                choices=[("concluida", "Concluída"), ("pendente", "Pendente"), ("cancelada", "Cancelada")],
                db_index=True,
                default="concluida",
                max_length=15,
            ),
        ),
    ]
