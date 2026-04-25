from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("loja", "0006_merge_20260415_1647"),
    ]

    operations = [
        migrations.AddField(
            model_name="produto",
            name="visualizacoes",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
