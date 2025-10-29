from flask import Flask, request, Response
import openai
import os
import requests
import time

app = Flask(__name__)

openai.api_key = os.environ.get("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")

VOICE_ID_DE = os.environ.get("VOICE_ID_DE")
VOICE_ID_EN = os.environ.get("VOICE_ID_EN")

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
    return path


@app.route("/twilio-ai", methods=["POST"])
def twilio_ai():
    digits = request.form.get("Digits")
    speech = request.form.get("SpeechResult")

    # Falls kein Sprach-Input kommt, wird speech leer gesetzt
    if not speech:
        speech = ""
    else:
        speech = speech.strip()

    # Menü-Logik (Sprachauswahl)
    if not digits and not speech:
        menu = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="dtmf" numDigits="1" timeout="10" action="/twilio-ai">
        <Say language="de-DE">Willkommen. Für Deutsch drücken Sie 1.</Say>
        <Pause length="1"/>
        <Say language="en-US">For English, press 2.</Say>
    </Gather>
    <Say>Kein Input erkannt. Auf Wiedersehen!</Say>
</Response>"""
        return Response(menu, mimetype="text/xml")

    # Sprachauswahl
    if digits == "1":
        greeting = "Willkommen bei SMA Voice AI. Wie kann ich Ihnen helfen?"
        voice_id = VOICE_ID_DE
    elif digits == "2":
        greeting = "Welcome to SMA Voice AI. How can I help you?"
        voice_id = VOICE_ID_EN
    else:
        greeting = "Ungültige Eingabe. Goodbye!"
        voice_id = VOICE_ID_DE

    # Generiere Audioantwort
    path = generate_voice(greeting, voice_id)
    time.sleep(3)  # kleine Pause, damit Datei bereit ist

    response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>{request.url_root}static/response.mp3</Play>
</Response>"""
    return Response(response, mimetype="text/xml")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)



   











