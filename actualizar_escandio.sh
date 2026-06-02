#!/usr/bin/env bash
# _*_ ENCODING: UTF-8 _*_
#
# Actualiza el back escandio en el server. Lo invoca deploy-pruebas.sh /
# deploy-prod.sh por ssh: `bash actualizar_escandio.sh [fix]`.
#
# Versionado en el repo a proposito: editar aca, no la copia suelta del server.
#
# Arregla el deploy anterior, que:
#   - hacia `git pull origin develop` y fallaba con "divergent branches",
#   - pero seguia de largo y reportaba "Actualizacion exitosa" en falso,
#     dejando el server en codigo viejo.
# Ahora:
#   - `git fetch` + `git reset --hard origin/$RAMA`: el server ESPEJA el remoto,
#     no hay merge/pull que reconciliar -> nunca mas ese fatal.
#   - `set -eo pipefail` + trap ERR: si git o migrate fallan, corta, NO imprime
#     exito y reintenta levantar el servicio para no dejarlo caido.
set -eo pipefail

RAMA="${RAMA:-develop}"

fallo() {
    echo "!!! Actualizacion escandio FALLO (linea ${1}). Codigo NO actualizado del todo."
    echo "!!! Reintentando iniciar el servicio para no dejarlo caido..."
    service escandio start || true
    exit 1
}
trap 'fallo "$LINENO"' ERR

echo "Se inicia actualizacion escandio"
service escandio stop
echo "servicio escandio detenido"

cd /root/aplicaciones/escandio

# El activate del venv referencia variables que con `set -u` reventarian; por eso
# este script usa solo `set -eo pipefail` (sin -u).
source ~/.venvs/escandio/bin/activate

# Espejar el remoto en vez de `git pull` (mata el "divergent branches").
git fetch origin "$RAMA"
git reset --hard "origin/$RAMA"
echo "Descarga de actualizaciones ($(git log --oneline -1))"

python manage.py migrate
echo "Base de datos actualizada"

if [ -n "${1:-}" ]; then
  if [ "$1" = "fix" ]; then
    #python manage.py all_tenants_command actualizar_fixtures general/fixtures/
    echo "Fixtures actualizados"
  fi
fi

service escandio start
echo "servicio escandio iniciado"
echo "Actualizacion exitosa escandio"
