from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('ruteo', '0008_crear_notificacion'),
    ]

    operations = [
        migrations.CreateModel(
            name='RutAlerta',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha', models.DateTimeField(auto_now_add=True)),
                ('tipo', models.CharField(choices=[('parada_prolongada', 'Parada prolongada'), ('fuera_geocerca', 'Fuera de geocerca')], max_length=30)),
                ('mensaje', models.CharField(blank=True, max_length=255, null=True)),
                ('usuario_id', models.IntegerField(null=True)),
                ('latitud', models.DecimalField(decimal_places=15, max_digits=25, null=True)),
                ('longitud', models.DecimalField(decimal_places=15, max_digits=25, null=True)),
                ('duracion_minutos', models.IntegerField(null=True)),
                ('leida', models.BooleanField(default=False)),
                ('fecha_leida', models.DateTimeField(null=True)),
                ('despacho', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='alertas_despacho_rel', to='ruteo.rutdespacho')),
                ('visita', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='alertas_visita_rel', to='ruteo.rutvisita')),
            ],
            options={
                'db_table': 'rut_alerta',
                'ordering': ['-id'],
            },
        ),
    ]
