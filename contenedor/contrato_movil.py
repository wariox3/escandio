"""
CONTRATO MOVIL v1.6.4 (versionCode 58 Android) - APP NO TOCABLE.

La app movil React Native publicada en stores consume los endpoints listados
abajo. Cualquier cambio que altere su path, payload o response shape rompe a
TODOS los usuarios de la app v1.6.4 publicada. Hasta que la app sea retirada
o forzada a actualizar, este modulo es ley.

Antes de modificar cualquiera de las views referenciadas, leer este archivo
y correr `python manage.py test contenedor.tests_contrato_movil`.

Endpoints obligatorios:

  POST /seguridad/login/
       in:  {username, password, proyecto: 'RUTEOAPP'}
       out: 200 {token, 'refresh-token', user}
       cls: contenedor.views.seguridad.Login (AllowAny)
       OJO: la clave del response es 'refresh-token' (con guion), NO 'refresh_token'.
       OJO: la whitelist de proyecto debe seguir incluyendo 'RUTEOAPP'.

  POST /contenedor/usuario/nuevo/
       in:  {username, password, confirmarPassword, aceptarTerminosCondiciones, aplicacion}
       out: 201 {usuario}
       cls: contenedor.views.usuario.UsuarioViewSet.nuevo_action (sin RolMixin)
       OJO: la app envia 'aplicacion':'ruteo' (minusculas) y campos extras
            (confirmarPassword, aceptarTerminosCondiciones) que el backend ignora.
            El UserSerializer NO debe marcar 'aplicacion' como required.

  POST /seguridad/token/refresh/
       in:  {refresh}
       out: 200 {access}
       cls: rest_framework_simplejwt.views.TokenRefreshView

  POST /contenedor/usuario/cambio-clave-solicitar/
       in:  {username, aplicacion}
       out: 201 {verificacion}
       cls: contenedor.views.usuario.UsuarioViewSet.cambio_clave_solicitar

  GET  /vertical/entrega/{codigo}/
       out: 200 {schema_name, despacho_id, ...}
       cls: vertical.views.entrega.EntregaViewSet (IsAuthenticated)

  GET  https://{schema}.ruteoapi.co/ruteo/visita/?despacho_id=...&estado_entregado=...
       cls: ruteo.views.visita.RutVisitaViewSet (acciones_publicas debe contener 'list')

  POST https://{schema}.ruteoapi.co/ruteo/visita/entrega/
       cls: ruteo.views.visita.RutVisitaViewSet.entrega_action
       (debe permanecer en acciones_publicas)

  GET  https://{schema}.ruteoapi.co/ruteo/novedad_tipo/
       cls: ruteo.views.novedad_tipo.RutNovedadTipoViewSet (IsAuthenticated)

  POST https://{schema}.ruteoapi.co/ruteo/novedad/nuevo/  (multipart/form-data)
       cls: ruteo.views.novedad.RutNovedadViewSet.nuevo_action

  POST https://{schema}.ruteoapi.co/ruteo/novedad/solucionar/
       cls: ruteo.views.novedad.RutNovedadViewSet.solucionar

REGLAS:
  1. Para entrar a list/retrieve/entrega de RutVisitaViewSet basta con IsAuthenticated.
     OJO: en `acciones_publicas` van los NOMBRES DE METODO, no los url_path.
     Para RutVisitaViewSet: 'list', 'retrieve', 'entrega_action'.
  2. Si se aplica RolMixin a RutNovedadViewSet, RutNovedadTipoViewSet o EntregaViewSet,
     se DEBE incluir las acciones equivalentes en acciones_publicas usando los nombres
     de metodo: 'list', 'retrieve', 'create', 'nuevo_action', 'solucionar' (este si
     coincide porque el metodo se llama solucionar) hasta que v1.6.4 sea deprecada.
  3. UsuarioContenedor.tiene_acceso_movil default=True para no bloquear conductores
     sembrados desde la web ni invitados pre-migracion 0009.
  4. Cambiar el response shape de cualquiera de estos endpoints rompe la app.
"""

ENDPOINTS_MOVIL_V164 = (
    'POST /seguridad/login/',
    'POST /contenedor/usuario/nuevo/',
    'POST /seguridad/token/refresh/',
    'POST /contenedor/usuario/cambio-clave-solicitar/',
    'GET /vertical/entrega/<codigo>/',
    'GET /ruteo/visita/',
    'POST /ruteo/visita/entrega/',
    'GET /ruteo/novedad_tipo/',
    'POST /ruteo/novedad/nuevo/',
    'POST /ruteo/novedad/solucionar/',
)
