from flask import Flask, request, Response
import openai
import os
import requests
import time

app = Flask(__name__)

openai.api_key = os.environ.get("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")

VOICE_ID_DE = "PAWzMWYQQXv6vAhaujU4"
VOICE_ID_EN = "ZoiZ8fuDWInAcwPXaVeq"

# Feste Öffnungszeiten (Daniel benutzt sie in Antworten)
OPENING_HOURS_DE = (
    "Das Restaurant Viadukt ist von Montag bis Freitag von 8 Uhr morgens bis Mitternacht geöffnet, "
    "am Samstag von 10 Uhr bis Mitternacht und am Sonntag von 9 Uhr bis Mitternacht."
)
OPENING_HOURS_EN = (
    "Restaurant Viadukt is open Monday to Friday from 8 AM until midnight, "
    "on Saturday from 10 AM until midnight, and on Sunday from 9 AM until midnight."
)


def generate_voice(text, voice_id):
    """Erstellt Sprachdatei mit ElevenLabs und speichert sie temporär"""
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
    path = "/tmp/response.mp3"
    with open(path, "wb") as f:
        f.write(r.content)
    return path


@app.route("/twilio-ai", methods=["POST"])
def twilio_ai():
    digits = request.form.get("Digits")
    speech = request.form.get("SpeechResult", "").strip()

    # --- Hauptmenü ---
    if not digits and not speech:
        menu = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="dtmf" numDigits="1" timeout="10" action="/twilio-ai" method="POST">
        <Say language="de-DE">Willkommen beim Restaurant Viadukt. Für Deutsch drücken Sie die 1.</Say>
        <Pause length="1"/>
        <Say language="en-US">For English, press 2.</Say>
    </Gather>
    <Redirect>/twilio-ai</Redirect>
</Response>"""
        return Response(menu, mimetype="text/xml")

    # --- Sprachauswahl ---
    if digits == "1":
        voice_id = VOICE_ID_DE
        lang = "de"
        system_msg = (
            "Du bist Daniel, ein höflicher, geduldiger deutschsprachiger Sprachassistent für das Restaurant Viadukt in Zürich. "
            "Sprich ruhig, freundlich und natürlich, mit kurzen Pausen. "
            "Wenn jemand nach Öffnungszeiten fragt, antworte: '" + OPENING_HOURS_DE + "'. "
            "Beantworte Fragen zu Reservierungen, Menü, Preisen oder Lage ebenfalls höflich und professionell. "
            "Wenn du etwas nicht weißt, sag: 'Das kann ich Ihnen gerade nicht sagen, aber ich kann Ihre Anfrage notieren.'"
        )
        greeting = "Hallo, ich bin Daniel vom Restaurant Viadukt. Wie kann ich Ihnen helfen?"
    elif digits == "2":
        voice_id = VOICE_ID_EN
        lang = "en"
        system_msg = (
            "You are Daniel, a polite and calm English-speaking voice assistant for Restaurant Viadukt in Zurich. "
            "Speak clearly, warmly and with pauses. "
            "If someone asks about opening hours, answer: '" + OPENING_HOURS_EN + "'. "
            "Answer questions about reservations, menu, prices, or location politely and professionally. "
            "If you don’t know something, say: 'I’m not sure about that, but I can note your request.'"
        )
        greeting = "Hello, this is Daniel from Restaurant Viadukt. How can I help you today?"
    else:
        repeat = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Sorry, I did not get that.</Say>
    <Redirect>/twilio-ai</Redirect>
</Response>"""
        return Response(repeat, mimetype="text/xml")

    # --- Begrüßung ---
    generate_voice(greeting, voice_id)
    greeting_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>/tmp/response.mp3</Play>
    <Gather input="speech" action="/reply?lang={}" method="POST" timeout="10"/>
</Response>""".format(lang)
    return Response(greeting_xml, mimetype="text/xml")


@app.route("/reply", methods=["POST"])
def reply():
    """Antwortet auf Kundengespräche"""
    speech = request.form.get("SpeechResult", "").strip() or " "
    lang = request.args.get("lang", "en")
    voice_id = VOICE_ID_EN if lang == "en" else VOICE_ID_DE

    system_msg = (
        "You are Daniel, a polite voice assistant for Restaurant Viadukt in Zurich. "
        "You know the restaurant is open Monday to Friday 8 AM to midnight, Saturday 10 AM to midnight, Sunday 9 AM to midnight. "
        "Answer calmly and briefly."
        if lang == "en"
        else "Du bist Daniel, ein höflicher Sprachassistent des Restaurants Viadukt in Zürich. "
             "Das Restaurant ist Montag bis Freitag von 8 Uhr bis Mitternacht geöffnet, "
             "am Samstag von 10 bis Mitternacht und am Sonntag von 9 bis Mitternacht. "
             "Antworte ruhig und kurz."
    )

    completion = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": system_msg}, {"role": "user", "content": speech}],
    )
    reply_text = completion.choices[0].message.content

    generate_voice(reply_text, voice_id)
    time.sleep(1.0)
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>/tmp/response.mp3</Play>
    <Gather input="speech" action="/reply?lang={}" method="POST" timeout="10"/>
</Response>""".format(lang)
    return Response(xml, mimetype="text/xml")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)

   











