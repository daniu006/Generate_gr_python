import cv2
import requests
import json
import time
from datetime import datetime
import pygame
import threading
from typing import Optional, Dict, Any, List
import logging
from dataclasses import dataclass

# ============= CONFIGURACIÓN =============
API_BASE_URL = "http://127.0.0.1:8000"  # Cambia por tu URL de API
CAMERA_INDEX = 1  # Índice de la cámara (0 para cámara principal)

# Configuración de sonidos
SOUND_SUCCESS = "success.wav"  # Archivo de sonido para éxito
SOUND_ERROR = "error.wav"      # Archivo de sonido para error
SOUND_WARNING = "warning.wav"  # Archivo de sonido para advertencias

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('qr_scanner.log'),
        logging.StreamHandler()
    ]
)

@dataclass
class TokenValidation:
    """Clase para manejar la respuesta de validación de tokens"""
    valid: bool
    message: str
    token_data: Optional[Dict[str, Any]] = None
    warnings: list = None
    estado: str = ""
    # Add new fields for attendance
    first_scan: Optional[bool] = None
    previous_scans: Optional[List[str]] = None

class QRScanner:
    def __init__(self):
        self.cap = None
        self.detector = cv2.QRCodeDetector()
        self.last_scanned_token = ""
        self.last_scan_time = 0
        self.scan_cooldown = 3  # Segundos entre escaneos del mismo token
        self.sound_enabled = True
        self.running = False
        self.current_display_validation = None # Stores the validation for display
        self.info_display_time = 0
        self.info_duration = 5 # Seconds to display information
        
        # Inicializar pygame para sonidos
        try:
            pygame.mixer.init()
            logging.info("Sistema de sonido inicializado")
        except Exception as e:
            logging.warning(f"No se pudo inicializar el sistema de sonido: {e}")
            self.sound_enabled = False
    
    def play_sound(self, sound_type: str):
        """Reproduce sonidos según el resultado de la validación"""
        if not self.sound_enabled:
            return
        
        try:
            sound_files = {
                "success": SOUND_SUCCESS,
                "error": SOUND_ERROR,
                "warning": SOUND_WARNING
            }
            
            sound_file = sound_files.get(sound_type)
            if sound_file:
                pygame.mixer.music.load(sound_file)
                pygame.mixer.music.play()
        except Exception as e:
            logging.warning(f"Error reproduciendo sonido {sound_type}: {e}")
    
    def validate_token_api(self, token: str) -> TokenValidation:
        """Valida el token usando la API mejorada"""
        try:
            url = f"{API_BASE_URL}/tokens/{token}/validate"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                validation = TokenValidation(
                    valid=data.get("valid", False),
                    message=data.get("message", ""),
                    token_data=data.get("token_data"),
                    warnings=data.get("warnings", []),
                    first_scan=data.get("first_scan", False),
                    previous_scans=data.get("previous_scans", [])
                )
                
                if validation.token_data:
                    validation.estado = validation.token_data.get("estado", "")
                
                return validation
                
            else:
                logging.error(f"Error en API: Status {response.status_code}")
                return TokenValidation(
                    valid=False,
                    message=f"Error de API: {response.status_code}",
                    estado="ERROR"
                )
                
        except requests.exceptions.Timeout:
            logging.error("Timeout conectando con la API")
            return TokenValidation(
                valid=False,
                message="Timeout: No se pudo conectar con el servidor",
                estado="ERROR"
            )
        except requests.exceptions.ConnectionError:
            logging.error("Error de conexión con la API")
            return TokenValidation(
                valid=False,
                message="Error: No se pudo conectar con el servidor",
                estado="ERROR"
            )
        except Exception as e:
            logging.error(f"Error validando token: {e}")
            return TokenValidation(
                valid=False,
                message=f"Error inesperado: {str(e)}",
                estado="ERROR"
            )
    
    def record_scan_api(self, token: str) -> dict:
        """Marca el token como usado en la API, registrando la asistencia"""
        try:
            url = f"{API_BASE_URL}/tokens/{token}/record_scan"
            response = requests.post(url, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            else:
                logging.error(f"Error registrando escaneo: Status {response.status_code} - {response.text}")
                return {"success": False, "message": f"Error API: {response.status_code}"}
                
        except Exception as e:
            logging.error(f"Error registrando escaneo: {e}")
            return {"success": False, "message": f"Error: {str(e)}"}
    
    def get_display_color(self, validation: TokenValidation) -> tuple:
        """Obtiene el color para mostrar según el estado del token"""
        if validation.estado == "ACTIVO":
            if validation.warnings:
                return (0, 255, 255)  # Amarillo para advertencias
            return (0, 255, 0)  # Verde para válido
        elif validation.estado == "EXPIRADO":
            return (0, 0, 255)  # Rojo para expirado
        elif validation.estado == "INACTIVO_O_NO_EXISTE":
            return (0, 0, 255) # Rojo
        else:
            return (0, 0, 255)  # Rojo para error o estados desconocidos
    
    def format_token_info(self, validation: TokenValidation) -> list:
        """Formatea la información del token para mostrar"""
        info_lines = []
        
        info_lines.append(f"Estado: {validation.estado}")
        info_lines.append(f"Mensaje: {validation.message}")
        
        if validation.token_data:
            data = validation.token_data
            
            info_lines.append(f"Empleado ID: {data.get('empleado_id', 'N/A')}")
            info_lines.append(f"Tipo: {data.get('tipo_token', 'N/A')}")
            
            # Show first scan time if available
            if data.get('usado_en'):
                try:
                    usado_en = datetime.fromisoformat(data['usado_en'].replace('Z', '+00:00'))
                    info_lines.append(f"Primer Escaneo: {usado_en.strftime('%d/%m/%Y %H:%M:%S')}")
                except:
                    info_lines.append(f"Primer Escaneo: {data['usado_en']}")
            
            # Show all previous scan times
            if validation.previous_scans:
                info_lines.append("Escaneos Previos:")
                for scan_time_str in validation.previous_scans:
                    try:
                        scan_dt = datetime.fromisoformat(scan_time_str.replace('Z', '+00:00'))
                        info_lines.append(f"  - {scan_dt.strftime('%d/%m/%Y %H:%M:%S')}")
                    except:
                        info_lines.append(f"  - {scan_time_str}")
            
            if data.get('departamento'):
                info_lines.append(f"Departamento: {data['departamento']}")
            
            if data.get('permisos_especiales'):
                info_lines.append(f"Permisos: {data['permisos_especiales']}")
            
            if data.get('expira_en'):
                try:
                    expira_en = datetime.fromisoformat(data['expira_en'].replace('Z', '+00:00'))
                    info_lines.append(f"Expira: {expira_en.strftime('%d/%m/%Y %H:%M')}")
                except:
                    info_lines.append(f"Expira: {data['expira_en']}")
        
        return info_lines
    
    def process_token(self, token: str) -> Optional[TokenValidation]:
        """Procesa un token escaneado"""
        current_time = time.time()
        
        # Verificar cooldown para evitar múltiples escaneos rápidos del MISMO token
        if (token == self.last_scanned_token and 
            current_time - self.last_scan_time < self.scan_cooldown):
            # If still in cooldown for the same token, don't re-process or update display
            return None # Do not update current_display_validation
        
        self.last_scanned_token = token
        self.last_scan_time = current_time
        
        logging.info(f"Token escaneado: {token[:8]}...")
        
        # 1. First, record the scan for attendance
        scan_record_result = self.record_scan_api(token)
        
        if not scan_record_result.get("success"):
            logging.error(f"Error al registrar escaneo: {scan_record_result.get('message')}")
            self.play_sound("error")
            return TokenValidation(
                valid=False,
                message=scan_record_result.get('message', "Error al registrar asistencia"),
                estado="ERROR_ASISTENCIA",
                first_scan=False, # Not a successful first scan
                previous_scans=[]
            )

        # 2. Then, validate the token to get its full status and previous scan times
        validation = self.validate_token_api(token)

        if validation.valid:
            # Check if it was truly the first scan based on the API's response
            if scan_record_result.get("is_first_scan"):
                logging.info(f"Primera asistencia registrada para {token[:8]}...")
                self.play_sound("success")
                validation.message = f"Primer registro de asistencia: {datetime.now().strftime('%H:%M:%S')}"
            else:
                logging.info(f"Asistencia adicional registrada para {token[:8]}...")
                self.play_sound("warning") # Or a specific sound for subsequent scans
                validation.message = f"Registro de asistencia adicional: {datetime.now().strftime('%H:%M:%S')}"
            validation.estado = "ASISTENCIA_REGISTRADA" # Custom status for display

        else: # Token is invalid (expired, inactive, etc.)
            self.play_sound("error")
            # The message and state are already set by validate_token_api

        logging.info(f"Resultado final: {validation.estado} - {validation.message}")
        
        return validation
    
    def initialize_camera(self) -> bool:
        """Inicializa la cámara"""
        try:
            self.cap = cv2.VideoCapture(CAMERA_INDEX)
            
            if not self.cap.isOpened():
                logging.error(f"No se pudo abrir la cámara {CAMERA_INDEX}")
                return False
            
            # Configurar resolución para mejor rendimiento
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.cap.set(cv2.CAP_PROP_FPS, 30)
            
            logging.info("Cámara inicializada correctamente")
            return True
            
        except Exception as e:
            logging.error(f"Error inicializando cámara: {e}")
            return False
    
    def run(self):
        """Ejecuta el bucle principal del escáner"""
        if not self.initialize_camera():
            print("Error: No se pudo inicializar la cámara")
            return
        
        self.running = True
        print("Escáner QR iniciado. Presiona 'q' para salir, 's' para alternar sonido")
        print("=== Control de Asistencia de Empleados ===")
        print("- Registra la hora del primer escaneo.")
        print("- Guarda la hora de cada escaneo posterior.")
        print("- Ideal para control de entradas y salidas.")
        print("==========================================")
        
        try:
            while self.running:
                ret, frame = self.cap.read()
                
                if not ret:
                    logging.error("Error capturando frame de la cámara")
                    break
                
                # Detectar códigos QR
                data, bbox, _ = self.detector.detectAndDecode(frame)
                
                if data:
                    # Process the token and update display validation if new
                    new_validation = self.process_token(data)
                    if new_validation: # Only update if it's not a cooldown bypass
                        self.current_display_validation = new_validation
                        self.info_display_time = time.time()
                
                # Dibujar el bbox si se detectó un QR
                if bbox is not None:
                    bbox = bbox.astype(int)
                    cv2.polylines(frame, [bbox], True, (255, 0, 255), 2)
                
                # Mostrar información del último token validado
                if (self.current_display_validation and 
                    time.time() - self.info_display_time < self.info_duration):
                    
                    color = self.get_display_color(self.current_display_validation)
                    info_lines = self.format_token_info(self.current_display_validation)
                    
                    # Fondo semi-transparente para mejor legibilidad
                    overlay = frame.copy()
                    cv2.rectangle(overlay, (10, 10), (450, 25 + len(info_lines) * 25), (0, 0, 0), -1)
                    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
                    
                    # Mostrar información línea por línea
                    for i, line in enumerate(info_lines):
                        y_pos = 30 + i * 25
                        cv2.putText(frame, line, (15, y_pos), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                
                # Mostrar instrucciones
                cv2.putText(frame, "Escaner QR - Control de Asistencia", (10, frame.shape[0] - 60), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                cv2.putText(frame, "Presiona 'q' para salir, 's' para sonido", (10, frame.shape[0] - 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                
                # Mostrar estado del sonido
                sound_status = "ON" if self.sound_enabled else "OFF"
                cv2.putText(frame, f"Sonido: {sound_status}", (frame.shape[1] - 120, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0) if self.sound_enabled else (0, 0, 255), 2)
                
                cv2.imshow('Escáner QR - Control de Asistencia', frame)
                
                # Manejar teclas
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('s'):
                    self.sound_enabled = not self.sound_enabled
                    print(f"Sonido {'activado' if self.sound_enabled else 'desactivado'}")
                    logging.info(f"Sonido {'activado' if self.sound_enabled else 'desactivado'}")
        
        except KeyboardInterrupt:
            logging.info("Escáner interrumpido por el usuario")
        except Exception as e:
            logging.error(f"Error en el bucle principal: {e}")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Limpia los recursos"""
        self.running = False
        
        if self.cap:
            self.cap.release()
        
        cv2.destroyAllWindows()
        
        if self.sound_enabled:
            pygame.mixer.quit()
        
        logging.info("Escáner cerrado correctamente")

def check_api_connection():
    """Verifica la conexión con la API"""
    try:
        response = requests.get(f"{API_BASE_URL}/info", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Conectado a: {data.get('app', 'QR Token API')}")
            print(f"📊 Versión: {data.get('version', 'N/A')}")
            
            if 'attendance_stats' in data:
                stats = data['attendance_stats']
                print(f"📈 Total de registros de asistencia: {stats.get('total_scans', 0)}")
            
            return True
        else:
            print(f"❌ Error de API: Status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error conectando con la API: {e}")
        print("Verifica que la API esté ejecutándose en:", API_BASE_URL)
        return False

def main():
    """Función principal"""
    print("=== Escáner QR - Sistema de Control de Asistencia ===")
    print("Verificando conexión con la API...")
    
    if not check_api_connection():
        print("\n⚠️  No se pudo conectar con la API.")
        print("   Asegúrate de que la API esté ejecutándose.")
        print(f"   URL: {API_BASE_URL}")
        return
    
    print("\n🚀 Iniciando escáner...")
    scanner = QRScanner()
    scanner.run()

if __name__ == "__main__":
    main()