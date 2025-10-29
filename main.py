from flask import Flask, request, Response
import openai
import os
import requests
import time

app = Flask(__name__)

# === API KEYS ===
openai.api_key = os.environ.get("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
VOICE_ID_DE = os.environ.get("VOICE_ID_DE")
VOICE_ID_EN = os.environ.get("VOICE_ID_EN")

# === FUNKTION: Stimme erzeugen ===
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
    response = requests.post(url, headers=headers, json=payload)
    path = os.path.join("static", "response.mp3")
    with open(path, "wb") as f:
        f.write(response.content)
    time.sleep(2)
    return path


# === FUNKTION: AI-Antwort generieren ===
def daniel_reply(prompt, language="de"):
    """AI-Logik für Daniel den Restaurant-Assistenten"""
    if language == "de":
        system_prompt = (
            "Du bist Daniel, ein freundlicher Restaurant-Assistent. "
            "Du nimmst Bestellungen entgegen, beantwortest Fragen zu Öffnungszeiten, "
            "Reservierungen und Allergien höflich und ruhig."
        )
    else:
        system_prompt = (
            "You are Daniel, a polite restaurant assistant. "
            "You help with reservations, menu questions, and allergies calmly and kindly."
        )

    chat = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
    )
    return chat.choices[0].message.content


# === HAUPTROUTE (Twilio) ===
@app.route("/twilio-ai", methods=["POST"])
def twilio_ai():
    digits = request.form.get("Digits")
    speech = request.form.get("SpeechResult", "").strip()

    # === Menü (erste Auswahl) ===
    if not digits and not speech:
        menu = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="dtmf" numDigits="1" timeout="5" action="/twilio-ai">
        <Say language="de-DE">Willkommen bei SMA Voice AI. Für Deutsch drücken Sie 1.</Say>
        <Pause length="2"/>
        <Say language="en-US">Welcome to SMA Voice AI. For English, press 2.</Say>
    </Gather>
    <Say>Kein Input erkannt. Auf Wiedersehen!</Say>
</Response>"""
        return Response(menu, mimetype="text/xml")

    # === Deutsch ausgewählt ===
    if digits == "1":
        lang = "de"
        voice = VOICE_ID_DE
        greeting = "Hallo, ich bin Daniel, der Restaurant-Assistent. Wie kann ich Ihnen helfen?"
    # === Englisch ausgewählt ===
    elif digits == "2":
        lang = "en"
        voice = VOICE_ID_EN
        greeting = "Hello, this is Daniel, your restaurant assistant. How can I help you?"
    else:
        invalid = """<?xml version="1.0" encoding="UTF-8"?>
<Response><Say>Ungültige Eingabe.</Say></Response>"""
        return Response(invalid, mimetype="text/xml")

    # === AI-Antwort generieren ===
    answer = daniel_reply(greeting, lang)
    generate_voice(answer, voice)
    time.sleep(3)

    # === HTTPS-Link (Twilio-kompatibel) ===
    audio_url = "https://smavoiceai.onrender.com/static/response.mp3"

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>{audio_url}</Play>
</Response>"""
    return Response(twiml, mimetype="text/xml")


# === SERVER START ===
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)





   











