from io import BytesIO
from datetime import datetime

from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from general.models.empresa import GenEmpresa
from ruteo.models.visita import RutVisita


PAGE_WIDTH = 100 * mm
PAGE_HEIGHT = 150 * mm
MARGEN = 4 * mm
CONTENIDO_ANCHO = PAGE_WIDTH - 2 * MARGEN


def _qr(data, lado_mm=22):
    """Genera un QR escalado a un tamaño fijo en milímetros."""
    widget = QrCodeWidget(str(data))
    x1, y1, x2, y2 = widget.getBounds()
    ancho_widget = x2 - x1
    alto_widget = y2 - y1
    objetivo = lado_mm * mm
    drawing = Drawing(
        objetivo,
        objetivo,
        transform=[objetivo / ancho_widget, 0, 0, objetivo / alto_widget, 0, 0],
    )
    drawing.add(widget)
    return drawing


class FormatoRotulo:
    def generar_pdf(self, visita_id):
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=(PAGE_WIDTH, PAGE_HEIGHT),
            leftMargin=MARGEN,
            rightMargin=MARGEN,
            topMargin=MARGEN,
            bottomMargin=MARGEN,
        )

        visita = (
            RutVisita.objects
            .select_related('ciudad')
            .get(id=visita_id)
        )

        empresa = GenEmpresa.objects.first()
        nombre_empresa = empresa.nombre_corto if empresa else ''

        guia = ParagraphStyle(
            'guia', fontName='Helvetica-Bold', fontSize=14, leading=15, alignment=TA_LEFT,
        )
        doc_cliente = ParagraphStyle(
            'doc', fontName='Helvetica-Bold', fontSize=10, leading=11, alignment=TA_LEFT,
        )
        etiqueta = ParagraphStyle(
            'etiqueta', fontName='Helvetica-Bold', fontSize=7, leading=8, alignment=TA_LEFT,
        )
        dato = ParagraphStyle(
            'dato', fontName='Helvetica', fontSize=8, leading=10, alignment=TA_LEFT,
        )
        destino = ParagraphStyle(
            'destino', fontName='Helvetica-Bold', fontSize=11, leading=12, alignment=TA_LEFT,
        )
        info = ParagraphStyle(
            'info', fontName='Helvetica', fontSize=8, leading=9, alignment=TA_CENTER,
        )
        pie = ParagraphStyle(
            'pie', fontName='Helvetica', fontSize=6.5, leading=8, alignment=TA_CENTER,
        )

        elementos = []
        guia_numero = visita.numero if visita.numero is not None else visita.id

        elementos.append(Paragraph(f'GUIA No. {guia_numero}', guia))
        elementos.append(
            Paragraph(f'DOC CLIENTE: {visita.documento or ""}', doc_cliente)
        )
        elementos.append(Spacer(1, 4))

        elementos.append(Paragraph('DESTINATARIO:', etiqueta))
        elementos.append(Paragraph(visita.destinatario or '', dato))
        elementos.append(Spacer(1, 2))

        direccion = visita.destinatario_direccion or ''
        if visita.destinatario_direccion_complemento:
            direccion = f'{direccion} {visita.destinatario_direccion_complemento}'.strip()
        elementos.append(Paragraph('DIRECCION:', etiqueta))
        elementos.append(Paragraph(direccion, dato))
        elementos.append(Spacer(1, 2))

        elementos.append(Paragraph('DESTINO:', etiqueta))
        elementos.append(
            Paragraph(visita.ciudad.nombre if visita.ciudad else '', destino)
        )
        elementos.append(Spacer(1, 2))

        remitente = visita.remitente or nombre_empresa
        elementos.append(Paragraph('REMITENTE:', etiqueta))
        elementos.append(Paragraph(remitente, dato))
        elementos.append(Spacer(1, 4))

        unidades = int(visita.unidades) if visita.unidades else 1
        cobro = int(visita.cobro) if visita.cobro else 0
        zona = visita.franja_codigo or ''
        info_table = Table(
            [[
                Paragraph(f'<b>ZONA</b><br/>{zona}', info),
                Paragraph(f'<b>PIEZA</b><br/>1/{unidades}', info),
                Paragraph(f'<b>COBRO</b><br/>{cobro}', info),
            ]],
            colWidths=[CONTENIDO_ANCHO / 3] * 3,
        )
        info_table.setStyle(
            TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BOX', (0, 0), (-1, -1), 0.4, colors.black),
                ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.black),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ])
        )
        elementos.append(info_table)
        elementos.append(Spacer(1, 6))

        qr_table = Table(
            [[_qr(guia_numero), _qr(guia_numero)]],
            colWidths=[CONTENIDO_ANCHO / 2, CONTENIDO_ANCHO / 2],
            rowHeights=[24 * mm],
        )
        qr_table.setStyle(
            TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (0, 0), (0, 0), 'CENTER'),
                ('ALIGN', (1, 0), (1, 0), 'CENTER'),
            ])
        )
        elementos.append(qr_table)

        elementos.append(Spacer(1, 4))
        fecha_actual = datetime.now().strftime('%Y-%m-%d %H:%M')
        elementos.append(
            Paragraph(
                f'{nombre_empresa.upper()}  ·  FECHA {fecha_actual}',
                pie,
            )
        )

        doc.build(elementos)

        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes
