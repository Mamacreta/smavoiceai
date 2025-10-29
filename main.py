from flask import Flask, request, Response
import openai
import os
import requests
import time

app = Flask(__name__)

openai.api_key = os.environ.get("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")

VOICE_ID_DE = "sQTJeoiy67ha6Wmrl162"  # Daniel Deutsch
VOICE_ID_EN = "ZoiZ8fuDWInAcwPXaVeq"  # Daniel English

# ----- Generate Voice -----
def generate_voice(text, voice_id):
    os.makedirs("static", exist_ok=True)
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
        file_path = "static/response.mp3"
        with open(file_path, "wb") as f:
            f.write(response.content)
        return file_path
    else:
        print("ElevenLabs error:", response.text)
        return None


# ----- Twilio AI -----
@app.route("/twilio-ai", methods=["POST"])
def twilio_ai():
    data = request.form
    digits = data.get("Digits")

    if not digits:
        # Sprachauswahl
        response = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="dtmf" numDigits="1" timeout="5" action="/twilio-ai">
        <Say language="de-DE">Hallo. Für Deutsch drücken Sie 1.</Say>
        <Pause length="2"/>
        <Say language="en-US">For English, press 2.</Say>
    </Gather>
    <Say>Kein Input erkannt. Auf Wiedersehen.</Say>
</Response>"""
        return Response(response, mimetype="text/xml")

    if digits == "1":
        text = "Willkommen im Restaurant Viadukt. Wie kann ich Ihnen helfen?"
        path = generate_voice(text, VOICE_ID_DE)
    elif digits == "2":
        text = "Welcome to Restaurant Viadukt. How can I help you today?"
        path = generate_voice(text, VOICE_ID_EN)
    else:
        text = "Ungültige Eingabe."
        path = generate_voice(text, VOICE_ID_DE)

    # Warten bis die Datei sicher gespeichert ist
    time.sleep(3)

    if path:
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>https://smavoiceai.onrender.com/{path}</Play>
</Response>"""
    else:
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Ein Fehler ist aufgetreten.</Say>
</Response>"""

    return Response(twiml, mimetype="text/xml")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)






   











