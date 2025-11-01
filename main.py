# ===== SMA Voice AI – "Sarah & Daniel" Professional Restaurant Bot =====
from flask import Flask, request, Response
import openai
import requests
import os
import time

app = Flask(__name__)

# ===== API KEYS =====
openai.api_key = os.getenv("OPENAI_API_KEY")
ELEVEN_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# ===== Voice IDs =====
VOICE_ID_DE = "5Wv1Fpkhep8UYrgKhTHd"  # Deine geklonte Stimme "Sarah"
VOICE_ID_EN = "ZoiZ8fuDWInAcwPXaVeq"  # Daniel English

# ===== Text to Speech Function =====
def generate_voice(text, lang):
    """Generiert Sprachausgabe und speichert sie als MP3"""
    os.makedirs("static", exist_ok=True)
    path = "static/response.mp3"

    if lang == "de":
        voice_id = VOICE_ID_DE
    else:
        voice_id = VOICE_ID_EN

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": ELEVEN_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.4, "similarity_boost": 0.8}
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        with open(path, "wb") as f:
            f.write(response.content)
        return path
    except Exception as e:
        print("TTS error:", e)
        return None


# ===== AI Response Function =====
def ai_reply(user_input, lang):
    """Antwortet basierend auf Sprache und Kontext"""
    if lang == "de":
        system_prompt = """
        Du bist Sarah, eine freundliche und ruhige Assistentin des Restaurants Viadukt in Zürich.
        Du sprichst warm, professionell und natürlich.
        Du begrüßt den Kunden nur einmal.
        Wenn eine Reservierung gewünscht ist, frage nach Name, Datum, Uhrzeit, Personenanzahl und Telefonnummer.
        Wenn alles bestätigt ist, verabschiede dich höflich: „Danke für Ihren Anruf und einen schönen Abend.“
        Wenn jemand nach Öffnungszeiten fragt:
        „Unsere Öffnungszeiten sind: Montag bis Freitag von 8 bis 24 Uhr, Samstag von 10 bis 24 Uhr, Sonntag von 9 bis 24 Uhr.“
        Beantworte kurz, klar und natürlich.
        """
    else:
        system_prompt = """
        You are Daniel, a calm and polite assistant for Restaurant Viadukt in Zurich.
        Speak naturally and kindly.
        If a reservation is requested, ask for name, date, time, number of people, and phone number.
        If everything is confirmed, end politely with “Thank you for your call and have a nice evening.”
        If someone asks about opening hours:
        “Our opening hours are: Monday to Friday from 8 AM to midnight, Saturday from 10 AM to midnight, and Sunday from 9 AM to midnight.”
        Respond naturally and shortly.
        """

    try:
        resp = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ]
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print("AI Error:", e)
        return "Es tut mir leid, ein Fehler ist aufgetreten."


# ===== Flask Endpoint =====
@app.route("/twilio-ai", methods=["POST"])
def twilio_ai():
    digits = request.form.get("Digits")
    user_speech = request.form.get("SpeechResult", "").strip()

    # === Step 1: Menu ===
    if not digits and not user_speech:
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="dtmf" numDigits="1" timeout="6" action="/twilio-ai" method="POST">
        <Say language="de-DE">Für Deutsch drücken Sie die 1.</Say>
        <Pause length="1"/>
        <Say language="en-US">For English, press 2.</Say>
    </Gather>
</Response>"""
        return Response(twiml, mimetype="text/xml")

    # === Step 2: Language Selection ===
    lang = "de" if digits == "1" else "en"

    # === Step 3: AI response ===
    ai_text = ai_reply("Hallo, ich möchte gerne reservieren.", lang)
    print(f"AI: {ai_text}")

    path = generate_voice(ai_text, lang)
    time.sleep(1.5)

    if path:
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>https://smavoiceai.onrender.com/{path}</Play>
</Response>"""
    else:
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="de-DE">Ein Fehler ist aufgetreten. Bitte versuchen Sie es später erneut.</Say>
</Response>"""

    return Response(twiml, mimetype="text/xml")


# ===== RUN APP =====
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)









   











