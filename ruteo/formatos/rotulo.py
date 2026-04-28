from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import inch
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER

from general.models.empresa import GenEmpresa
from ruteo.models.visita import RutVisita
from utilidades.utilidades import generar_qr


PAGE_WIDTH = 100 * mm
PAGE_HEIGHT = 150 * mm


class FormatoRotulo:
    def generar_pdf(self, visita_id):
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=(PAGE_WIDTH, PAGE_HEIGHT),
            leftMargin=4 * mm,
            rightMargin=4 * mm,
            topMargin=4 * mm,
            bottomMargin=4 * mm,
        )

        visita = (
            RutVisita.objects
            .select_related('ciudad')
            .get(id=visita_id)
        )

        empresa = GenEmpresa.objects.first()
        nombre_empresa = empresa.nombre_corto if empresa else ''

        elementos = []

        estilo_titulo = ParagraphStyle(
            'titulo',
            fontName='Helvetica-Bold',
            fontSize=14,
            alignment=TA_LEFT,
            leading=16,
        )
        estilo_cliente = ParagraphStyle(
            'cliente',
            fontName='Helvetica-Bold',
            fontSize=11,
            alignment=TA_LEFT,
            leading=13,
        )
        estilo_etiqueta = ParagraphStyle(
            'etiqueta',
            fontName='Helvetica-Bold',
            fontSize=8,
            alignment=TA_LEFT,
            leading=10,
        )
        estilo_dato = ParagraphStyle(
            'dato',
            fontName='Helvetica',
            fontSize=8,
            alignment=TA_LEFT,
            leading=10,
        )
        estilo_destino = ParagraphStyle(
            'destino',
            fontName='Helvetica-Bold',
            fontSize=10,
            alignment=TA_LEFT,
            leading=12,
        )
        estilo_pie = ParagraphStyle(
            'pie',
            fontName='Helvetica',
            fontSize=7,
            alignment=TA_CENTER,
            leading=9,
        )

        guia_numero = visita.numero if visita.numero is not None else visita.id
        elementos.append(Paragraph(f'GUIA No. {guia_numero}', estilo_titulo))
        elementos.append(
            Paragraph(f'DOC CLIENTE: {visita.documento or ""}', estilo_cliente)
        )
        elementos.append(Spacer(1, 4))

        elementos.append(Paragraph('DESTINATARIO:', estilo_etiqueta))
        elementos.append(
            Paragraph(visita.destinatario or '', estilo_dato)
        )
        elementos.append(Spacer(1, 2))

        direccion_completa = visita.destinatario_direccion or ''
        if visita.destinatario_direccion_complemento:
            direccion_completa = (
                f'{direccion_completa} {visita.destinatario_direccion_complemento}'.strip()
            )
        elementos.append(Paragraph('DIRECCION:', estilo_etiqueta))
        elementos.append(Paragraph(direccion_completa, estilo_dato))
        elementos.append(Spacer(1, 2))

        ciudad_nombre = visita.ciudad.nombre if visita.ciudad else ''
        elementos.append(Paragraph('DESTINO:', estilo_etiqueta))
        elementos.append(Paragraph(ciudad_nombre, estilo_destino))
        elementos.append(Spacer(1, 2))

        remitente = visita.remitente or nombre_empresa
        elementos.append(Paragraph('REMITENTE:', estilo_etiqueta))
        elementos.append(Paragraph(remitente, estilo_dato))
        elementos.append(Spacer(1, 4))

        unidades = int(visita.unidades) if visita.unidades else 1
        cobro = int(visita.cobro) if visita.cobro else 0
        info_data = [
            [
                Paragraph(f'<b>ZONA:</b> {visita.franja_codigo or ""}', estilo_dato),
                Paragraph(f'<b>PIEZA</b> 1/{unidades}', estilo_dato),
                Paragraph(f'<b>COBRO:</b> {cobro}', estilo_dato),
            ]
        ]
        ancho_total = PAGE_WIDTH - (8 * mm)
        info_table = Table(info_data, colWidths=[ancho_total / 3] * 3)
        info_table.setStyle(
            TableStyle(
                [
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('TOPPADDING', (0, 0), (-1, -1), 1),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
                ]
            )
        )
        elementos.append(info_table)
        elementos.append(Spacer(1, 6))

        qr_data = str(guia_numero)
        qr_left = generar_qr(qr_data)
        qr_right = generar_qr(qr_data)

        qr_table = Table(
            [[qr_left, qr_right]],
            colWidths=[ancho_total / 2, ancho_total / 2],
            rowHeights=[60],
        )
        qr_table.setStyle(
            TableStyle(
                [
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                    ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                ]
            )
        )
        elementos.append(qr_table)

        elementos.append(Spacer(1, 4))
        fecha_actual = datetime.now().strftime('%Y-%m-%d %H:%M')
        elementos.append(
            Paragraph(
                f'{nombre_empresa.upper()} &nbsp;&nbsp;&nbsp; FECHA {fecha_actual}',
                estilo_pie,
            )
        )

        doc.build(elementos)

        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes
