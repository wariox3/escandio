from django.db import migrations


def _complemento_segun_perfil(perfil_web):
    # 'complemento' es modulo administrativo: solo supervisor lo tiene
    # habilitado por plantilla. Operativo / consulta / sin perfil no.
    if perfil_web == 'supervisor':
        return {'ver': True, 'editar': True}
    return {'ver': False, 'editar': False}


def agregar_complemento(apps, schema_editor):
    UsuarioContenedor = apps.get_model('contenedor', 'UsuarioContenedor')
    qs = UsuarioContenedor.objects.exclude(permisos__isnull=True)
    for uc in qs.iterator():
        permisos = uc.permisos
        if not isinstance(permisos, dict) or 'complemento' in permisos:
            continue
        permisos['complemento'] = _complemento_segun_perfil(uc.perfil_web)
        uc.permisos = permisos
        uc.save(update_fields=['permisos'])


def quitar_complemento(apps, schema_editor):
    UsuarioContenedor = apps.get_model('contenedor', 'UsuarioContenedor')
    qs = UsuarioContenedor.objects.exclude(permisos__isnull=True)
    for uc in qs.iterator():
        permisos = uc.permisos
        if not isinstance(permisos, dict) or 'complemento' not in permisos:
            continue
        permisos.pop('complemento', None)
        uc.permisos = permisos
        uc.save(update_fields=['permisos'])


class Migration(migrations.Migration):

    dependencies = [
        ('contenedor', '0013_user_estado_registro'),
    ]

    operations = [
        migrations.RunPython(agregar_complemento, quitar_complemento),
    ]
