import math
from io import BytesIO
from datetime import datetime

from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    FrameBreak,
    KeepInFrame,
    PageTemplate,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.pagesizes import A4

from general.models.empresa import GenEmpresa
from ruteo.models.visita import RutVisita


# Tope de etiquetas por PDF: el documento se arma completo en memoria y una
# guía con unidades erradas (p. ej. 50000) tumbaría el worker.
MAX_ETIQUETAS = 1500

# Etiqueta térmica 5x3 pulgadas (127x76mm) en orientación horizontal
PAGE_WIDTH = 127 * mm
PAGE_HEIGHT = 76 * mm
MARGEN = 2.5 * mm
CONTENIDO_ANCHO = PAGE_WIDTH - 2 * MARGEN

INK = HexColor('#0f172a')
INK_SOFT = HexColor('#475569')
MUTED = HexColor('#94a3b8')
BORDER = HexColor('#cbd5e1')
SOFT_BG = HexColor('#f1f5f9')
ACCENT = HexColor('#0f172a')
ACCENT_TEXT = HexColor('#ffffff')
DANGER = HexColor('#dc2626')


def _qr(data, lado_mm=24):
    widget = QrCodeWidget(str(data), barLevel='M')
    x1, y1, x2, y2 = widget.getBounds()
    w, h = x2 - x1, y2 - y1
    objetivo = lado_mm * mm
    drawing = Drawing(
        objetivo,
        objetivo,
        transform=[objetivo / w, 0, 0, objetivo / h, 0, 0],
    )
    drawing.add(widget)
    return drawing


def _truncar(texto, limite):
    texto = (texto or '').strip()
    if len(texto) > limite:
        return texto[: limite - 1].rstrip() + '…'
    return texto


