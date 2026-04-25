from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("loja", "0007_produto_visualizacoes"),
    ]

    operations = [
        migrations.AddField(
            model_name="fiadoconta",
            name="grupo_referencia",
            field=models.CharField(blank=True, db_index=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="fiadoconta",
            name="parcela_numero",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="fiadoconta",
            name="parcelas_total",
            field=models.PositiveIntegerField(default=1),
        ),
    ]
