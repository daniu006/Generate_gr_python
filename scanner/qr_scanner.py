import cv2
from pyzbar import pyzbar
from pyzbar.pyzbar import decode, ZBarSymbol
import serial
import time
import requests
import sqlite3
from datetime import datetime
import json

# ============= CONFIGURACIÓN =============
puerto_serial = 'COM5'
baud_rate = 115200
API_BASE_URL = 'http://127.0.0.1:8000/docs'  # Cambia por tu URL de FastAPI

# ============= CONFIGURACIÓN BASE DE DATOS LOCAL =============
def inicializar_db_local():
    """Crea la base de datos local para logs si no existe"""
    conn = sqlite3.connect('access_logs.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS access_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            token_data TEXT NOT NULL,
            validation_result TEXT NOT NULL,
            access_granted BOOLEAN NOT NULL,
            response_data TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def guardar_log_acceso(token_data, validation_result, access_granted, response_data=None):
    """Guarda un log de acceso en la base de datos local"""
    conn = sqlite3.connect('access_logs.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO access_logs (timestamp, token_data, validation_result, access_granted, response_data)
        VALUES (?, ?, ?, ?, ?)
    ''', (
        datetime.now().isoformat(),
        token_data,
        validation_result,
        access_granted,
        json.dumps(response_data) if response_data else None
    ))
    conn.commit()
    conn.close()

# ============= FUNCIONES DE VALIDACIÓN =============
def es_codigo_rechazado(data):
    """Validación local: rechaza códigos WiFi e imágenes"""
    if data.strip().upper().startswith("WIFI:"):
        return True
    
    extensiones_imagen = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
    for ext in extensiones_imagen:
        if ext in data.lower():
            return True
    return False

def validar_token_con_api(token):
    """Valida el token con la API FastAPI"""
    try:
        response = requests.get(f"{API_BASE_URL}/tokens/{token}/validate", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get('valid', False), data
        else:
            return False, {"error": f"HTTP {response.status_code}"}
    except requests.exceptions.RequestException as e:
        return False, {"error": f"Error de conexión: {str(e)}"}

def procesar_codigo_qr(data):
    """Procesa el código QR detectado"""
    print(f"📱 Código detectado: {data}")
    
    # Validación local primero
    if es_codigo_rechazado(data):
        print("❌ Código RECHAZADO (WiFi o imagen detectada)")
        guardar_log_acceso(
            token_data=data,
            validation_result="RECHAZADO_LOCAL",
            access_granted=False,
            response_data={"reason": "WiFi o imagen detectada"}
        )
        return False, "Código rechazado localmente"
    
    # Validación remota con API
    print("🔍 Validando con API...")
    is_valid, api_response = validar_token_con_api(data)
    
    if is_valid:
        print("✅ Token VÁLIDO - Acceso permitido")
        guardar_log_acceso(
            token_data=data,
            validation_result="ACEPTADO",
            access_granted=True,
            response_data=api_response
        )
        return True, "Token válido"
    else:
        print(f"❌ Token INVÁLIDO - {api_response.get('message', 'Error desconocido')}")
        guardar_log_acceso(
            token_data=data,
            validation_result="RECHAZADO_API",
            access_granted=False,
            response_data=api_response
        )
        return False, api_response.get('message', 'Token inválido')

# ============= CONFIGURACIÓN SERIAL =============
def conectar_esp32():
    """Conecta con el ESP32"""
    try:
        esp32 = serial.Serial(puerto_serial, baud_rate)
        time.sleep(2)
        print(f"✅ Conectado a ESP32 en {puerto_serial}")
        return esp32
    except Exception as e:
        print(f"❌ ERROR: No se pudo conectar a {puerto_serial}: {e}")
        return None

def enviar_resultado_esp32(esp32, acceso_concedido):
    """Envía el resultado al ESP32"""
    if esp32:
        try:
            comando = b'1' if acceso_concedido else b'0'
            esp32.write(comando)
            print(f"📡 Enviado al ESP32: {'1 (ACCESO)' if acceso_concedido else '0 (RECHAZADO)'}")
        except Exception as e:
            print(f"❌ Error enviando al ESP32: {e}")

# ============= FUNCIÓN PRINCIPAL =============
def main():
    """Función principal del escáner QR"""
    print("🚀 Iniciando sistema de validación QR...")
    
    # Inicializar base de datos local
    inicializar_db_local()
    print("📊 Base de datos local inicializada")
    
    # Conectar ESP32
    esp32 = conectar_esp32()
    if not esp32:
        print("⚠️ Continuando sin ESP32...")
    
    # Inicializar cámara
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ ERROR: No se pudo acceder a la cámara")
        return
    
    print("📷 Cámara inicializada")
    print("🔍 Escaneando códigos QR... Presiona ESC para salir.")
    print("-" * 50)
    
    ultimo_codigo = ""
    ultimo_tiempo = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            continue
        
        # Detectar códigos QR
        codigos_qr = decode(frame, symbols=[ZBarSymbol.QRCODE])
        
        for qr in codigos_qr:
            data = qr.data.decode('utf-8')
            tiempo_actual = time.time()
            
            # Evitar procesar el mismo código repetidamente
            if data == ultimo_codigo and (tiempo_actual - ultimo_tiempo) < 3:
                continue
            
            ultimo_codigo = data
            ultimo_tiempo = tiempo_actual
            
            # Procesar el código QR
            acceso_concedido, mensaje = procesar_codigo_qr(data)
            
            # Enviar resultado al ESP32
            enviar_resultado_esp32(esp32, acceso_concedido)
            
            print(f"📝 Resultado: {mensaje}")
            print("-" * 50)
            
            # Pausa para evitar lecturas múltiples
            time.sleep(2)
        
        # Mostrar video
        cv2.imshow('📷 Lector QR - Sistema de Acceso', frame)
        
        # Salir con ESC
        if cv2.waitKey(1) & 0xFF == 27:
            break
    
    # Limpiar recursos
    cap.release()
    cv2.destroyAllWindows()
    if esp32:
        esp32.close()
    print("🔚 Programa finalizado.")

# ============= FUNCIONES AUXILIARES PARA CONSULTAR LOGS =============
def mostrar_logs_recientes(limite=10):
    """Muestra los logs más recientes"""
    conn = sqlite3.connect('access_logs.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT timestamp, token_data, validation_result, access_granted, response_data
        FROM access_logs 
        ORDER BY id DESC 
        LIMIT ?
    ''', (limite,))
    
    logs = cursor.fetchall()
    conn.close()
    
    print(f"\n📋 Últimos {len(logs)} registros de acceso:")
    print("-" * 80)
    for log in logs:
        timestamp, token, result, granted, response = log
        status = "✅ ACCESO" if granted else "❌ RECHAZADO"
        print(f"{timestamp} | {status} | {result} | Token: {token[:20]}...")
    print("-" * 80)

def obtener_estadisticas():
    """Obtiene estadísticas de acceso"""
    conn = sqlite3.connect('access_logs.db')
    cursor = conn.cursor()
    
    # Total de intentos
    cursor.execute('SELECT COUNT(*) FROM access_logs')
    total = cursor.fetchone()[0]
    
    # Accesos concedidos
    cursor.execute('SELECT COUNT(*) FROM access_logs WHERE access_granted = 1')
    concedidos = cursor.fetchone()[0]
    
    # Accesos rechazados
    cursor.execute('SELECT COUNT(*) FROM access_logs WHERE access_granted = 0')
    rechazados = cursor.fetchone()[0]
    
    conn.close()
    
    print(f"\n📊 Estadísticas de Acceso:")
    print(f"Total de intentos: {total}")
    print(f"Accesos concedidos: {concedidos}")
    print(f"Accesos rechazados: {rechazados}")
    if total > 0:
        print(f"Tasa de éxito: {(concedidos/total)*100:.1f}%")

# ============= PUNTO DE ENTRADA =============
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Programa interrumpido por el usuario")
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
    finally:
        # Mostrar estadísticas al finalizar
        try:
            obtener_estadisticas()
            mostrar_logs_recientes(5)
        except:
            pass