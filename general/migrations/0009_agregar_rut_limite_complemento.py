from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('general', '0008_agregar_config_alertas'),
    ]

    operations = [
        migrations.AddField(
            model_name='genconfiguracion',
            name='rut_limite_complemento',
            field=models.IntegerField(default=1000),
        ),
    ]
