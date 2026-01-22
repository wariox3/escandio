# Backend Ruteo.co

Para instalar el proyecto debes seguir las siguientes instrucciones en la terminar

```sh
git clone
cd escandio
crear archivo al nivel de manage.py llamado .env con estas variables

DATABASE_USER='user'
DATABASE_CLAVE='clave'
DATABASE_HOST='localhost'
DATABASE_NAME='bdprueba'
DATABASE_PORT='5432'
#Entorno
ENV='dev'
DOMINIO_BACKEND='ruteoapi.online'
DOMINIO_FRONTEND='ruteo.online'
#Credenciales sendgrid
KEY_SENDGRID='xyz'
#Credenciales S#
DO_CLAVE_ACCESO="xyz"
DO_CLAVE_SECRETA="xyz"
DO_REGION="xyz"
DO_BUCKET="xyz"
#Agregar los secret key de cloudflare para cada proyecto
CF_TURNSTILE_SECRET_KEY_REDDOC='xyz'
CF_TURNSTILE_SECRET_KEY_RUTEO='xyz'
CF_TURNSTILE_SECRET_KEY_POS='xyz'
#GoogleKey
GOOGLE_MAPS_API_KEY=""
#Pasarela de pago
WOMPI_SECRETO_INTEGRIDAD=
python3.10 -m venv ~/.venvs/escandio
source ~/.venvs/escandio/bin/activate
pip3 install -r requirements.txt
cd escandio
python3 manage.py runserver
# Migrar la base de datos -> Debe estar creada
python3 manage.py migrate
```

