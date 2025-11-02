from flask import Flask, request, send_from_directory
from twilio.twiml.voice_response import VoiceResponse
import requests
import os
import threading
import time

app = Flask(__name__)

# === ENVIRONMENT VARIABLEN ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID_DE = os.getenv("VOICE_ID_DE", "5Wv1Fpkhep8UYrgKhTHd")  # Sarah
VOICE_ID_EN = os.getenv("VOICE_ID_EN", "ZoiZ8fuDWInAcwPXaVeq")  # Daniel

# === AUDIO ERSTELLEN (HINTERGRUND) ===
def generate_voice_async(text, voice_id, filename):
    """Erstellt Sprachdatei im Hintergrundthread"""
    try:
        print(f"🎙️ Generiere Audio mit Voice ID {voice_id}")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": ELEVENLABS_API_KEY
        }
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}
        }

        r = requests.post(url, headers=headers, json=payload)
        if r.status_code == 200:
            path = f"static/{filename}"
            with open(path, "wb") as f:
                f.write(r.content)
            print(f"✅ Audio gespeichert: {path}")
        else:
            print("❌ ElevenLabs Fehler:", r.text)

    except Exception as e:
        print("❌ Fehler beim Erstellen des Audios:", e)

# === STATIC ROUTE ===
@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory("static", filename)

# === TWILIO-HAUPTROUTE ===
@app.route("/twilio-ai", methods=["POST"])
def twilio_ai():
    resp = VoiceResponse()
    digits = request.form.get("Digits")

    # --- Auswahlmenü ---
    if not digits:
        gather = resp.gather(
            numDigits=1,
            action="/twilio-ai",
            method="POST"
        )
        gather.say("Für Deutsch drücken Sie 1. For English press 2.", language="de-DE")
        return str(resp)

    # --- Deutsch (Sarah) ---
    if digits == "1":
        resp.say("Einen Moment bitte, ich verbinde Sie mit Sarah.", language="de-DE")
        text = (
            "Hallo, hier ist Sarah vom Restaurant Viadukt. "
            "Wie darf ich Ihnen helfen? Wir sind von Montag bis Freitag von acht bis Mitternacht geöffnet, "
            "am Samstag von zehn bis Mitternacht und am Sonntag von neun bis Mitternacht."
        )
        threading.Thread(
            target=generate_voice_async,
            args=(text, VOICE_ID_DE, "response_de.mp3")
        ).start()
        time.sleep(2)
        resp.play("https://smavoiceai.onrender.com/static/response_de.mp3")

    # --- Englisch (Daniel) ---
    elif digits == "2":
        resp.say("Just a moment please, connecting you with Daniel.", language="en-US")
        text = (
            "Hello, this is Daniel from Restaurant Viadukt. "
            "How may I help you today? We are open Monday to Friday from eight AM to midnight, "
            "Saturday from ten AM to midnight and Sunday from nine AM to midnight."
        )
        threading.Thread(
            target=generate_voice_async,
            args=(text, VOICE_ID_EN, "response_en.mp3")
        ).start()
        time.sleep(2)
        resp.play("https://smavoiceai.onrender.com/static/response_en.mp3")

    else:
        resp.say("Ungültige Eingabe. Bitte versuchen Sie es erneut.", language="de-DE")

    return str(resp)

# === START DER APP ===
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    print(f"🚀 SMA Voice AI läuft auf Port {port}")
    app.run(host="0.0.0.0", port=port)














   











