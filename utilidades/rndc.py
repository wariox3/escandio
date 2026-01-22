# app/utilidades/rndc.py
from zeep import Client
import xml.etree.ElementTree as ET
import re
from typing import Dict, Any, List, Optional
from django.conf import settings

class Rndc:
    def __init__(self):
        # self.url = "http://rndcws.mintransporte.gov.co:8080/ws/svr008w.dll/wsdl/IBPMServices"
        #self.url = "http://rndcws.mintransporte.gov.co:8080/wsdl/IBPMServices"
        # Url del ministerio para pruebas
        self.url = "http://plc.mintransporte.gov.co:8080/ws/svr008w.dll/wsdl/IBPMServices"
    
    def enviar(self, str_xml: str) -> Dict[str, Any]:
        try:
            if str_xml:
                # Validar XML
                xml_valido, errores_xml_envio = self._validar_xml(str_xml)
                if xml_valido:
                    cliente = Client(self.url)
                    respuesta = cliente.service.AtenderMensajeRNDC(str_xml)
                    
                    cadena_xml = ET.fromstring(respuesta)
                    error_msg = self._buscar_elemento(cadena_xml, 'ErrorMSG')
                    
                    if error_msg == "" or error_msg is None:
                        ingresoid = self._buscar_elemento(cadena_xml, 'ingresoid')
                        return {
                            'error': False,
                            'ingresoid': ingresoid
                        }
                    else:
                        return {
                            'error': True,
                            'errorMensaje': error_msg.encode('latin-1').decode('utf-8', errors='ignore')
                        }
                else:
                    mensaje_error = ""
                    if errores_xml_envio:
                        for error in errores_xml_envio:
                            mensaje_error += f"{error['message']} en la línea {error['line']}<br>"
                    
                    return {
                        'error': True,
                        'errorMensaje': f"El xml no es valido {mensaje_error}"
                    }
            else:
                return {
                    'error': True,
                    'errorMensaje': "El parametro xml esta vacio"
                }
                
        except Exception as e:
            return {
                'error': True,
                'errorMensaje': f"Ocurrio un error interno con el envio {str(e)}"
            }
    
    def enviar_consulta(self, str_xml: str) -> Dict[str, Any]:
        try:
            if str_xml:
                # Validar XML
                xml_valido, errores_xml_envio = self._validar_xml(str_xml)
                if xml_valido:
                    cliente = Client(self.url)
                    respuesta = cliente.service.AtenderMensajeRNDC(str_xml)
                    
                    # Limpiar respuesta (equivalente al preg_replace de PHP)
                    respuesta_limpia = re.sub(
                        r'\s*<\/puntocontrol>\s*<\/puntoscontrol>\s*<\/documento>\s*', 
                        '', 
                        respuesta
                    )
                    
                    cadena_xml = ET.fromstring(respuesta_limpia)
                    error_msg = self._buscar_elemento(cadena_xml, 'ErrorMSG')
                    
                    if error_msg == "" or error_msg is None:
                        return {
                            'error': False,
                            'cadena_xml': cadena_xml
                        }
                    else:
                        return {
                            'error': True,
                            'errorMensaje': error_msg.encode('latin-1').decode('utf-8', errors='ignore')
                        }
                else:
                    mensaje_error = ""
                    if errores_xml_envio:
                        for error in errores_xml_envio:
                            mensaje_error += f"{error['message']} en la línea {error['line']}<br>"
                    
                    return {
                        'error': True,
                        'errorMensaje': f"El xml no es valido {mensaje_error}"
                    }
            else:
                return {
                    'error': True,
                    'errorMensaje': "El parametro xml esta vacio"
                }
                
        except Exception as e:
            return {
                'error': True,
                'errorMensaje': f"Ocurrio un error interno con el envio {str(e)}"
            }
    
    def crear_xml(self, credencial: Dict, tipo: str, procesoid: str, 
                 propiedades: Dict, arr_guias: Optional[List] = None) -> str:
        # Crear documento DOM
        from xml.dom.minidom import Document
        doc = Document()
        
        # Elemento root
        root = doc.createElement('root')
        doc.appendChild(root)
        
        # Elemento acceso
        acceso = doc.createElement('acceso')
        
        if procesoid == "86":
            username = doc.createElement('username')
            username.appendChild(doc.createTextNode(credencial['usuarioFacturacion']))
            password = doc.createElement('password')
            password.appendChild(doc.createTextNode(credencial['claveFacturacion']))
        else:
            username = doc.createElement('username')
            username.appendChild(doc.createTextNode(credencial['tte_usuario_rndc'] or ''))
            password = doc.createElement('password')
            password.appendChild(doc.createTextNode(credencial['tte_clave_rndc'] or ''))
        
        acceso.appendChild(username)
        acceso.appendChild(password)
        root.appendChild(acceso)
        
        # Elemento solicitud
        solicitud = doc.createElement('solicitud')
        tipo_dom = doc.createElement('tipo')
        tipo_dom.appendChild(doc.createTextNode(tipo))
        proceso = doc.createElement('procesoid')
        proceso.appendChild(doc.createTextNode(procesoid))
        solicitud.appendChild(tipo_dom)
        solicitud.appendChild(proceso)
        root.appendChild(solicitud)
        
        if tipo == "1" or tipo == "6":
            if tipo == "6":
                variables = doc.createElement('documento')
            else:
                variables = doc.createElement('variables')
                nit_empresa = doc.createElement('NUMNITEMPRESATRANSPORTE')
                nit_empresa.appendChild(doc.createTextNode(credencial['empresa__numero_identificacion']))
                variables.appendChild(nit_empresa)
            
            for clave, valor in propiedades.items():
                if valor is None:
                    valor = ''
                nodo = doc.createElement(clave)
                nodo.appendChild(doc.createTextNode(str(valor)))
                variables.appendChild(nodo)
            
            if arr_guias:
                if procesoid == "4":
                    nodo = doc.createElement('REMESASMAN')
                    remesas = variables.appendChild(nodo)
                    remesas.setAttribute('procesoid', "43")
                    for guia in arr_guias:
                        nodo = doc.createElement("REMESA")
                        remesa = remesas.appendChild(nodo)
                        nodo = doc.createElement('CONSECUTIVOREMESA')
                        nodo.appendChild(doc.createTextNode(guia))
                        remesa.appendChild(nodo)
                
                if procesoid == "81":
                    nodo = doc.createElement('REMESAS')
                    remesas = variables.appendChild(nodo)
                    remesas.setAttribute('procesoid', "82")
                    for guia in arr_guias:
                        nodo = doc.createElement("REMESA")
                        remesa = remesas.appendChild(nodo)
                        nodo = doc.createElement('REMESAURBANA')
                        nodo.appendChild(doc.createTextNode(guia))
                        remesa.appendChild(nodo)
            
            root.appendChild(variables)
        else:
            variables = doc.createElement('variables')
            variables.appendChild(doc.createTextNode("INGRESOID"))
            root.appendChild(variables)
            
            documento = doc.createElement('documento')
            nit_empresa = doc.createElement('NUMNITEMPRESATRANSPORTE')
            nit_empresa.appendChild(doc.createTextNode(credencial['empresa__numero_identificacion']))
            documento.appendChild(nit_empresa)
            root.appendChild(documento)
        
        return doc.toprettyxml(indent="  ", encoding='ISO-8859-1').decode('ISO-8859-1')
    
    def crear_xml_consulta(self, credencial: Dict, tipo: str, procesoid: str, 
                          parametro_variables: str, arr_parametros_documento: Dict,
                          arr_parametros_documento_rangos: Optional[Dict] = None) -> str:
        # Crear documento DOM
        from xml.dom.minidom import Document
        doc = Document()
        
        # Elemento root
        root = doc.createElement('root')
        doc.appendChild(root)
        
        # Elemento acceso
        acceso = doc.createElement('acceso')
        username = doc.createElement('username')
        username.appendChild(doc.createTextNode(credencial['usuario']))
        password = doc.createElement('password')
        password.appendChild(doc.createTextNode(credencial['clave']))
        acceso.appendChild(username)
        acceso.appendChild(password)
        root.appendChild(acceso)
        
        # Elemento solicitud
        solicitud = doc.createElement('solicitud')
        tipo_elem = doc.createElement('tipo')
        tipo_elem.appendChild(doc.createTextNode(tipo))
        procesoid_elem = doc.createElement('procesoid')
        procesoid_elem.appendChild(doc.createTextNode(procesoid))
        solicitud.appendChild(tipo_elem)
        solicitud.appendChild(procesoid_elem)
        root.appendChild(solicitud)
        
        # Elemento variables
        variables = doc.createElement('variables')
        variables.appendChild(doc.createTextNode(parametro_variables))
        root.appendChild(variables)
        
        # Elemento documento
        documentos = doc.createElement('documento')
        nit_empresa = doc.createElement('NUMNITEMPRESATRANSPORTE')
        nit_empresa.appendChild(doc.createTextNode(credencial['nitEmpresa']))
        documentos.appendChild(nit_empresa)
        
        for clave, valor in arr_parametros_documento.items():
            nodo = doc.createElement(clave)
            nodo.appendChild(doc.createTextNode(str(valor)))
            documentos.appendChild(nodo)
        
        root.appendChild(documentos)
        
        # Elemento documentorango (opcional)
        if arr_parametros_documento_rangos:
            documento_rangos = doc.createElement('documentorango')
            for clave, valor in arr_parametros_documento_rangos.items():
                nodo = doc.createElement(clave)
                nodo.appendChild(doc.createTextNode(str(valor)))
                documento_rangos.appendChild(nodo)
            root.appendChild(documento_rangos)
        
        return doc.toprettyxml(indent="  ", encoding='ISO-8859-1').decode('ISO-8859-1')
    
    # ===== MÉTODOS PRIVADOS DE APOYO =====
    
    def _validar_xml(self, xml_string: str) -> tuple:
        """
        Valida XML similar a libxml_use_internal_errors de PHP
        Retorna: (es_valido, lista_errores)
        """
        try:
            ET.fromstring(xml_string)
            return True, []
        except ET.ParseError as e:
            error_info = {
                'message': str(e),
                'line': e.position[0] if hasattr(e, 'position') else 0
            }
            return False, [error_info]
    
    def _buscar_elemento(self, xml_element, tag_name: str) -> Optional[str]:
        """
        Busca un elemento en el XML similar a simplexml_load_string de PHP
        """
        try:
            element = xml_element.find(tag_name)
            if element is not None:
                return element.text or ""
            return None
        except:
            return None