from flask import Flask, request, Response
import openai
import os
import requests
import time

app = Flask(__name__)

# === ENVIRONMENT KEYS ===
openai.api_key = os.environ.get("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
VOICE_ID_DE = os.environ.get("VOICE_ID_DE")
VOICE_ID_EN = os.environ.get("VOICE_ID_EN")

# === FIX: set correct headers for audio ===
@app.after_request
def add_header(response):
    if response.mimetype == "audio/mpeg":
        response.headers["Content-Type"] = "audio/mpeg"
    return response


# === GENERATE VOICE ===
def generate_voice(text, voice_id):
    """Erstellt Sprachdatei mit ElevenLabs und speichert sie in /static"""
    os.makedirs("static", exist_ok=True)
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY,
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.55, "similarity_boost": 0.85},
    }

    r = requests.post(url, headers=headers, json=payload)
    path = os.path.join("static", "response.mp3")
    with open(path, "wb") as f:
        f.write(r.content)

    # Warte bis Datei wirklich fertig ist (damit Twilio sie finden kann)
    for _ in range(10):  # bis zu 10 Sekunden prüfen
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            break
        time.sleep(1)

    return path


# === TWILIO ROUTE ===
@app.route("/twilio-ai", methods=["POST"])
def twilio_ai():
    digits = request.form.get("Digits")
    speech = request.form.get("SpeechResult", "").strip()

    # --- Menü ---
    if not digits and not speech:
        menu = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="dtmf" numDigits="1" timeout="5" action="/twilio-ai">
        <Say language="de-DE">Willkommen. Für Deutsch drücken Sie 1.</Say>
        <Pause length="2"/>
        <Say language="en-US">For English, press 2.</Say>
    </Gather>
    <Say>Kein Input erkannt. Auf Wiedersehen!</Say>
</Response>"""
        return Response(menu, mimetype="text/xml")

    # --- Deutsch (1) ---
    if digits == "1":
        greeting = "Willkommen bei SMA Voice AI. Wie kann ich Ihnen helfen?"
        voice_id = VOICE_ID_DE

    # --- Englisch (2) ---
    elif digits == "2":
        greeting = "Welcome to SMA Voice AI. How can I assist you today?"
        voice_id = VOICE_ID_EN

    else:
        response = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Ungültige Eingabe. Bitte versuchen Sie es erneut.</Say>
</Response>"""
        return Response(response, mimetype="text/xml")

    # === Audio generieren ===
    path = generate_voice(greeting, voice_id)
    time.sleep(3)  # kleine Pause

    audio_url = f"{request.url_root}static/response.mp3".replace("http://", "https://")
    response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>{audio_url}</Play>
</Response>"""
    return Response(response, mimetype="text/xml")


# === MAIN RUN ===
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)




   











