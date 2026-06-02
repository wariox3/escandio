#!/usr/bin/env bash
#
# Deploy de escandio.
#
# Espeja origin/<BRANCH> en el servidor (NO hace merge/pull) y reinicia el
# servicio. Versionado en el repo a proposito: editar este archivo, no una
# copia suelta en el server. En el server se invoca este mismo script.
#
# Arregla dos problemas del deploy anterior:
#   1. `git pull` fallaba con "divergent branches" y dejaba el server en codigo
#      viejo. Ahora `fetch` + `reset --hard origin/$BRANCH`: el working tree
#      queda SIEMPRE identico al remoto, sin reconciliacion posible.
#   2. El script reportaba "Actualizacion exitosa" aunque un paso fallara. Ahora
#      `set -euo pipefail` + trap ERR: corta ante el primer error y NO imprime
#      el mensaje de exito.
#
# Uso:  ./deploy.sh            (usa los defaults de abajo)
#       BRANCH=develop SERVICE=escandio ./deploy.sh   (override por entorno)
#
set -euo pipefail

# --- Config (ajustar a las rutas/servicio del server) ---
REPO_DIR="${REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
VENV_DIR="${VENV_DIR:-$REPO_DIR/venv}"
BRANCH="${BRANCH:-develop}"
SERVICE="${SERVICE:-escandio}"

log() { echo "=== $*"; }

# Ante cualquier error: avisar claro (sin "exito" enganoso) e intentar dejar el
# servicio arriba para no dejarlo caido entre el stop y el start.
deploy_fallo() {
    echo "!!! Deploy de $SERVICE FALLO en la linea ${1}. Codigo NO actualizado del todo."
    echo "!!! Intentando reiniciar el servicio para no dejarlo caido..."
    systemctl start "$SERVICE" || true
    exit 1
}
trap 'deploy_fallo "$LINENO"' ERR

cd "$REPO_DIR"

log "Se inicia actualizacion $SERVICE"

# 1. Detener el servicio
systemctl stop "$SERVICE"
log "servicio $SERVICE detenido"

# 2. Traer y ESPEJAR el remoto (sin merge/pull -> sin "divergent branches")
log "Descarga de actualizaciones"
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"
log "Commit desplegado: $(git log --oneline -1)"

# 3. Dependencias (idempotente; no-op si requirements.txt no cambio)
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install -q -r requirements.txt

# 4. Migraciones de public + TODOS los tenants en una sola corrida (django-tenants)
log "Starting migration"
python manage.py migrate_schemas --noinput
log "Base de datos actualizada"

# 5. Reiniciar el servicio
systemctl start "$SERVICE"
log "servicio $SERVICE iniciado"

log "Actualizacion exitosa $SERVICE"
