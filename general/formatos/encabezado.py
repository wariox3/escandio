from decouple import config
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader

from general.models.empresa import GenEmpresa

# Cache en memoria del logo por URL. reportlab redibuja el encabezado en CADA
# pagina, y antes cada dibujo re-descargaba el logo (lento y fragil). Se cachea
# solo el exito; ante un fallo se reintenta la proxima vez, para que un blip de
# red no deje el proceso entero sin logo.
_LOGO_CACHE = {}

AZUL = HexColor('#1F3B57')


def _obtener_logo(empresa):
    if not (empresa and empresa.imagen):
        return None
    try:
        region = config('DO_REGION')
        bucket = config('DO_BUCKET')
    except Exception:
        return None
    url = f'https://{bucket}.{region}.digitaloceanspaces.com/{empresa.imagen}'
    if url in _LOGO_CACHE:
        return _LOGO_CACHE[url]
    try:
        logo = ImageReader(url)
        _LOGO_CACHE[url] = logo
        return logo
    except Exception:
        return None


class FormatoEncabezado():
    def generar_pdf(self, p, titulo):
        empresa = GenEmpresa.objects.filter(pk=1).first()

        logo = _obtener_logo(empresa)
        if logo is not None:
            try:
                p.drawImage(
                    logo, 28, 700,
                    width=75, height=75,
                    preserveAspectRatio=True, anchor='c', mask='auto',
                )
            except Exception:
                pass

        # Barra de titulo corporativa.
        p.setFillColor(AZUL)
        p.rect(120, 756, 450, 19, stroke=0, fill=1)
        p.setFillColor(colors.white)
        p.setFont("Helvetica-Bold", 10)
        p.drawCentredString(345, 761, titulo)

        # Bloque de empresa. Manejo seguro de None (empresa o sus campos).
        p.setFillColor(colors.black)
        nombre_corto = ((empresa.nombre_corto if empresa else '') or '').upper()
        nit = ((empresa.numero_identificacion if empresa else '') or '').upper()
        direccion = ((empresa.direccion if empresa else '') or '').upper()
        telefono = (empresa.telefono if empresa else '') or ''

        p.setFont("Helvetica-Bold", 9)
        p.drawString(120, 740, nombre_corto)
        p.setFont("Helvetica", 8)
        p.drawString(120, 730, f"NIT: {nit}")
        p.drawString(120, 720, f"DIRECCIÓN: {direccion}")
        p.drawString(120, 710, f"TEL: {telefono}")
