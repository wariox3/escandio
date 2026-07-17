"""Errores de dominio de los servicios moviles v2."""


class EvidenciaNoGuardada(Exception):
    """No se pudieron persistir las fotos/firmas (Backblaze o el registro del
    archivo fallo). La entrega/novedad NO debe darse por registrada: su
    transaccion se revierte y el conductor reintenta. Se convierte en un error
    LIMPIO del envelope v2 (no un 500 opaco que la app muestra como "servidor
    fuera de linea" y reintenta en bucle)."""
