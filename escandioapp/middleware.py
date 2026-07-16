"""Observabilidad — middleware de Sentry.

Etiqueta cada evento de Sentry con el `tenant` (schema) del request. En un
backend multi-tenant es la pieza clave para saber A QUIEN le paso el error sin
tener que adivinar. Es no-op si Sentry no esta inicializado (sin SENTRY_DSN),
asi que es seguro tenerlo siempre en MIDDLEWARE.

Debe ir DESPUES de django_tenants TenantMainMiddleware (que setea request.tenant).
"""
try:
    import sentry_sdk
except ImportError:
    # Defensivo: si sentry-sdk no esta instalado en el server, el middleware
    # queda como no-op y el backend arranca igual.
    sentry_sdk = None


class SentryTenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if sentry_sdk is not None:
            tenant = getattr(request, 'tenant', None)
            schema = getattr(tenant, 'schema_name', None) if tenant is not None else None
            if schema:
                sentry_sdk.set_tag('tenant', schema)
        return self.get_response(request)
