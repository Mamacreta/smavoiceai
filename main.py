from flask import Flask, request, Response
import requests
import os
import time

app = Flask(__name__)

# --- API KEYS ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# --- VOICE IDs ---
VOICE_ID_EN = "ZoiZ8fuDWInAcwPXaVeq"   # Daniel English
VOICE_ID_DE = "sQTJeoiy67ha6Wmrl162"   # Daniel Deutsch

# --- Generate voice with ElevenLabs ---
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

    if response.status_code != 200:
        print("Voice generation failed:", response.text)
        return None

    audio_path = os.path.join("static", "response.mp3")
    with open(audio_path, "wb") as f:
        f.write(response.content)

    print("Voice generated and saved to:", audio_path)
    return "/static/response.mp3"


@app.route("/twilio-ai", methods=["POST"])
def twilio_ai():
    digits = request.form.get("Digits")

    # --- Step 1: Language selection ---
    if not digits:
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="dtmf" numDigits="1" timeout="5" action="/twilio-ai">
        <Say language="de-DE">Hallo. Für Deutsch drücken Sie 1.</Say>
        <Pause length="2"/>
        <Say language="en-US">Hello. For English, press 2.</Say>
    </Gather>
    <Say>Kein Input erkannt. Auf Wiedersehen!</Say>
</Response>"""
        return Response(twiml, mimetype="text/xml")

    # --- Step 2: German version ---
    elif digits == "1":
        text = "Willkommen beim Restaurant Viadukt Zürich. Wie kann ich Ihnen helfen?"
        file_path = generate_voice(text, VOICE_ID_DE)
        time.sleep(3)
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>https://smavoiceai.onrender.com{file_path}</Play>
</Response>"""
        print("Daniel (DE) played:", file_path)
        return Response(twiml, mimetype="text/xml")

    # --- Step 3: English version ---
    elif digits == "2":
        text = "Welcome to Restaurant Viadukt Zurich. How may I assist you today?"
        file_path = generate_voice(text, VOICE_ID_EN)
        time.sleep(3)
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>https://smavoiceai.onrender.com{file_path}</Play>
</Response>"""
        print("Daniel (EN) played:", file_path)
        return Response(twiml, mimetype="text/xml")

    # --- Step 4: Invalid input ---
    else:
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Ungültige Eingabe. Auf Wiedersehen!</Say>
</Response>"""
        return Response(twiml, mimetype="text/xml")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)





   











