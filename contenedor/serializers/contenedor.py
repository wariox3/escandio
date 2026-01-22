from rest_framework import serializers
from contenedor.models import Contenedor
from decouple import config
from datetime import datetime

class ContenedorSerializador(serializers.ModelSerializer):
    class Meta:
        model = Contenedor
        fields = ['id', 'schema_name', 'plan']
    
    def to_representation(self, instance):
        region = config('DO_REGION')
        bucket = config('DO_BUCKET')
        plan = instance.plan
        plan_usuarios_base = None
        plan_limite_usuarios = None
        plan_nombre = None
        plan_venta = False
        plan_compra = False
        plan_cartera = False
        plan_tesoreria = False
        plan_inventario = False
        plan_humano = False
        plan_contabilidad = False
        if plan:
            plan_usuarios_base = plan.usuarios_base
            plan_limite_usuarios = plan.limite_usuarios
            plan_nombre = plan.nombre
            plan_venta = plan.venta
            plan_compra = plan.compra
            plan_cartera = plan.cartera
            plan_tesoreria = plan.tesoreria
            plan_inventario = plan.inventario
            plan_humano = plan.humano
            plan_contabilidad = plan.contabilidad            
        acceso_restringido = False
        if instance.usuario:
            usuario = instance.usuario
            if usuario.vr_saldo > 0 and datetime.now().date() > usuario.fecha_limite_pago:
                acceso_restringido = True
        return {
            'id': instance.id,            
            'subdominio': instance.schema_name,
            'nombre': instance.nombre,
            'plan_id': instance.plan_id,
            'plan_usuarios_base': plan_usuarios_base,
            'plan_limite_usuarios': plan_limite_usuarios,
            'plan_nombre':  plan_nombre,
            'plan_venta': plan_venta,
            'plan_compra': plan_compra,
            'plan_tesoreria': plan_tesoreria,
            'plan_cartera': plan_cartera,
            'plan_inventario': plan_inventario,
            'plan_humano': plan_humano,
            'plan_contabilidad': plan_contabilidad,
            'imagen': f"https://{bucket}.{region}.digitaloceanspaces.com/{instance.imagen}",
            'reddoc': instance.reddoc,
            'ruteo': instance.ruteo,
            'cortesia': instance.cortesia,
            'usuario_id': instance.usuario_id,
            'usuarios': instance.usuarios,
            'fecha': instance.fecha,
            'acceso_restringido': acceso_restringido
        } 
    
class ContenedorActualizarSerializador(serializers.HyperlinkedModelSerializer):    
    class Meta:
        model = Contenedor
        fields = ['nombre']         


class ContenedorUsuarioSerializador(serializers.ModelSerializer):    
    class Meta:
        model = Contenedor
        fields = ['id', 'schema_name']

    def to_representation(self, instance):
        plan = instance.plan
        planNombre = None
        usuariosBase = None
        if plan:
            planNombre = plan.nombre
            usuariosBase = plan.usuarios_base
        acceso_restringido = False
        if instance.usuario:
            usuario = instance.usuario
            if usuario.vr_saldo > 0 and datetime.now().date() > usuario.fecha_limite_pago:
                acceso_restringido = True  
        return {
            'id': instance.id,
            'usuario_id': instance.usuario_id,
            'contenedor_id': instance.id,
            'rol': "Administrador",
            'subdominio': instance.schema_name,
            'nombre': instance.nombre,
            'imagen': f"https://{config('DO_BUCKET')}.{config('DO_REGION')}.digitaloceanspaces.com/{instance.imagen}",
            'usuarios': instance.usuarios,
            'usuarios_base': usuariosBase,
            'plan_id': instance.plan_id,
            'plan_nombre': planNombre,
            'reddoc': instance.reddoc,
            'ruteo': instance.ruteo,
            'acceso_restringido': acceso_restringido
        }
