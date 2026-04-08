from flask import Flask, render_template, Response, jsonify
import cv2
import numpy as np
import threading
import time
import base64
import logging
from os import environ
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

MIN_CONTOUR_AREA = 500
COOLDOWN = 15.0
MODEL_NAME = "meta-llama/llama-4-scout-17b-16e-instruct"

# --- Groq ---
try:
    from groq import Groq
    groq_client = Groq(api_key=environ.get("GROQ_API_KEY"))
    GROQ_AVAILABLE = True
except Exception:
    groq_client = None
    GROQ_AVAILABLE = False

logging.basicConfig(level=logging.INFO)


class MotionDetector:
    def __init__(self):
        self.camera = cv2.VideoCapture(0)
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(detectShadows=True)
        self.last_detection = 0
        self.motion_events = []  # lista de dicts
        self.movement_count = 0
        self.frame_dims = (640, 480)
        self.lock = threading.RLock()

    def detect_motion(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (9, 9), 0)
        fg_mask = self.bg_subtractor.apply(gray)
        _, fg_mask = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=2)
        fg_mask = cv2.dilate(fg_mask, np.ones((7, 7), np.uint8), iterations=3)

        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        motion_regions = []
        for contour in contours:
            if cv2.contourArea(contour) > MIN_CONTOUR_AREA:
                x, y, w, h = cv2.boundingRect(contour)
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(frame, "MOVIMENTO DETECTADO", (x, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                area = w * h
                cx, cy = x + w // 2, y + h // 2
                px = "esquerda" if cx < 213 else ("direita" if cx > 427 else "centro")
                py = "superior" if cy < 160 else ("inferior" if cy > 320 else "meio")
                motion_regions.append({
                    "posicao": f"{py}-{px}",
                    "tamanho": "grande" if area > 50000 else ("medio" if area > 10000 else "pequeno"),
                    "largura": w,
                    "altura": h
                })

        if motion_regions:
            fh, fw = frame.shape[:2]
            dados = f"Frame: {fw}x{fh}. {len(motion_regions)} regiao(oes): "
            for i, r in enumerate(motion_regions):
                dados += f"R{i+1}: [{r['posicao']}] tam={r['tamanho']} ({r['largura']}x{r['altura']}px). "
            return True, dados, frame.copy()

        return False, None, frame.copy()

    def query_groq(self, frame):
        if not GROQ_AVAILABLE or groq_client is None:
            return {"error": "Groq nao configurado"}

        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
        frame_b64 = base64.b64encode(buffer).decode()

        messages = [
            {
                "role": "system",
                "content": (
                    "Você analisa imagens de câmera de segurança. "
                    "Descreva EXATAMENTE o que está vendo: gestos, ações, movimentos. "
                    "Se alguem faz joinha, tchau, levanta a mao - descreva. "
                    "Seja objetivo e direto. Maximo 2 frases."
                )
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{frame_b64}",
                            "detail": "low"
                        }
                    },
                    {
                        "type": "text",
                        "text": "Descreva exatamente o que ve nesta imagem. Que gestos, acoes ou movimentos estao acontecendo?"
                    }
                ]
            }
        ]

        for attempt in range(3):
            try:
                resp = groq_client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=messages,
                    max_tokens=80,
                    temperature=0.7
                )
                return {
                    "analysis": resp.choices[0].message.content,
                    "timestamp": time.strftime("%H:%M:%S")
                }
            except Exception as e:
                err = str(e)
                if "rate_limit" in err.lower() and attempt < 2:
                    wait = (attempt + 1) * 3
                    time.sleep(wait)
                    continue
                return {"error": err[:200]}

    def stream_generator(self):
        while True:
            ret, frame = self.camera.read()
            if not ret:
                continue

            resized = cv2.resize(frame, self.frame_dims)
            motion_detected, motion_data, crop_frame = self.detect_motion(resized)

            if motion_detected:
                now = time.time()
                if now - self.last_detection >= COOLDOWN:
                    self.last_detection = now
                    self.movement_count += 1

                    # Crop the frame to only the moving regions for better AI vision
                    ai_frame = crop_frame.copy()

                    event = {
                        "count": self.movement_count,
                        "timestamp": time.strftime("%H:%M:%S"),
                        "status": "analyzing..."
                    }

                    logging.info(f"[IA] Analisando evento #{self.movement_count}...")
                    result = self.query_groq(ai_frame)
                    logging.info(f"[IA] Resultado evento #{self.movement_count}: {result}")

                    event.update(result)
                    event.pop("status", None)

                    with self.lock:
                        self.motion_events.insert(0, event)
                        self.motion_events = self.motion_events[:50]

            cv2.putText(resized, f"Detecções: {self.movement_count}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            ret1, jpeg = cv2.imencode('.jpg', resized)
            if ret1:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n'
                       + jpeg.tobytes() + b'\r\n')

    def get_events(self):
        with self.lock:
            return list(self.motion_events)


detector = MotionDetector()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/video_feed')
def video_feed():
    return Response(
        detector.stream_generator(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@app.route('/events')
def events():
    return jsonify(detector.get_events())


@app.route('/groq-status')
def groq_status():
    return jsonify({
        "available": GROQ_AVAILABLE,
        "model": MODEL_NAME if GROQ_AVAILABLE else None
    })


if __name__ == '__main__':
    print("=" * 50)
    print("  iaCAM - Detector de Movimento com IA")
    print("=" * 50)
    print(f"  Groq IA: {'Ativa' if GROQ_AVAILABLE else 'Desativada'}")
    print(f"  Modelo: {MODEL_NAME}")
    print("  Acessar: http://localhost:5000")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
