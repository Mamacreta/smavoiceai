# ============================================================
# SMA Voice AI – Restaurant Viadukt
# by Siham M. A. 💜
# ============================================================

from flask import Flask, request, Response
import os
import requests
import time

app = Flask(__name__)

# ------------------------------------------------------------
# 🔐 Load API keys from environment variables
# ------------------------------------------------------------
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
VOICE_ID_DE = os.environ.get("VOICE_ID_DE")
VOICE_ID_EN = os.environ.get("VOICE_ID_EN")

# ------------------------------------------------------------
# 🎙️ Generate AI text reply (OpenAI)
# ------------------------------------------------------------
def generate_ai_reply(message, language):
    print("🔹 Generating AI reply...")

    if language == "de":
        system_prompt = (
            "Du bist Daniel, ein höflicher Kundenservice-Assistent vom Restaurant Viadukt in Zürich. "
            "Du begrüßt freundlich, beantwortest Fragen zu Öffnungszeiten, Reservierungen oder allgemeinen Anliegen. "
            "Wenn der Kunde Smalltalk beginnt, bleib höflich, aber professionell. "
            "Öffnungszeiten: Montag–Freitag 08:00–00:00, Samstag 10:00–00:00, Sonntag 09:00–00:00."
        )
    else:
        system_prompt = (
            "You are Daniel, a polite customer service assistant for Restaurant Viadukt in Zurich. "
            "Greet kindly and answer questions about opening hours, reservations, or general inquiries. "
            "If the customer starts small talk, stay polite and professional. "
            "Opening hours: Monday–Friday 8:00–00:00, Saturday 10:00–00:00, Sunday 9:00–00:00."
        )

    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    json_data = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ]
    }

    try:
        response = requests.post("https://api.openai.com/v1/chat/completions",
                                 headers=headers, json=json_data)
        response.raise_for_status()
        ai_text = response.json()["choices"][0]["message"]["content"].strip()
        print("✅ AI Response:", ai_text)
        return ai_text
    except Exception as e:
        print("❌ OpenAI Error:", e)
        return "Es gab ein technisches Problem. Bitte versuchen Sie es später erneut."


# ------------------------------------------------------------
# 🔊 Generate voice via ElevenLabs
# ------------------------------------------------------------
def generate_voice(text, language):
    print("🔹 Generating voice...")
    voice_id = VOICE_ID_DE if language == "de" else VOICE_ID_EN
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }

    data = {
        "text": text,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        print("🟢 ELEVENLABS STATUS:", response.status_code)
        if response.status_code != 200:
            print("❌ ElevenLabs error:", response.text)
            return None

        os.makedirs("static", exist_ok=True)
        filename = "static/response.mp3"
        with open(filename, "wb") as f:
            f.write(response.content)
        print("✅ Voice file generated successfully!")
        return filename
    except Exception as e:
        print("❌ ElevenLabs Exception:", e)
        return None


# ------------------------------------------------------------
# ☎️ Twilio Endpoint
# ------------------------------------------------------------
@app.route("/twilio-ai", methods=["POST"])
def twilio_ai():
    digits = request.values.get("Digits", "")
    print("🔸 User pressed:", digits)

    # Step 1: Menü-Ansage
    if not digits:
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Gather input="dtmf" numDigits="1" timeout="5" action="/twilio-ai">
                <Say language="de-DE">Hallo! Für Deutsch drücken Sie die 1.</Say>
                <Pause length="2"/>
                <Say language="en-US">For English, press 2.</Say>
            </Gather>
            <Say>Kein Input erkannt. Auf Wiedersehen!</Say>
        </Response>"""
        return Response(twiml, mimetype="text/xml")

    # Step 2: Sprache bestimmen
    language = "de" if digits == "1" else "en"

    # Step 3: Beispieltext (später dynamisch)
    user_input = "Was sind Ihre Öffnungszeiten?"
    ai_response = generate_ai_reply(user_input, language)

    # Step 4: Stimme generieren
    path = generate_voice(ai_response, language)
    time.sleep(3)

    # Step 5: Abspielen oder Fehlermeldung
    if path:
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Play>https://smavoiceai-production.up.railway.app/{path}</Play>
        </Response>"""
    else:
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say>Ein Fehler ist aufgetreten. Bitte versuchen Sie es später erneut.</Say>
        </Response>"""

    return Response(twiml, mimetype="text/xml")


# ------------------------------------------------------------
# 🚀 Start Flask server
# ------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))






   











