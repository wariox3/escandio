"""PDF del Documento de Terminacion de Viaje.

Se renderiza DESDE el snapshot inmutable (RutTerminacion + RutTerminacionNovedad),
no desde los datos vivos: asi el documento no cambia si luego se edita el viaje.
Reutiliza el encabezado corporativo (FormatoEncabezado) y la numeracion de
paginas (NumberedCanvas) de orden_entrega.
"""
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from contenedor.models import User
from general.formatos.encabezado import FormatoEncabezado
from ruteo.formatos.orden_entrega import NumberedCanvas
from ruteo.models.terminacion import RutTerminacion

AZUL = HexColor('#1F3B57')


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
        estilos = getSampleStyleSheet()
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=letter,
            leftMargin=0.5 * inch, rightMargin=0.5 * inch,
            topMargin=1.4 * inch, bottomMargin=0.6 * inch,
        )

        def _encabezado(canvas, doc):
            FormatoEncabezado().generar_pdf(canvas, "DOCUMENTO DE TERMINACIÓN DE VIAJE")

        elementos = []
        elementos.extend(self._identificacion(terminacion, estilos))
        elementos.append(Spacer(1, 10))
        elementos.extend(self._resumen(terminacion, estilos))
        elementos.append(Spacer(1, 12))
        elementos.extend(self._novedades(novedades, estilos))
        elementos.append(Spacer(1, 14))
        elementos.extend(self._trazabilidad(terminacion, estilos))

        doc.build(elementos, onFirstPage=_encabezado, onLaterPages=_encabezado, canvasmaker=NumberedCanvas)
        pdf = buffer.getvalue()
        buffer.close()
        return pdf

    # -- secciones ----------------------------------------------------------
    @staticmethod
    def _fmt(dt, con_hora=True):
        if not dt:
            return 'N/A'
        return dt.strftime('%Y-%m-%d %H:%M' if con_hora else '%Y-%m-%d')

    def _identificacion(self, t, estilos):
        etiqueta = estilos['Normal'].clone('etq'); etiqueta.fontName = 'Helvetica-Bold'; etiqueta.fontSize = 8
        dato = estilos['Normal'].clone('dat'); dato.fontName = 'Helvetica'; dato.fontSize = 8
        filas = [
            [Paragraph('Viaje:', etiqueta), Paragraph(f'#{t.despacho_id}', dato),
             Paragraph('Placa:', etiqueta), Paragraph(t.placa or 'N/A', dato)],
            [Paragraph('Conductor:', etiqueta), Paragraph(t.conductor_nombre or 'N/A', dato),
             Paragraph('Fecha viaje:', etiqueta), Paragraph(self._fmt(t.fecha_viaje, False), dato)],
            [Paragraph('Inicio:', etiqueta), Paragraph(self._fmt(t.fecha_salida), dato),
             Paragraph('Terminación:', etiqueta), Paragraph(self._fmt(t.fecha_cierre), dato)],
        ]
        ancho = letter[0] - inch
        tabla = Table(filas, colWidths=[ancho * 0.13, ancho * 0.37, ancho * 0.15, ancho * 0.35])
        tabla.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        return [tabla]

    def _resumen(self, t, estilos):
        banner = estilos['Normal'].clone('ban'); banner.fontName = 'Helvetica-Bold'
        banner.fontSize = 12; banner.textColor = colors.white; banner.alignment = 1
        num = estilos['Normal'].clone('num'); num.fontName = 'Helvetica-Bold'; num.fontSize = 10; num.alignment = 1
        etq = estilos['Normal'].clone('etqr'); etq.fontSize = 7; etq.alignment = 1; etq.textColor = colors.grey
        ancho = letter[0] - inch

        titulo = Table([[Paragraph('VIAJE FINALIZADO', banner)]], colWidths=[ancho])
        titulo.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), AZUL),
            ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))

        celdas = [
            [Paragraph(str(t.total_guias), num), Paragraph(str(t.entregadas), num),
             Paragraph(str(t.con_novedad), num), Paragraph(f'{t.porcentaje}%', num)],
            [Paragraph('Total guías', etq), Paragraph('Entregadas', etq),
             Paragraph('Con novedad', etq), Paragraph('Cumplimiento', etq)],
        ]
        resumen = Table(celdas, colWidths=[ancho * 0.25] * 4)
        resumen.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D9D9D9')),
            ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        return [titulo, Spacer(1, 4), resumen]

    def _novedades(self, novedades, estilos):
        titulo = estilos['Normal'].clone('tn'); titulo.fontName = 'Helvetica-Bold'; titulo.fontSize = 9
        elementos = [Paragraph('Guías con novedad', titulo), Spacer(1, 4)]
        if not novedades:
            vacio = estilos['Normal'].clone('vac'); vacio.fontName = 'Helvetica-Oblique'; vacio.fontSize = 8
            elementos.append(Paragraph('Sin guías con novedad', vacio))
            return elementos

        celda = estilos['Normal'].clone('cel'); celda.fontName = 'Helvetica'; celda.fontSize = 7; celda.leading = 9
        data = [['Guía', 'Destinatario', 'Tipo de novedad', 'Descripción', 'Fecha']]
        for n in novedades:
            data.append([
                Paragraph(str(n.numero) if n.numero is not None else 's/n', celda),
                Paragraph(n.destinatario or '', celda),
                Paragraph(n.tipo_novedad or '', celda),
                Paragraph(n.descripcion or '', celda),
                Paragraph(self._fmt(n.fecha), celda),
            ])
        ancho = letter[0] - inch
        tabla = Table(data, repeatRows=1,
                      colWidths=[ancho * 0.10, ancho * 0.25, ancho * 0.22, ancho * 0.28, ancho * 0.15])
        tabla.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        elementos.append(tabla)
        return elementos

    def _trazabilidad(self, t, estilos):
        est = estilos['Normal'].clone('tz'); est.fontName = 'Helvetica'; est.fontSize = 7; est.textColor = colors.grey
        usuario = None
        if t.usuario_id:
            u = User.objects.filter(pk=t.usuario_id).values('nombre', 'apellido').first()
            if u:
                usuario = f"{u['nombre'] or ''} {u['apellido'] or ''}".strip() or None
        texto = f"Confirmó la terminación: {usuario or 'N/A'}  ·  {self._fmt(t.fecha_cierre)}"
        return [Paragraph(texto, est)]
