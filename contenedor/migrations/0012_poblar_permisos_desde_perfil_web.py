from django.db import migrations


MODULOS = (
    'visita',
    'vehiculo',
    'despacho',
    'franja',
    'flota',
    'novedad',
    'contacto',
    'empresa',
    'configuracion',
    'mensajeria',
    'facturacion',
    'usuario',
)


def _plantilla(perfil_web):
    if perfil_web == 'consulta':
        editar = False
    else:
        editar = True
    return {modulo: {'ver': True, 'editar': editar} for modulo in MODULOS}


def poblar(apps, schema_editor):
    """Genera UsuarioContenedor.permisos a partir de perfil_web existente.

    Idempotente: solo escribe si permisos esta vacio. Mantiene perfil_web
    en la columna como legacy hasta que se deprecie por completo.
    """
    UsuarioContenedor = apps.get_model('contenedor', 'UsuarioContenedor')
    for uc in UsuarioContenedor.objects.filter(permisos__isnull=True):
        uc.permisos = _plantilla(uc.perfil_web or 'operativo')
        uc.save(update_fields=['permisos'])


class Migration(migrations.Migration):

    dependencies = [
        ('contenedor', '0011_admin_usuarios_y_permisos'),
    ]

    operations = [
        migrations.RunPython(poblar, migrations.RunPython.noop),
    ]
