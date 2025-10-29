from flask import Flask, request, Response
import openai
import os
import time

# Flask setup
app = Flask(__name__)

# API Key
openai.api_key = os.getenv("OPENAI_API_KEY")

# --- Generate voice with OpenAI Audio ---
def generate_voice(text, lang="de"):
    """Erstellt eine Sprachdatei mit OpenAI Audio TTS und speichert sie in /static"""
    os.makedirs("static", exist_ok=True)
    voice = "alloy" if lang == "en" else "verse"  # alloy = neutral English, verse = calm German
    file_name = f"static/response_{lang}.mp3"

    try:
        with openai.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice=voice,
            input=text
        ) as response:
            response.stream_to_file(file_name)
        return file_name
    except Exception as e:
        print(f"Audio generation error ({lang}):", e)
        return None

# --- Generate AI Response ---
def generate_ai_response(user_input, lang="de"):
    """Generiert Textantwort basierend auf Benutzereingabe"""
    try:
        if lang == "de":
            system_prompt = (
                "Du bist Daniel, ein höflicher Kundenservice-Mitarbeiter des Restaurants Viadukt in Zürich. "
                "Sprich ruhig, freundlich und professionell. "
                "Unsere Öffnungszeiten sind: Montag bis Freitag 08:00–00:00, Samstag 10:00–00:00, Sonntag 09:00–00:00. "
                "Wenn jemand eine Reservierung möchte, sag höflich, dass dies bald automatisiert möglich ist. "
                "Beantworte Smalltalk-Fragen freundlich und natürlich."
            )
        else:
            system_prompt = (
                "You are Daniel, a polite customer service representative for Restaurant Viadukt in Zurich. "
                "Speak warmly and naturally. "
                "Our opening hours are: Monday to Friday 8 AM to midnight, Saturday 10 AM to midnight, Sunday 9 AM to midnight. "
                "If someone asks for a reservation, kindly say that online booking will be available soon. "
                "Keep your tone conversational and kind."
            )

        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("AI error:", e)
        return "Ein technischer Fehler ist aufgetreten." if lang == "de" else "A technical error occurred."

# --- Twilio Endpoint ---
@app.route("/twilio-ai", methods=["POST"])
def twilio_ai():
    """Verarbeitet den eingehenden Anruf von Twilio"""
    try:
        digits = request.form.get("Digits")

        # --- Begrüßungsmenü ---
        if not digits:
            twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="dtmf" numDigits="1" timeout="6" action="/twilio-ai">
        <Say language="de-DE">Willkommen bei Restaurant Viadukt. Für Deutsch drücken Sie die 1.</Say>
        <Pause length="2"/>
        <Say language="en-US">Welcome to Restaurant Viadukt. For English, press 2.</Say>
    </Gather>
    <Say>Kein Input erkannt. Auf Wiedersehen!</Say>
</Response>"""
            return Response(twiml, mimetype="text/xml")

        # --- Deutsch ausgewählt ---
        elif digits == "1":
            user_input = "Was sind Ihre Öffnungszeiten?"
            ai_reply = generate_ai_response(user_input, "de")
            print("AI (DE):", ai_reply)

            path = generate_voice(ai_reply, "de")
            time.sleep(3)

            if path:
                twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response><Play>https://smavoiceai-production.up.railway.app/{path}</Play></Response>"""
            else:
                twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response><Say>Ein Fehler ist aufgetreten. Bitte versuchen Sie es später erneut.</Say></Response>"""
            return Response(twiml, mimetype="text/xml")

        # --- Englisch ausgewählt ---
        elif digits == "2":
            user_input = "What are your opening hours?"
            ai_reply = generate_ai_response(user_input, "en")
            print("AI (EN):", ai_reply)

            path = generate_voice(ai_reply, "en")
            time.sleep(3)

            if path:
                twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response><Play>https://smavoiceai-production.up.railway.app/{path}</Play></Response>"""
            else:
                twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response><Say language="en-US">An error occurred. Please try again later.</Say></Response>"""
            return Response(twiml, mimetype="text/xml")

    except Exception as e:
        print("Main route error:", e)
        error_twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response><Say>Ein interner Fehler ist aufgetreten.</Say></Response>"""
        return Response(error_twiml, mimetype="text/xml")

# --- Run Server ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))







   











