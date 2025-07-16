import cv2
from pyzbar import pyzbar
from pyzbar.pyzbar import decode, ZBarSymbol

def es_codigo_rechazado(data):
    if data.strip().upper().startswith("WIFI:"):
        return True
    
    extensiones_imagen = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
    for ext in extensiones_imagen:
        if ext in data.lower():
            return True
    return False

cap = cv2.VideoCapture(0)
print("📷 Escaneando códigos QR... Presiona ESC para salir.")

while True:
    ret, frame = cap.read()
    if not ret:
        continue

    for qr in decode(frame, symbols=[ZBarSymbol.QRCODE]):
        data = qr.data.decode('utf-8')
        print(f"Código detectado: {data}")

        if es_codigo_rechazado(data):
            print("❌ Código RECHAZADO (WiFi o imagen detectada)")
        else:
            print("✅ Código ACEPTADO")

    cv2.imshow('Lector QR', frame)

    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()
print("Programa finalizado.")
