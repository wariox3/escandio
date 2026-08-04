"""PDF del Documento de Terminacion de Viaje.

Se renderiza DESDE el snapshot inmutable (RutTerminacion + RutTerminacionNovedad),
no desde los datos vivos: asi el documento no cambia si luego se edita el viaje.
Reutiliza el encabezado corporativo (FormatoEncabezado) y la numeracion de
paginas (NumberedCanvas) de orden_entrega.
"""
from datetime import datetime
from io import BytesIO

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from contenedor.models import User
from general.formatos.encabezado import FormatoEncabezado
from ruteo.formatos.orden_entrega import NumberedCanvas
from ruteo.models.terminacion import RutTerminacion

AZUL = HexColor('#1F3B57')
GRIS_BORDE = HexColor('#D9D9D9')
GRIS_LINEA = HexColor('#EEEEEE')
GRIS_TEXTO = HexColor('#6B7280')
CEBRA = HexColor('#F7F9FB')
VERDE = HexColor('#16A34A'); VERDE_BG = HexColor('#F0FDF4')
AMBAR = HexColor('#B45309'); AMBAR_BG = HexColor('#FFFBEB')
AZULK = HexColor('#1D4ED8'); AZULK_BG = HexColor('#EFF6FF')

ANCHO = letter[0] - 1.2 * inch


