"""
CONTRATO API MOVIL v2 (/api/v2/).

La API v2 es la superficie que consumira la NUEVA version de la app movil
berkelio. Es aditiva: vive en paralelo al legacy v1.6.4 (ver
contenedor/contrato_movil.py) y no lo reemplaza hasta que v1.6.4 quede sin uso.

El contrato formal y versionado es el schema OpenAPI en movil/openapi_v2.yaml.
La suite movil/tests/test_contrato_v2.py lo blinda: si el schema cambia, el
snapshot test falla. Antes de tocar una view o serializer de la app `movil`:

    python manage.py test movil
    python manage.py spectacular --file movil/openapi_v2.yaml   # si el cambio es intencional

Endpoints — ver paths y shapes exactos en openapi_v2.yaml:

  Dominio base (la app aun no conoce el tenant):
    GET  /api/v2/app/config/             -> {version_minima, actualizacion_requerida, ...}
    POST /api/v2/auth/login/             -> {access, refresh, usuario}
    POST /api/v2/auth/registro/          -> 201 {usuario}
    POST /api/v2/auth/token/refresh/     -> {access, refresh}
    POST /api/v2/auth/logout/            -> 200 {mensaje}
    GET  /api/v2/auth/me/                -> usuario autenticado (estado, acceso_movil)
    POST /api/v2/auth/clave/solicitar/   -> 200 {mensaje}
    GET  /api/v2/despachos/<id>/         -> {schema_name, despacho_id, ...}

  Subdominio del tenant ({schema}.ruteoapi.co):
    GET  /api/v2/visitas/                -> lista (sin paginar)
    POST /api/v2/visitas/<id>/entregar/  -> 200 {mensaje}   (multipart)
    GET  /api/v2/novedades/tipos/        -> lista
    POST /api/v2/novedades/              -> 201 {id}        (multipart)
    POST /api/v2/novedades/<id>/solucionar/ -> 200 {mensaje}
    POST /api/v2/ubicacion/              -> 201 {ubicacion}

REGLAS DEL CONTRATO v2:
  1. Tokens estandar: el login devuelve {access, refresh} (sin la clave
     'refresh-token' con guion que usaba el legacy).
  2. Envelope de error unico {codigo, titulo, mensaje}; ver movil/responses.py
     y movil/exceptions.py. `codigo` es estable (constantes COD_*).
  3. Permisos: los endpoints de tenant exigen EsConductorMovil (autenticado +
     acceso movil al contenedor). auth/* y despachos/<id>/ corren en el dominio
     base con AllowAny / IsAuthenticated.
  4. El schema solo cubre /api/v2/ (hook movil.spectacular.solo_endpoints_v2).
  5. Cualquier cambio breaking para la app v2 publicada debe ser una v3, no una
     mutacion de v2 — igual que el legacy.
  6. La app envia el header `X-App-Version`; el backend lo registra en cada
     login (movil.middleware.VersionAppMiddleware) para medir adopcion y
     decidir el sunset del legacy v1.6.4.
"""

ENDPOINTS_MOVIL_V2 = (
    'GET /api/v2/app/config/',
    'POST /api/v2/auth/login/',
    'POST /api/v2/auth/registro/',
    'POST /api/v2/auth/token/refresh/',
    'POST /api/v2/auth/logout/',
    'GET /api/v2/auth/me/',
    'POST /api/v2/auth/clave/solicitar/',
    'GET /api/v2/despachos/<id>/',
    'GET /api/v2/visitas/',
    'POST /api/v2/visitas/<id>/entregar/',
    'GET /api/v2/novedades/tipos/',
    'POST /api/v2/novedades/',
    'POST /api/v2/novedades/<id>/solucionar/',
    'POST /api/v2/ubicacion/',
)
