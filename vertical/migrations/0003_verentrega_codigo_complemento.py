from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vertical', '0002_crear_entrega_detalle'),
    ]

    operations = [
        migrations.AddField(
            model_name='verentrega',
            name='codigo_complemento',
            field=models.IntegerField(null=True),
        ),
    ]
