from django.db import migrations, models


def normalizar(apps, schema_editor):
    """RETROCOMPAT MOVIL v1.6.4 - ver contenedor/contrato_movil.py.

    Antes de la migracion 0009, UsuarioContenedor no tenia los campos
    tiene_acceso_movil ni perfil_movil, asi que los conductores invitados
    pre-existentes quedaron con tiene_acceso_movil=False (default viejo).
    Si en el futuro se aplica RolMixin a viewsets que la app movil consume,
    estos usuarios quedarian bloqueados.

    Este RunPython los habilita por default como conductores. Excluye
    perfil_web='consulta' (auditores que solo deben leer en web).
    """
    UsuarioContenedor = apps.get_model('contenedor', 'UsuarioContenedor')
    UsuarioContenedor.objects.filter(perfil_movil__isnull=True) \
        .exclude(perfil_web='consulta') \
        .update(tiene_acceso_movil=True, perfil_movil='conductor')


class Migration(migrations.Migration):

    dependencies = [
        ('contenedor', '0009_usuariocontenedor_perfil_movil_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='usuariocontenedor',
            name='tiene_acceso_movil',
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(normalizar, migrations.RunPython.noop),
    ]
