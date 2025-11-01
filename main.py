# ===== SMA Voice AI – Gesprächsversion (Sarah & Daniel) =====
from flask import Flask, request, Response
import openai
import requests
import os
import threading

app = Flask(__name__)

# ===== API KEYS =====
openai.api_key = os.getenv("OPENAI_API_KEY")
ELEVEN_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# ===== Voice IDs =====
VOICE_ID_DE = "5Wv1Fpkhep8UYrgKhTHd"  # Sarah (deine geklonte Stimme)
VOICE_ID_EN = "ZoiZ8fuDWInAcwPXaVeq"  # Daniel (englische Stimme)

# ===== Text-to-Speech (asynchron, schnell) =====
def generate_voice_async(text, lang):
    """Erzeugt Audio im Hintergrund, damit keine Wartezeit entsteht."""
    def worker():
        try:
            voice_id = VOICE_ID_DE if lang == "de" else VOICE_ID_EN
            path = f"static/response_{lang}.mp3"
            os.makedirs("static", exist_ok=True)

            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            headers = {
                "xi-api-key": ELEVEN_API_KEY,
                "Content-Type": "application/json"
            }
            payload = {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.9}
            }

            r = requests.post(url, headers=headers, json=payload)
            r.raise_for_status()
            with open(path, "wb") as f:
                f.write(r.content)
            print(f"✅ Voice generated for {lang}: {path}")
        except Exception as e:
            print("❌ ElevenLabs Error:", e)

    threading.Thread(target=worker).start()
    return f"static/response_{lang}.mp3"


# ===== Gesprächsfluss =====
def ai_reply(user_input, lang, context):
    """Erzeugt KI-Antwort basierend auf vorherigem Gesprächsverlauf."""
    try:
        if lang == "de":
            system_prompt = (
                "Du bist Sarah, die höfliche und freundliche Assistentin des Restaurants Viadukt in Zürich. "
                "Führe ein natürliches Gespräch auf Deutsch. "
                "Frage nacheinander nach Name, Datum, Uhrzeit, Personenanzahl und Telefonnummer. "
                "Wenn alle Informationen vorhanden sind, bestätige die Reservierung mit: "
                "'Vielen Dank! Ihre Reservierung wurde notiert. Einen schönen Abend noch.' "
                "Wenn der Kunde sich verabschiedet oder Danke sagt, beende höflich das Gespräch. "
                "Wenn er etwas anderes fragt, antworte passend, aber kurz und professionell."
            )
        else:
            system_prompt = (
                "You are Daniel, the polite English-speaking assistant of Restaurant Viadukt in Zurich. "
                "Guide the user through a natural conversation. "
                "Ask step by step for name, date, time, number of people, and phone number. "
                "Once all are provided, confirm the reservation with: "
                "'Thank you! Your reservation is confirmed. Have a great evening.' "
                "If the caller says goodbye or thanks, end the call politely."
            )

        conversation = context + [{"role": "user", "content": user_input}]

        resp = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt}] + conversation
        )

        ai_text = resp.choices[0].message.content.strip()
        print(f"🤖 {lang.upper()}:", ai_text)
        return ai_text

    except Exception as e:
        print("❌ OpenAI Error:", e)
        return "Es tut mir leid, es gab ein technisches Problem."


# ===== Haupt-Route für Twilio =====
@app.route("/twilio-ai", methods=["POST"])
def twilio_ai():
    digits = request.form.get("Digits")
    user_speech = (request.form.get("SpeechResult") or "").strip()

    # === Step 1: Menü (Sprache wählen) ===
    if not digits and not user_speech:
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="dtmf" numDigits="1" timeout="5" action="/twilio-ai" method="POST">
        <Say language="de-DE">Für Deutsch drücken Sie die 1.</Say>
        <Pause length="1"/>
        <Say language="en-US">For English, press 2.</Say>
    </Gather>
</Response>"""
        return Response(twiml, mimetype="text/xml")

    # === Step 2: Sprachwahl ===
    lang = "de" if digits == "1" else "en"
    quick_reply = "Einen Moment bitte..." if lang == "de" else "Just a moment please..."
    print(f"📞 Sprache erkannt: {lang.upper()}")

    # Sofortige Rückmeldung
    twiml_quick = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="{'de-DE' if lang == 'de' else 'en-US'}">{quick_reply}</Say>
</Response>"""

    # Starte Gespräch asynchron
    threading.Thread(target=start_conversation, args=(lang,)).start()

    return Response(twiml_quick, mimetype="text/xml")


# ===== Gesprächslogik =====
def start_conversation(lang):
    """Simuliert eine fließende Unterhaltung (Dialog)."""
    context = []

    # 1. Begrüßung & erste Frage
    first_input = "Hallo, ich möchte reservieren."
    ai_text = ai_reply(first_input, lang, context)
    context.append({"role": "assistant", "content": ai_text})
    generate_voice_async(ai_text, lang)

    # 2. Simulation: der Kunde antwortet
    fake_replies = [
        "Mein Name ist Ahmed.",
        "Am Freitag um 19 Uhr.",
        "Für vier Personen.",
        "Meine Nummer ist 079 123 45 67.",
        "Danke, das wäre alles."
    ]

    for reply in fake_replies:
        ai_text = ai_reply(reply, lang, context)
        context.append({"role": "assistant", "content": ai_text})
        generate_voice_async(ai_text, lang)


# ===== Start der App =====
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)












   











