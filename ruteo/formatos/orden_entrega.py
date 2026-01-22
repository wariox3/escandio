from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from datetime import datetime

from general.formatos.encabezado import FormatoEncabezado
from ruteo.models.visita import RutVisita
from ruteo.models.despacho import RutDespacho


# --- Canvas personalizado para numeración "Página X de Y" ---
class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super(NumberedCanvas, self).__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        """Agregar el número total de páginas a cada página"""
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super(NumberedCanvas, self).showPage()
        super(NumberedCanvas, self).save()

    def draw_page_number(self, page_count):
        page = self.getPageNumber()
        text = f"Página {page} de {page_count}"
        self.setFont("Helvetica", 8)
        self.drawRightString(letter[0] - 0.5*inch, 0.4*inch, text)


class FormatoOrdenEntrega:
    def generar_pdf(self, despacho_id):
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=0.4*inch, rightMargin=0.4*inch,
            topMargin=1.4*inch, bottomMargin=0.5*inch
        )
        elementos = []
        estilos = getSampleStyleSheet()

        def _encabezado(canvas, doc):
            FormatoEncabezado().generar_pdf(canvas, "ORDEN DE ENTREGA")

        try:
            despacho = RutDespacho.objects.get(id=despacho_id)
        except RutDespacho.DoesNotExist:
            elementos.append(Paragraph("Despacho no encontrado.", estilos["Normal"]))
            doc.build(elementos, onFirstPage=_encabezado, onLaterPages=_encabezado,
                      canvasmaker=NumberedCanvas)
            pdf_bytes = buffer.getvalue()
            buffer.close()
            return pdf_bytes

        visitas = RutVisita.objects.filter(despacho_id=despacho_id).order_by('orden')

        # --- Estilos ---
        estilo_etiqueta = estilos["Normal"].clone('etiqueta')
        estilo_etiqueta.fontName = "Helvetica-Bold"
        estilo_etiqueta.fontSize = 8
        estilo_etiqueta.leading = 11

        estilo_dato = estilos["Normal"].clone('dato')
        estilo_dato.fontName = "Helvetica"
        estilo_dato.fontSize = 8
        estilo_dato.leading = 11

        estilo_fecha = estilos["Normal"].clone('fecha')
        estilo_fecha.fontName = "Helvetica"
        estilo_fecha.fontSize = 8
        estilo_fecha.leading = 11

        fecha_formateada = despacho.fecha.strftime("%Y-%m-%d") if despacho.fecha else "N/A"

        # Fila 1 - Agregar "Orden entrega:" antes de "Vehículo:"
        fila1_data = [
            Paragraph("Id:", estilo_etiqueta),
            Paragraph(str(despacho.id), estilo_dato),
            Paragraph("Orden entrega:", estilo_etiqueta),
            Paragraph(str(despacho.entrega_id) if hasattr(despacho, 'entrega_id') and despacho.entrega_id else "N/A", estilo_dato),
            Paragraph("Vehículo:", estilo_etiqueta),
            Paragraph(str(despacho.vehiculo.placa if despacho.vehiculo else "N/A"), estilo_dato),
            Paragraph("Fecha:", estilo_etiqueta),
            Paragraph(fecha_formateada, estilo_fecha)
        ]

        # Fila 2 - Agregar "Código complemento:" antes de "Peso Total:"
        fila2_data = [
            Paragraph("Complemento:", estilo_etiqueta),
            Paragraph(str(despacho.codigo_complemento) if hasattr(despacho, 'codigo_complemento') and despacho.codigo_complemento else "N/A", estilo_dato),
            Paragraph("Unidades:", estilo_etiqueta),
            Paragraph(f"{int(despacho.unidades)}" if despacho.unidades else "0", estilo_dato),
            Paragraph("Peso Total:", estilo_etiqueta),
            Paragraph(f"{int(despacho.peso)}" if despacho.peso else "0", estilo_dato),
            Paragraph("Total Visitas:", estilo_etiqueta),
            Paragraph(str(visitas.count()), estilo_dato)
        ]

        # Ajustar los anchos de columna para acomodar los nuevos campos
        ancho_total = letter[0] - (0.8 * inch)
        anchos_columnas = [
            ancho_total * 0.15,  
            ancho_total * 0.05,  
            ancho_total * 0.15,  
            ancho_total * 0.10,  
            ancho_total * 0.15,  
            ancho_total * 0.10, 
            ancho_total * 0.12, 
            ancho_total * 0.14,
        ]

        # Ajustar tabla_fila2 para 8 columnas también
        anchos_columnas_fila2 = [
            ancho_total * 0.15,  # Etiqueta 1 (Código complemento:)
            ancho_total * 0.05,  # Dato 1 (codigo_complemento)
            ancho_total * 0.15,  # Etiqueta 2 (Peso Total:)
            ancho_total * 0.10,  # Dato 2 (peso)
            ancho_total * 0.15,  # Etiqueta 3 (Volumen Total:)
            ancho_total * 0.10,  # Dato 3 (volumen)
            ancho_total * 0.12,  # Etiqueta 4 (Total Visitas:)
            ancho_total * 0.14,  # Dato 4 (count)
        ]

        tabla_fila1 = Table([fila1_data], colWidths=anchos_columnas)
        tabla_fila2 = Table([fila2_data], colWidths=anchos_columnas_fila2)

        estilo_info_despacho = TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
        ])

        tabla_fila1.setStyle(estilo_info_despacho)
        tabla_fila2.setStyle(estilo_info_despacho)

        elementos.append(tabla_fila1)
        elementos.append(tabla_fila2)
        elementos.append(Spacer(1, 12))

        if not visitas.exists():
            elementos.append(Paragraph("No hay visitas registradas.", estilos["Normal"]))
        else:
            data = [["", "Id", "Número", "Documento", "Destinatario", "Teléfono", "Dirección", "Und", "Peso"]]

            estilo_normal = estilos["Normal"].clone('normal_tabla')
            estilo_normal.fontName = "Helvetica"
            estilo_normal.fontSize = 7
            estilo_normal.leading = 9
            estilo_normal.wordWrap = True

            estilo_numero = estilos["Normal"].clone('numero_tabla')
            estilo_numero.fontName = "Helvetica"
            estilo_numero.fontSize = 7
            estilo_numero.alignment = 2
            estilo_numero.wordWrap = True

            for visita in visitas:
                telefono = str(visita.destinatario_telefono) if visita.destinatario_telefono else ""
                orden = Paragraph(str(visita.orden), estilo_normal)
                id_visita = Paragraph(str(visita.id), estilo_normal)
                numero = Paragraph(str(visita.numero), estilo_normal)
                documento = Paragraph(str(visita.documento), estilo_normal)
                destinatario = Paragraph(str(visita.destinatario), estilo_normal)
                destinatario_telefono = Paragraph(telefono, estilo_normal)
                direccion = Paragraph(str(visita.destinatario_direccion), estilo_normal)

                peso_formateado = str(int(visita.peso)) if visita.peso else "0"
                unidad_formateado = str(int(visita.unidades)) if visita.unidades else "0"
                peso = Paragraph(peso_formateado, estilo_numero)
                unidad = Paragraph(unidad_formateado, estilo_numero)

                data.append([orden, id_visita, numero, documento, destinatario,
                             destinatario_telefono, direccion, unidad, peso])

            anchos_columnas_visitas = [
                ancho_total * 0.04,
                ancho_total * 0.06,
                ancho_total * 0.08,
                ancho_total * 0.10,
                ancho_total * 0.22,
                ancho_total * 0.10,
                ancho_total * 0.30,
                ancho_total * 0.05,
                ancho_total * 0.05,
            ]

            table = Table(data, repeatRows=1, colWidths=anchos_columnas_visitas)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("ALIGN", (0, 1), (-1, -1), "LEFT"),
                ("ALIGN", (6, 1), (6, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("WORDWRAP", (0, 0), (-1, -1)),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            elementos.append(table)

        doc.build(
            elementos,
            onFirstPage=_encabezado,
            onLaterPages=_encabezado,
            canvasmaker=NumberedCanvas
        )

        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes
