import cv2
from pyzbar import pyzbar
from pyzbar.pyzbar import decode, ZBarSymbol
import serial
import time

puerto_serial = 'COM5'
baud_rate = 115200

def es_codigo_rechazado(data):
    if data.strip().upper().startswith("WIFI:"):
        return True
    
    extensiones_imagen = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
    for ext in extensiones_imagen:
        if ext in data.lower():
            return True
    return False

try:
    esp32 = serial.Serial(puerto_serial, baud_rate)
    time.sleep(2)
    print(f"✅ Conectado a {puerto_serial}")
except:
    print(f"❌ ERROR: No se pudo conectar a {puerto_serial}")
    exit()

cap = cv2.VideoCapture(1)
print("Escaneando códigos QR... Presiona ESC para salir.")

while True:
    ret, frame = cap.read()
    if not ret:
        continue

    for qr in decode(frame, symbols=[ZBarSymbol.QRCODE]):
        data = qr.data.decode('utf-8')
        print(f"Código detectado: {data}")

        if es_codigo_rechazado(data):
            print("❌ Código RECHAZADO (WiFi o imagen detectada)")
            esp32.write(b'0')
            print("Enviado al ESP32: 0")
        else:
            print("✅ Código ACEPTADO")
            esp32.write(b'1')
            print("Enviado al ESP32: 1")

        time.sleep(2)

    cv2.imshow('Lector QR', frame)

    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()
esp32.close()
print("Programa finalizado.")
