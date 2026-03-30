#!/bin/bash
python manage.py shell << 'EOF'
from contenedor.models import User
u = User.objects.get(username='prueba@gmail.com')
u.set_password('Prueba123')
u.save()
print('Listo')
EOF