class FormatoRotulo:
    def generar_pdf(self, visita_id):
        return self.generar_pdf_lote([visita_id])

    def generar_pdf_lote(self, visita_ids, formato='termica', por_unidad=False):
        visitas = list(
            RutVisita.objects
            .select_related('ciudad')
            .filter(id__in=visita_ids)
        )
        orden = {v: i for i, v in enumerate(visita_ids)}
        visitas.sort(key=lambda v: orden.get(v.id, 0))

        if not visitas:
            raise RutVisita.DoesNotExist()

        empresa = GenEmpresa.objects.first()
        nombre_empresa = (empresa.nombre_corto if empresa else '').upper()

        # Cada item es (visita, pieza, total_piezas). Con por_unidad una guía
        # de N unidades genera N etiquetas (1/N, 2/N, ...) para poder marcar
        # cada paquete al cargar; sin por_unidad se conserva 1 etiqueta por guía.
        # ceil: unidades es float y truncar dejaría un paquete sin etiqueta.
        items = []
        for visita in visitas:
            total = max(math.ceil(visita.unidades) if visita.unidades else 1, 1)
            if por_unidad:
                items.extend((visita, pieza, total) for pieza in range(1, total + 1))
            else:
                items.append((visita, 1, total))

        if len(items) > MAX_ETIQUETAS:
            raise ValueError(
                f'La impresión genera {len(items)} etiquetas y el máximo es '
                f'{MAX_ETIQUETAS}; revise las unidades de las guías'
            )

        if formato == 'a4':
            return self._render_a4_lote(items, nombre_empresa)
        return self._render_thermal_lote(items, nombre_empresa)

    def _render_thermal_lote(self, items, nombre_empresa):
        primera = items[0][0]
        primera_guia = primera.numero if primera.numero is not None else primera.id
        title = (
            f'Rotulo {primera_guia}' if len(items) == 1
            else f'Rotulos termicos ({len(items)})'
        )

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=(PAGE_WIDTH, PAGE_HEIGHT),
            leftMargin=MARGEN,
            rightMargin=MARGEN,
            topMargin=MARGEN,
            bottomMargin=MARGEN,
            title=title,
            author=nombre_empresa or 'Ruteo',
            subject=title,
            creator=nombre_empresa or 'Ruteo',
        )

        from reportlab.platypus import PageBreak
        elementos = []
        for idx, (visita, pieza, total_piezas) in enumerate(items):
            elementos.extend(self._construir_elementos(visita, nombre_empresa, pieza, total_piezas))
            if idx < len(items) - 1:
                elementos.append(PageBreak())

        doc.build(elementos)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes

    def _render_a4_lote(self, items, nombre_empresa):
        title = f'Rotulos ({len(items)})'
        page_w, page_h = A4
        margen = 5 * mm
        gutter = 3 * mm
        cell_w = (page_w - 2 * margen - gutter) / 2
        cell_h = (page_h - 2 * margen - gutter) / 2

        # Frames en orden top-left → top-right → bottom-left → bottom-right
        frames = [
            Frame(margen, page_h - margen - cell_h, cell_w, cell_h,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
                  showBoundary=0),
            Frame(margen + cell_w + gutter, page_h - margen - cell_h, cell_w, cell_h,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
                  showBoundary=0),
            Frame(margen, margen, cell_w, cell_h,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
                  showBoundary=0),
            Frame(margen + cell_w + gutter, margen, cell_w, cell_h,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
                  showBoundary=0),
        ]

        def _draw_cut_marks(canvas, doc):
            canvas.saveState()
            canvas.setStrokeColor(HexColor('#cbd5e1'))
            canvas.setLineWidth(0.3)
            canvas.setDash(2, 2)
            # Línea horizontal central
            mid_y = page_h / 2
            canvas.line(margen, mid_y, page_w - margen, mid_y)
            # Línea vertical central
            mid_x = page_w / 2
            canvas.line(mid_x, margen, mid_x, page_h - margen)
            canvas.restoreState()

        page_template = PageTemplate(
            id='rotulos', frames=frames, onPage=_draw_cut_marks
        )

        buffer = BytesIO()
        doc = BaseDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=margen,
            rightMargin=margen,
            topMargin=margen,
            bottomMargin=margen,
            title=title,
            author=nombre_empresa or 'Ruteo',
            subject=title,
            creator=nombre_empresa or 'Ruteo',
        )
        doc.addPageTemplates([page_template])

        story = []
        for i, (visita, pieza, total_piezas) in enumerate(items):
            elementos = self._construir_elementos(visita, nombre_empresa, pieza, total_piezas)
            story.append(KeepInFrame(cell_w, cell_h, elementos, mode='shrink'))
            if i < len(items) - 1:
                story.append(FrameBreak())

        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes

    def _construir_elementos(self, visita, nombre_empresa, pieza, total_piezas):
        """Layout para etiqueta horizontal 127×76mm (5×3 pulgadas).

        pieza/total_piezas los calcula únicamente generar_pdf_lote (la regla
        de expansión por unidades vive en un solo lugar).
        """
        guia_numero = visita.numero if visita.numero is not None else visita.id
        zona = (visita.franja_codigo or '—').upper()
        destino = (visita.ciudad.nombre if visita.ciudad else 'SIN CIUDAD').upper()
        destinatario = _truncar(visita.destinatario, 40).upper()
        telefono = visita.destinatario_telefono or ''
        direccion = _truncar(visita.destinatario_direccion or '', 60)
        complemento = _truncar(visita.destinatario_direccion_complemento or '', 50)
        documento = visita.documento or '—'
        unidades_int = total_piezas
        orden_ruteo = int(visita.orden) if visita.orden else 0
        cobro_int = int(visita.cobro) if visita.cobro else 0
        cobro_texto = f'$ {cobro_int:,}'.replace(',', '.') if cobro_int else 'NO'
        peso_texto = f'{int(visita.peso)} kg' if visita.peso else '—'

        st_label_dark = ParagraphStyle(
            'label_dark', fontName='Helvetica-Bold', fontSize=5.5, leading=6.5,
            textColor=HexColor('#cbd5e1'), alignment=TA_LEFT,
        )
        st_label = ParagraphStyle(
            'label', fontName='Helvetica-Bold', fontSize=5.5, leading=6.5,
            textColor=MUTED, alignment=TA_LEFT,
        )
        st_destino = ParagraphStyle(
            'destino', fontName='Helvetica-Bold', fontSize=14, leading=15,
            textColor=ACCENT_TEXT, alignment=TA_LEFT,
        )
        st_zona = ParagraphStyle(
            'zona', fontName='Helvetica-Bold', fontSize=18, leading=19,
            textColor=ACCENT_TEXT, alignment=TA_RIGHT,
        )
        st_guia_valor = ParagraphStyle(
            'guia_valor', fontName='Helvetica-Bold', fontSize=14, leading=15,
            textColor=INK, alignment=TA_LEFT,
        )
        st_doc = ParagraphStyle(
            'doc', fontName='Helvetica', fontSize=7, leading=9,
            textColor=INK_SOFT, alignment=TA_LEFT,
        )
        st_destinatario = ParagraphStyle(
            'destinatario', fontName='Helvetica-Bold', fontSize=10, leading=11,
            textColor=INK, alignment=TA_LEFT,
        )
        st_direccion = ParagraphStyle(
            'direccion', fontName='Helvetica', fontSize=8, leading=10,
            textColor=INK, alignment=TA_LEFT,
        )
        st_telefono = ParagraphStyle(
            'tel', fontName='Helvetica', fontSize=7.5, leading=9,
            textColor=INK, alignment=TA_LEFT,
        )
        st_info_label = ParagraphStyle(
            'info_label', fontName='Helvetica-Bold', fontSize=5.5, leading=6.5,
            textColor=MUTED, alignment=TA_CENTER,
        )
        st_info_value = ParagraphStyle(
            'info_value', fontName='Helvetica-Bold', fontSize=8.5, leading=9.5,
            textColor=INK, alignment=TA_CENTER,
        )
        st_cobro = ParagraphStyle(
            'cobro', fontName='Helvetica-Bold', fontSize=8.5, leading=9.5,
            textColor=DANGER if cobro_int else INK, alignment=TA_CENTER,
        )
        st_pie = ParagraphStyle(
            'pie', fontName='Helvetica', fontSize=5.5, leading=7,
            textColor=INK_SOFT, alignment=TA_LEFT,
        )
        st_pie_strong = ParagraphStyle(
            'pie_strong', fontName='Helvetica-Bold', fontSize=6, leading=7,
            textColor=INK, alignment=TA_RIGHT,
        )

        elementos = []

        # === Header oscuro: DESTINO + ZONA (+ ORDEN cuando la visita ya fue ruteada) ===
        header_left = [
            Paragraph('DESTINO', st_label_dark),
            Paragraph(destino, st_destino),
        ]
        header_right = [
            Paragraph('ZONA', st_label_dark),
            Paragraph(zona, st_zona),
        ]
        if orden_ruteo:
            st_orden = ParagraphStyle(
                'orden', fontName='Helvetica-Bold', fontSize=22, leading=23,
                textColor=ACCENT_TEXT, alignment=TA_RIGHT,
            )
            st_zona_compacta = ParagraphStyle(
                'zona_compacta', fontName='Helvetica-Bold', fontSize=13, leading=14,
                textColor=ACCENT_TEXT, alignment=TA_RIGHT,
            )
            header_right = [
                Paragraph('ZONA', st_label_dark),
                Paragraph(zona, st_zona_compacta),
            ]
            header_orden = [
                Paragraph('ORDEN', st_label_dark),
                Paragraph(str(orden_ruteo), st_orden),
            ]
            header_table = Table(
                [[header_left, header_right, header_orden]],
                colWidths=[
                    CONTENIDO_ANCHO * 0.5,
                    CONTENIDO_ANCHO * 0.24,
                    CONTENIDO_ANCHO * 0.26,
                ],
                rowHeights=[12 * mm],
            )
        else:
            header_table = Table(
                [[header_left, header_right]],
                colWidths=[CONTENIDO_ANCHO * 0.7, CONTENIDO_ANCHO * 0.3],
                rowHeights=[12 * mm],
            )
        header_table.setStyle(
            TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), ACCENT),
                ('LEFTPADDING', (0, 0), (-1, -1), 3 * mm),
                ('RIGHTPADDING', (0, 0), (-1, -1), 3 * mm),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ])
        )
        elementos.append(header_table)
        elementos.append(Spacer(1, 1.5 * mm))

        # === Sección body: 2 columnas (info izquierda + QR derecha) ===
        info_left = [
            Paragraph('GUIA No.', st_label),
            Paragraph(str(guia_numero), st_guia_valor),
            Paragraph(f'<b>DOC</b>&nbsp;&nbsp;{documento}', st_doc),
            Spacer(1, 1.5 * mm),
            Paragraph('ENTREGAR A', st_label),
            Paragraph(destinatario, st_destinatario),
            Paragraph(direccion, st_direccion),
        ]
        if complemento:
            info_left.append(Paragraph(complemento, st_direccion))
        if telefono:
            info_left.append(Spacer(1, 0.5 * mm))
            info_left.append(
                Paragraph(f'<font face="Helvetica-Bold">Tel.</font>&nbsp;&nbsp;{telefono}', st_telefono)
            )

        qr_right = [
            _qr(guia_numero, lado_mm=22),
            Spacer(1, 0.5 * mm),
            Paragraph(f'<b>{guia_numero}</b>', ParagraphStyle(
                'qr_text', fontName='Helvetica-Bold', fontSize=8, leading=9,
                textColor=INK, alignment=TA_CENTER,
            )),
        ]

        body_ancho_qr = 26 * mm
        body_table = Table(
            [[info_left, qr_right]],
            colWidths=[CONTENIDO_ANCHO - body_ancho_qr, body_ancho_qr],
        )
        body_table.setStyle(
            TableStyle([
                ('VALIGN', (0, 0), (0, 0), 'TOP'),
                ('VALIGN', (1, 0), (1, 0), 'TOP'),
                ('ALIGN', (1, 0), (1, 0), 'CENTER'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('LEFTPADDING', (0, 0), (0, 0), 3 * mm),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ])
        )
        elementos.append(body_table)
        elementos.append(Spacer(1, 1.5 * mm))

        # === Cinta inferior: PIEZAS / PESO / COBRO ===
        info_table = Table(
            [
                [
                    Paragraph('PIEZAS', st_info_label),
                    Paragraph('PESO', st_info_label),
                    Paragraph('COBRO', st_info_label),
                ],
                [
                    Paragraph(f'{pieza} / {unidades_int}', st_info_value),
                    Paragraph(peso_texto, st_info_value),
                    Paragraph(cobro_texto, st_cobro),
                ],
            ],
            colWidths=[CONTENIDO_ANCHO / 3] * 3,
        )
        info_table.setStyle(
            TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), SOFT_BG),
                ('LINEABOVE', (0, 0), (-1, 0), 0.4, BORDER),
                ('LINEBELOW', (0, 1), (-1, 1), 0.4, BORDER),
                ('LINEBEFORE', (1, 0), (1, -1), 0.4, BORDER),
                ('LINEBEFORE', (2, 0), (2, -1), 0.4, BORDER),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 1 * mm),
                ('RIGHTPADDING', (0, 0), (-1, -1), 1 * mm),
                ('TOPPADDING', (0, 0), (-1, -1), 1 * mm),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 1 * mm),
            ])
        )
        elementos.append(info_table)
        elementos.append(Spacer(1, 1 * mm))

        # === Footer: empresa + fecha ===
        fecha_actual = datetime.now().strftime('%Y-%m-%d %H:%M')
        elementos.append(
            Table(
                [[Paragraph(f'Remitente: <b>{nombre_empresa}</b>', st_pie),
                  Paragraph(fecha_actual, st_pie_strong)]],
                colWidths=[CONTENIDO_ANCHO * 0.65, CONTENIDO_ANCHO * 0.35],
                style=TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                    ('TOPPADDING', (0, 0), (-1, -1), 0),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                ]),
            )
        )

        return elementos


def _padding_block(elementos):
    """Envuelve elementos en una tabla con padding consistente para que el bloque sea uniforme."""
    return Table(
        [[elementos]],
        colWidths=[CONTENIDO_ANCHO],
        style=TableStyle([
            ('LEFTPADDING', (0, 0), (-1, -1), 3 * mm),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3 * mm),
            ('TOPPADDING', (0, 0), (-1, -1), 1 * mm),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1 * mm),
        ]),
    )
