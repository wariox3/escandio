from num2words import num2words
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.barcode.qr import QrCodeWidget
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from datetime import datetime
from decimal import Decimal
import re
import math
import json

def convertir_a_letras(numero):
    if numero == 0:
        return "Cero pesos"
    
    if numero < 0 or numero >= 1000000000:
        return "Número fuera de rango"
    
    palabras = num2words(numero, lang='es').title()
    
    # Reemplazar "Y Un" por "Y Unos" cuando corresponda
    palabras = palabras.replace("Y Un ", "Y Unos ")
    
    # Agregar "Pesos" al final
    palabras += " Pesos"
    
    return palabras.upper()

def generar_qr(data):
    qr_code = QrCodeWidget(data)
    d = Drawing(45, 45)
    d.add(qr_code)
    return d

class Utilidades:

    @staticmethod
    def rellenar(cadena, largo, caracter, direccion = "I"):
        if cadena is None:
            cadena = ""
        if not isinstance(cadena, str):
            cadena = str(cadena)
            
        if not cadena:
            cadena = ""
        longitud = len(cadena)
        if longitud < largo:
            if direccion == "I":
                cadena = caracter * (largo - longitud) + cadena
            else:
                cadena = cadena + caracter * (largo - longitud)
        else:
            cadena = cadena[:largo]        
        return cadena    
        
    @staticmethod
    def eliminar_caracteres_especiales(cadena):
        return re.sub(r'[^a-zA-Z0-9\s]', '', cadena)  
             
    @staticmethod
    def correo_valido(correo):
        try:
            validate_email(correo)
            return True
        except ValidationError:
            return False    
        
    @staticmethod
    def dias_prestacionales(fecha_inicio, fecha_fin):
        """
        Calcula el número de días entre dos fechas suponiendo meses de 30 días,
        con un ajuste especial para febrero.

        :param fecha_inicio: Fecha inicial en formato 'YYYY-MM-DD'.
        :param fecha_fin: Fecha final en formato 'YYYY-MM-DD'.
        :return: Número de días entre las dos fechas, con meses de 30 días y ajuste para febrero.
        """
        # Convertimos las fechas en objetos datetime
        inicio = datetime.strptime(fecha_inicio, "%Y-%m-%d")
        fin = datetime.strptime(fecha_fin, "%Y-%m-%d")
        
        # Calculamos las diferencias de años, meses y días
        años = fin.year - inicio.year
        meses = fin.month - inicio.month
        dias = fin.day - inicio.day

        # Totalizamos los meses y los días
        total_meses = años * 12 + meses
        total_dias = total_meses * 30 + dias

        # Ajuste para febrero
        if fin.month == 2:
            if fin.day == 28:
                total_dias += 2  
            elif fin.day == 29:
                total_dias += 1 

        # Sumamos 1 día adicional
        total_dias += 1

        return total_dias
    
    @staticmethod
    def digito_verificacion(nit):
        factores = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]        
        rut_ajustado=str(nit).rjust( 15, '0')
        s = sum(int(rut_ajustado[14-i]) * factores[i] for i in range(14)) % 11
        if s > 1:
            return 11 - s
        else:
            return s 

    @staticmethod
    def pdf_texto(texto, caracteres=None):
        if isinstance(texto, int):
            texto = str(texto)

        if not texto or len(texto.strip()) == 0:
            texto = ""

        if caracteres is not None and len(texto) > caracteres:
            texto = texto[:caracteres]
        return texto
    
    @staticmethod
    def separar_base64(base64_string):        
        if ';base64,' in base64_string:
            metadata, base64_data = base64_string.split(';base64,')            
            content_type = metadata.split(':')[1]            
            extension = content_type.split('/')[1]
            return {
                'content_type': content_type,
                'extension': extension,
                'base64_raw': base64_data
            }
        else:
            raise ValueError("La cadena base64 no contiene el formato esperado 'data:[tipo]/[extensión];base64,'.")
        
    @staticmethod
    def redondear_cien(valor):
        valor = math.ceil(valor / 100) * 100
        return valor    
    
    @staticmethod
    def obtener_valor_formateado(valor):
        """ Convierte un valor numérico a entero sin redondeo incorrecto """
        try:
            return int(format(float(valor), ".0f"))
        except (ValueError, TypeError):
            return 0 
        

class UtilidadGeneral:

    @staticmethod
    def transformar_decimal(obj):
        if isinstance(obj, dict):            
            return {key: UtilidadGeneral.transformar_decimal(value) 
                for key, value in obj.items()}
        elif isinstance(obj, (list, tuple)):            
            return type(obj)(UtilidadGeneral.transformar_decimal(item) 
                for item in obj)
        elif isinstance(obj, Decimal):
            return str(obj)
        else:            
            return obj            
        
    @staticmethod
    def json_texto(texto):
        if not texto or not texto.strip():
            return None        
        try:
            datos = json.loads(texto)
            return datos if isinstance(datos, dict) else None
        except (json.JSONDecodeError, ValueError):
            return None