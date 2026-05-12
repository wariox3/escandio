from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contenedor', '0010_normalizar_acceso_movil_existentes'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='debe_cambiar_clave',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='usuariocontenedor',
            name='permisos',
            field=models.JSONField(blank=True, null=True),
        ),
    ]
