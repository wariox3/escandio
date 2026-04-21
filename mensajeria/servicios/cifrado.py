from cryptography.fernet import Fernet, InvalidToken
from decouple import config


class CifradoServicio:
    _fernet = None

    @classmethod
    def _obtener_fernet(cls):
        if cls._fernet is None:
            clave = config('MENSAJERIA_FERNET_KEY', default='')
            if not clave:
                raise RuntimeError('MENSAJERIA_FERNET_KEY no está configurada en .env')
            cls._fernet = Fernet(clave.encode() if isinstance(clave, str) else clave)
        return cls._fernet

    @classmethod
    def cifrar(cls, texto_plano):
        if texto_plano is None:
            return None
        return cls._obtener_fernet().encrypt(texto_plano.encode()).decode()

    @classmethod
    def descifrar(cls, texto_cifrado):
        if not texto_cifrado:
            return None
        try:
            return cls._obtener_fernet().decrypt(texto_cifrado.encode()).decode()
        except InvalidToken:
            raise ValueError('No se pudo descifrar el valor (clave Fernet incorrecta o dato corrupto)')
