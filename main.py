from flask import Flask, request, Response
import openai
import os

app = Flask(__name__)

openai.api_key = os.environ.get("OPENAI_API_KEY")

@app.route("/twilio-ai", methods=["POST"])
def twilio_ai():
    user_input = request.form.get("SpeechResult", "").lower()
    digits = request.form.get("Digits")

    # Wenn der Anrufer eine Zahl gedrückt hat:
    if digits == "1":
        language = "de-DE"
        greeting = "Willkommen beim Restaurant Viadukt. Wie kann ich Ihnen helfen?"
    elif digits == "2":
        language = "en-US"
        greeting = "Welcome to Restaurant Viadukt. How can I help you today?"
    else:
        # Wenn noch keine Auswahl getroffen wurde
        choose_language = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech dtmf" numDigits="1" action="/twilio-ai" method="POST">
        <Say voice="daniel" language="de-DE">
            Willkommen beim Restaurant Viadukt.
            Für Deutsch drücken Sie die 1.
            For English, press 2.
        </Say>
    </Gather>
</Response>"""
        return Response(choose_language, mimetype="text/xml")

    # OpenAI-Kommunikation
    completion = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system",
             "content": (
                f"Du bist Daniel, der freundliche und professionelle "
                f"Restaurantassistent vom Restaurant Viadukt in Zürich. "
                f"Wenn Sprache {language} ist, antworte vollständig in dieser Sprache. "
                f"Klinge natürlich, höflich und hilfsbereit – wie ein echter Mensch. "
                f"Halte die Antworten kurz und klar, und sprich so, als würdest du wirklich am Telefon sein."
             )
            },
            {"role": "user", "content": user_input or "Begrüsse den Kunden höflich."}
        ]
    )

    ai_text = completion.choices[0].message.content

    # TwiML-Antwort
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="daniel" language="{language}">
        {ai_text}
    </Say>
</Response>"""
    return Response(twiml, mimetype="text/xml")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)







