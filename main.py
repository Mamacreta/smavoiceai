from flask import Flask, request, send_file
import requests
import os

app = Flask(__name__)

# === API Keys ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# === Voice IDs ===
VOICE_ID_DE = os.getenv("VOICE_ID_DE")
VOICE_ID_EN = os.getenv("VOICE_ID_EN")

# === Öffnungszeiten ===
OPENING_HOURS_DE = (
    "Das Restaurant Viadukt ist von Montag bis Freitag von 8 Uhr morgens bis Mitternacht geöffnet, "
    "am Samstag von 10 Uhr bis Mitternacht und am Sonntag von 9 Uhr bis Mitternacht."
)
OPENING_HOURS_EN = (
    "Restaurant Viadukt is open Monday to Friday from 8 AM until midnight, "
    "on Saturday from 10 AM until midnight, and on Sunday from 9 AM until midnight."
)

# === ElevenLabs Sprachgenerierung ===
def generate_voice(text, voice_id):
    """Erstellt Sprachausgabe mit ElevenLabs und speichert sie in /static"""
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

    # Stelle sicher, dass der static-Ordner existiert
    os.makedirs("static", exist_ok=True)
    path = os.path.join("static", "response.mp3")

    # Speichere Audiodatei
    with open(path, "wb") as f:
        f.write(r.content)

    return path


@app.route("/twilio-ai", methods=["POST"])
def twilio_ai():
    digits = request.form.get("Digits")
    speech = request.form.get("SpeechResult", "").strip()

    # === Menü ===
    if not digits and not speech:
        menu = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="dtmf speech" numDigits="1" timeout="10" action="/twilio-ai" method="POST">
        <Say language="de-DE">Willkommen beim Restaurant Viadukt. Für Deutsch, drücken Sie 1. Für Englisch, drücken Sie 2.</Say>
        <Pause length="1"/>
        <Say language="en-US">Welcome to Restaurant Viadukt. For English, press 2. For German, press 1.</Say>
    </Gather>
    <Say>Keine Eingabe erhalten. Auf Wiedersehen.</Say>
</Response>"""
        return menu

    # === Sprache auswählen ===
    if digits == "1" or "de" in speech.lower():
        text = OPENING_HOURS_DE
        voice_id = VOICE_ID_DE
    else:
        text = OPENING_HOURS_EN
        voice_id = VOICE_ID_EN

    audio_path = generate_voice(text, voice_id)
    response = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Play>https://smavoiceai.onrender.com/{audio_path}</Play>
    </Response>"""
    return response


    response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>{request.url_root}{audio_path}</Play>
</Response>"""
    return response


@app.route("/static/<path:filename>")
def static_files(filename):
    """Stellt statische Dateien wie Audiodateien bereit"""
    return send_file(os.path.join("static", filename))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

   











