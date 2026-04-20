from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('general', '0009_agregar_rut_limite_complemento'),
    ]

    operations = [
        migrations.AddField(
            model_name='genconfiguracion',
            name='rut_limite_importacion',
            field=models.IntegerField(default=500),
        ),
        migrations.AddField(
            model_name='genconfiguracion',
            name='rut_alertas_intervalo_segundos',
            field=models.IntegerField(default=30),
        ),
    ]
