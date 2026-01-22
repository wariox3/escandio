import requests
from rest_framework.exceptions import ValidationError
from decouple import config

class CloudflareTurnstile:
    VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    
    @classmethod
    def verify_token(cls, token, secret_key, ip_address=None):
        if not token:
            raise ValidationError({
                'cf_turnstile_response': "Token de Turnstile no proporcionado"
            })
            
        if not secret_key:
            # Si no hay secret key configurada, considerar como válido (para desarrollo)
            return True
            
        data = {
            'secret': secret_key,
            'response': token
        }
        
        if ip_address:
            data['remoteip'] = ip_address
            
        try:
            response = requests.post(cls.VERIFY_URL, data=data, timeout=5)
            response.raise_for_status()  # Lanza excepción para códigos HTTP 4xx/5xx
            result = response.json()
            
            if not result.get('success'):
                error_codes = result.get('error-codes', ['unknown'])
                raise ValidationError({
                    'cf_turnstile_response': f"Error en verificación Turnstile: {', '.join(error_codes)}",
                    'error_codes': error_codes
                })
                
            return True
        except requests.RequestException as e:
            raise ValidationError({
                'cf_turnstile_response': f"Error al conectar con el servicio de verificación: {str(e)}"
            })