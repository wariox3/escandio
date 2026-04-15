from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('general', '0007_agregar_estrategia_ruteo'),
    ]

    operations = [
        migrations.AddField(
            model_name='genconfiguracion',
            name='rut_alerta_parada_activa',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='genconfiguracion',
            name='rut_alerta_parada_minutos',
            field=models.IntegerField(default=15),
        ),
        migrations.AddField(
            model_name='genconfiguracion',
            name='rut_alerta_parada_radio_metros',
            field=models.IntegerField(default=80),
        ),
        migrations.AddField(
            model_name='genconfiguracion',
            name='rut_alerta_geocerca_activa',
            field=models.BooleanField(default=False),
        ),
    ]
