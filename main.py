from flask import Flask, request, Response
import openai
import requests
import os
import time

app = Flask(__name__)

# Keys aus Umgebungsvariablen
openai.api_key = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# Voice IDs (dein Daniel Voice)
VOICE_ID_DE = "sQTJeoiy67ha6Wmrl162"  # Deutsch
VOICE_ID_EN = "ZoiZ8fuDWInAcwPXaVeq"  # Englisch

# === Funktion: Stimme generieren ===
def generate_voice(text, voice_id):
    """Erstellt Sprachdatei mit ElevenLabs und speichert sie in /static"""
    os.makedirs("static", exist_ok=True)
    file_path = os.path.join("static", "response.mp3")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.55, "similarity_boost": 0.85}
    }

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code == 200:
        with open(file_path, "wb") as f:
            f.write(response.content)
            f.flush()
            os.fsync(f.fileno())
        time.sleep(3)  # wartet, bis Datei wirklich fertig gespeichert ist
        return file_path
    else:
        print("Fehler bei ElevenLabs:", response.text)
        return None


# === Haupt-Route für Twilio ===
@app.route("/twilio-ai", methods=["POST"])
def twilio_ai():
    data = request.form
    digits = data.get("Digits")

    # Falls kein Input (erster Anruf)
    if not digits:
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="dtmf" numDigits="1" timeout="5" action="/twilio-ai">
        <Say language="de-DE">Hallo. Für Deutsch drücken Sie die 1.</Say>
        <Pause length="1"/>
        <Say language="en-US">For English, press 2.</Say>
    </Gather>
    <Say>Kein Input erkannt. Auf Wiedersehen!</Say>
</Response>"""
        return Response(twiml, mimetype="text/xml")

    # === Deutsch (Taste 1) ===
    if digits == "1":
        text = "Willkommen im Restaurant Viadukt. Wie kann ich Ihnen helfen?"
        path = generate_voice(text, VOICE_ID_DE)

    # === Englisch (Taste 2) ===
    elif digits == "2":
        text = "Welcome to Restaurant Viadukt. How can I assist you today?"
        path = generate_voice(text, VOICE_ID_EN)

    else:
        path = None

    # === Twilio antwortet mit Play ===
    if path:
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>https://smavoiceai.onrender.com/{path}</Play>
</Response>"""
    else:
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Ein Fehler ist aufgetreten. Bitte versuchen Sie es später erneut.</Say>
</Response>"""

    return Response(twiml, mimetype="text/xml")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)






   











