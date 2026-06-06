from django.db import migrations


def agregar_reporte(apps, schema_editor):
    UsuarioContenedor = apps.get_model('contenedor', 'UsuarioContenedor')
    qs = UsuarioContenedor.objects.exclude(permisos__isnull=True)
    for uc in qs.iterator():
        permisos = uc.permisos
        if not isinstance(permisos, dict) or 'reporte' in permisos:
            continue
        despacho = permisos.get('despacho') or {'ver': False, 'editar': False}
        permisos['reporte'] = {
            'ver': bool(despacho.get('ver')),
            'editar': bool(despacho.get('editar')),
        }
        uc.permisos = permisos
        uc.save(update_fields=['permisos'])


def quitar_reporte(apps, schema_editor):
    UsuarioContenedor = apps.get_model('contenedor', 'UsuarioContenedor')
    qs = UsuarioContenedor.objects.exclude(permisos__isnull=True)
    for uc in qs.iterator():
        permisos = uc.permisos
        if not isinstance(permisos, dict) or 'reporte' not in permisos:
            continue
        permisos.pop('reporte', None)
        uc.permisos = permisos
        uc.save(update_fields=['permisos'])


class Migration(migrations.Migration):

    dependencies = [
        ('contenedor', '0014_agregar_complemento_a_permisos'),
    ]

    operations = [
        migrations.RunPython(agregar_reporte, quitar_reporte),
    ]
