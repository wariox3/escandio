# Ruteo — Colección Postman

## TL;DR — Notificación "Tu paquete está en camino"

**No hay un endpoint aparte para notificar.** El backend lo hace automático cuando aprobás un despacho:

```
POST /ruteo/despacho/aprobar/
{ "id": 123 }
```

El servicio `NotificacionServicio.notificar_despacho_aprobado` corre en un hilo:

1. Lee todas las visitas del despacho.
2. Para cada visita con `destinatario_telefono` válido, manda la plantilla `entrega` por WhatsApp.
3. El cliente recibe: `Hola {nombre}, {empresa} ha despachado tu pedido. Guías: {documento}`.
4. Queda registrado en `MsjConversacion` / `MsjMensaje` (visible en el inbox).

El response del aprobar incluye `notificaciones`:

```json
{
  "mensaje": "Se aprobo el despacho",
  "notificaciones": {
    "enviado": true,
    "razon": "ok",
    "mensaje": "Notificaciones en cola para 5 destinatario(s).",
    "destinatarios": 5
  }
}
```

Si `enviado=false`, mirá `razon` y `mensaje` para ver qué falta. Ver carpeta **03 — Diagnóstico**.

---

## Pre-condiciones (una vez por tenant)

| Quién | Qué | Cómo |
|---|---|---|
| Super-admin | `Contenedor.acceso_whatsapp_notificaciones=True` | Django admin o panel super-admin |
| Admin tenant | Crear `CtnWhatsappConexion` con credenciales Meta | Setup paso 3 |
| Admin tenant | `GenConfiguracion.rut_whatsapp_habilitado=True` + plantilla configurada | Setup paso 5 |
| Meta | Plantilla `entrega` aprobada en español | Meta Business Manager |
| Meta | Webhook apuntando a `{tenant_url}/mensajeria/webhook/` | Meta Developers |
| Operador | Visitas con `destinatario_telefono` válido (10 dígitos CO o E.164) | Crear/importar visita |

## Estructura de la colección

| Carpeta | Para qué |
|---|---|
| **00 — Setup (una vez por tenant)** | Login + verificar/crear conexión + encender flag de WhatsApp. |
| **01 — Flujo principal: Despacho → WhatsApp automático** | Crear visita → listar despachos → aprobar (dispara el envío) → ver mensaje en inbox. **Esto es lo que querés probar.** |
| **02 — Mensajería (chat con clientes)** | Hablar con un cliente: texto libre (24h), plantilla, imagen, marcar leído, cerrar/reabrir. |
| **03 — Diagnóstico** | Probar credenciales Meta, ver flags, validar webhook. |
| **90 — Super-Admin** | Crear/editar usuarios, resetear contraseñas, asignar permisos. |
| **91 — Catálogo CRUD** | Visita, despacho, configuración. |

## Cómo cargarla

1. Postman → **Import** → arrastrá los dos archivos JSON.
2. Seleccioná el environment **Ruteo - pruebas**.
3. Cualquier request hace **auto-login** si `{{token}}` está vacío (script en la colección).
4. Ajustá `telefono_destinatario` si querés probar con tu número.

## Probar el flujo principal (Runner)

1. Asegurate de que el Setup quedó verde (todos los checks de WhatsApp).
2. Postman → **Runner** → seleccioná la carpeta `01 — Flujo principal: Despacho → WhatsApp automático`.
3. Run.
4. Mirá la **Console** de Postman: vas a ver los logs `notificaciones={...}` y el contenido del último mensaje en la conversación.

## Variables clave

| Variable | Para qué |
|---|---|
| `base_url` | Schema `public` (login y super-admin global). |
| `tenant_url` | `http://<schema>.ruteoapi.online`. Cambialo según el tenant. |
| `token`, `refresh_token` | Auto-rellenados en login. |
| `telefono_destinatario` | Número al que se va a mandar el WhatsApp en el flujo de prueba (default: `573227242549`, el de Jaime). |
| `despacho_id`, `visita_id`, `conversacion_id` | Se autocompletan a medida que corrés los requests del flujo. |

> Nota: `visita_id` no se autocompleta al crear la visita porque el endpoint `nuevo` solo devuelve `{mensaje}`. Si lo necesitás, copialo a mano del listado de visitas (carpeta 91).

## Razones de fallo y arreglo

| `razon` en la respuesta | Significa | Arreglo |
|---|---|---|
| `sin_conexion_activa` | Falta `CtnWhatsappConexion` o está en `error`. | Setup paso 3 + Diagnóstico → Probar credenciales. |
| `tenant_whatsapp_off` | `rut_whatsapp_habilitado=False`. | Setup paso 5. |
| `acceso_whatsapp_notificaciones_off` | El contenedor no tiene WhatsApp habilitado. | Super-admin lo enciende. |
| Mensaje saliente queda en `estado=error` | Meta rechazó (token expirado, plantilla no aprobada, número no válido). | Diagnóstico → Probar credenciales; revisar `error_mensaje` del mensaje. |
