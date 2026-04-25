from django.db import migrations, models


class Migration(migrations.Migration):

	dependencies = [
		("loja", "0008_fiadoconta_parcelamento"),
	]

	operations = [
		migrations.AddField(
			model_name="fiadoconta",
			name="data_pagamento",
			field=models.DateField(blank=True, db_index=True, null=True),
		),
	]