class FormatoTerminacionViaje:

    def generar_pdf(self, despacho_id):
        terminacion = (
            RutTerminacion.objects
            .filter(despacho_id=despacho_id)
            .order_by('-id')
            .first()
        )
        if terminacion is None:
            return None
        novedades = list(terminacion.novedades.all())

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=letter,
            leftMargin=0.6 * inch, rightMargin=0.6 * inch,
            topMargin=1.5 * inch, bottomMargin=0.7 * inch,
        )

        def _encabezado(canvas, doc):
            FormatoEncabezado().generar_pdf(canvas, "DOCUMENTO DE TERMINACIÓN DE VIAJE")

        elementos = []
        elementos += self._identificacion(terminacion)
        elementos.append(Spacer(1, 14))
        elementos += self._resultado(terminacion)
        elementos.append(Spacer(1, 16))
        elementos += self._novedades(novedades)
        elementos.append(Spacer(1, 18))
        elementos += self._trazabilidad(terminacion)

        doc.build(elementos, onFirstPage=_encabezado, onLaterPages=_encabezado, canvasmaker=NumberedCanvas)
        pdf = buffer.getvalue()
        buffer.close()
        return pdf

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _fmt(dt, con_hora=True):
        if not dt:
            return 'N/A'
        # La BD guarda en UTC (USE_TZ=True); convertir a la hora local (America/Bogota)
        # antes de formatear, si es un datetime con zona.
        if isinstance(dt, datetime) and timezone.is_aware(dt):
            dt = timezone.localtime(dt)
        return dt.strftime('%Y-%m-%d %H:%M' if con_hora else '%Y-%m-%d')

    @staticmethod
    def _usuario(usuario_id):
        if not usuario_id:
            return None
        u = User.objects.filter(pk=usuario_id).values('nombre', 'apellido').first()
        if u:
            return f"{u['nombre'] or ''} {u['apellido'] or ''}".strip() or None
        return None

    def _titulo(self, texto):
        st = ParagraphStyle('sec', fontName='Helvetica-Bold', fontSize=9, textColor=AZUL,
                            spaceAfter=2, tracking=0.5)
        return [Paragraph(texto.upper(), st),
                HRFlowable(width='100%', thickness=0.8, color=GRIS_BORDE, spaceAfter=7)]

    # -- secciones ----------------------------------------------------------
    def _identificacion(self, t):
        etq = ParagraphStyle('etq', fontName='Helvetica', fontSize=7.5, textColor=GRIS_TEXTO)
        dat = ParagraphStyle('dat', fontName='Helvetica-Bold', fontSize=8.5, textColor=colors.black)

        def par(label, value):
            return [Paragraph(label, etq), Paragraph(value if value else 'N/A', dat)]

        filas = [
            par('AGENCIA', t.agencia) + par('ORDEN DE ENTREGA', str(t.consecutivo) if t.consecutivo else None),
            par('VIAJE', f'#{t.despacho_id}') + par('PLACA', t.placa),
            par('CONDUCTOR', t.conductor_nombre) + par('FECHA DEL VIAJE', self._fmt(t.fecha_viaje, False)),
            par('INICIO', self._fmt(t.fecha_salida)) + par('TERMINACIÓN', self._fmt(t.fecha_cierre)),
        ]
        tabla = Table(filas, colWidths=[ANCHO * 0.19, ANCHO * 0.31, ANCHO * 0.19, ANCHO * 0.31])
        tabla.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LINEBELOW', (0, 0), (-1, -2), 0.5, GRIS_LINEA),
        ]))
        return self._titulo('Identificación del viaje') + [tabla]

    def _resultado(self, t):
        ban = ParagraphStyle('ban', fontName='Helvetica-Bold', fontSize=12, textColor=colors.white, alignment=1)
        banner = Table([[Paragraph('VIAJE FINALIZADO', ban)]], colWidths=[ANCHO])
        banner.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), AZUL),
            ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ]))

        def kpi(valor, etiqueta, color_num, bg):
            ns = ParagraphStyle('kn', fontName='Helvetica-Bold', fontSize=16, textColor=color_num,
                                alignment=1, leading=18, spaceAfter=3)
            ls = ParagraphStyle('kl', fontName='Helvetica', fontSize=6.5, textColor=GRIS_TEXTO,
                                alignment=1, leading=8)
            celda = [Paragraph(str(valor), ns), Paragraph(etiqueta, ls)]
            c = Table([[celda]], colWidths=[ANCHO * 0.25 - 6])
            c.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), bg),
                ('BOX', (0, 0), (-1, -1), 0.7, GRIS_BORDE),
                ('TOPPADDING', (0, 0), (-1, -1), 9), ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
                ('LEFTPADDING', (0, 0), (-1, -1), 2), ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            return c

        tarjetas = Table([[
            kpi(t.total_guias, 'TOTAL GUÍAS', colors.black, colors.white),
            kpi(t.entregadas, 'ENTREGADAS', VERDE, VERDE_BG),
            kpi(t.con_novedad, 'CON NOVEDAD', AMBAR, AMBAR_BG),
            kpi(f'{t.porcentaje}%', 'CUMPLIMIENTO', AZULK, AZULK_BG),
        ]], colWidths=[ANCHO * 0.25] * 4)
        tarjetas.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ]))

        res = ParagraphStyle('res', fontName='Helvetica', fontSize=9, textColor=colors.black, leading=13)
        guias_nov = 'guía' if t.con_novedad == 1 else 'guías'
        texto = (f'El viaje finalizó con <b>{t.entregadas}</b> de <b>{t.total_guias}</b> guías entregadas '
                 f'(<b>{t.porcentaje}%</b> de cumplimiento)')
        texto += (f' y <b>{t.con_novedad}</b> {guias_nov} con novedad, según el detalle.'
                  if t.con_novedad else ', sin guías con novedad.')

        return self._titulo('Resultado') + [banner, Spacer(1, 7), tarjetas, Spacer(1, 9), Paragraph(texto, res)]

    def _novedades(self, novedades):
        if not novedades:
            vac = ParagraphStyle('vac', fontName='Helvetica-Oblique', fontSize=8.5, textColor=GRIS_TEXTO)
            return self._titulo('Guías con novedad') + [Paragraph('Sin guías con novedad.', vac)]

        celda = ParagraphStyle('cel', fontName='Helvetica', fontSize=7.5, leading=9.5)
        head = ParagraphStyle('h', fontName='Helvetica-Bold', fontSize=7.5, textColor=colors.white)
        data = [[Paragraph(x, head) for x in ['Guía', 'Destinatario', 'Tipo de novedad', 'Descripción', 'Fecha']]]
        for n in novedades:
            data.append([
                Paragraph(str(n.numero) if n.numero is not None else 's/n', celda),
                Paragraph(n.destinatario or '', celda),
                Paragraph(n.tipo_novedad or '', celda),
                Paragraph(n.descripcion or '', celda),
                Paragraph(self._fmt(n.fecha), celda),
            ])
        tabla = Table(data, repeatRows=1,
                      colWidths=[ANCHO * 0.10, ANCHO * 0.24, ANCHO * 0.22, ANCHO * 0.29, ANCHO * 0.15])
        estilo = [
            ('BACKGROUND', (0, 0), (-1, 0), AZUL),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LINEBELOW', (0, 0), (-1, -1), 0.4, GRIS_BORDE),
            ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]
        for i in range(2, len(data), 2):
            estilo.append(('BACKGROUND', (0, i), (-1, i), CEBRA))
        tabla.setStyle(TableStyle(estilo))
        return self._titulo('Guías con novedad') + [tabla]

    def _trazabilidad(self, t):
        etq = ParagraphStyle('tzl', fontName='Helvetica', fontSize=7.5, textColor=GRIS_TEXTO)
        dat = ParagraphStyle('tzd', fontName='Helvetica-Bold', fontSize=8.5)
        info = Table([[
            Paragraph('Confirmó la terminación', etq), Paragraph(self._usuario(t.usuario_id) or 'N/A', dat),
            Paragraph('Fecha y hora de cierre', etq), Paragraph(self._fmt(t.fecha_cierre), dat),
        ]], colWidths=[ANCHO * 0.22, ANCHO * 0.28, ANCHO * 0.22, ANCHO * 0.28])
        info.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))

        lbl = ParagraphStyle('fl', fontName='Helvetica', fontSize=7.5, textColor=GRIS_TEXTO, alignment=1)
        firma = Table([['', ''], [Paragraph('Firma / Aceptación', lbl), Paragraph('Observaciones', lbl)]],
                      colWidths=[ANCHO * 0.5, ANCHO * 0.5], rowHeights=[36, 14])
        firma.setStyle(TableStyle([
            ('LINEABOVE', (0, 1), (0, 1), 0.7, colors.black),
            ('LINEABOVE', (1, 1), (1, 1), 0.7, colors.black),
            ('LEFTPADDING', (0, 0), (-1, -1), 24), ('RIGHTPADDING', (0, 0), (-1, -1), 24),
            ('VALIGN', (0, 1), (-1, 1), 'TOP'),
        ]))
        return self._titulo('Trazabilidad y validación') + [info, Spacer(1, 12), firma]
