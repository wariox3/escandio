from django.core.management.base import BaseCommand
from django.apps import apps
from django_tenants.utils import schema_context
from django.db import connection
import json
import os


class Command(BaseCommand):
    help = 'Descripción de tu comando aquí'

    def add_arguments(self, parser):
        parser.add_argument('json_file', type=str, help='Ruta del archivo JSON')

    def handle(self, *args, request=None,  **options):            
        prueba1 = connection.schema_name
        prueba2 = schema_context
        self.stdout.write(self.style.WARNING(prueba2))
        #tenant = get_tenant()
        #tenant = get_tenant(request=request)
        #self.stdout.write(self.style.WARNING(str(request)))
        #tenant_model = get_tenant_model()    
        #current_tenant_schema_name = tenant_model.objects.get(pk=tenant_model._default_manager.get_current_tenant().pk).schema_name
        
        
        #self.stdout.write(self.style.WARNING(tenant_model))
        #current_tenant = tenant_model.objects.get_current()
        #self.stdout.write(f"Este comando se está ejecutando en el tenant '{current_tenant.schema_name}'")

        '''TenantModel = get_tenant_model()
        tenants = TenantModel.objects.all()
        for tenant in tenants:
            self.stdout.write(self.style.SUCCESS(f'Ejecutando comando sobre el tenant: {tenant.schema_name}'))            
        '''
        self.stdout.write(self.style.WARNING('Hola mundo'))