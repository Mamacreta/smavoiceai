from flask import Flask, request, Response
import openai
import os
import requests
import time

app = Flask(__name__)

openai.api_key = os.environ.get("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")

VOICE_ID_DE = "PAWzMWYQQXv6vAhaujU4"  # Deutsche männliche Stimme
VOICE_ID_EN = "ZoiZ8fuDWInAcwPXaVeq"  # Englische männliche Stimme


def generate_voice(text, voice_id):
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
    r = requests.post(url, headers=headers, json=payload)
    path = "/tmp/response.mp3"
    with open(path, "wb") as f:
        f.write(r.content)
    return path


@app.route("/twilio-ai", methods=["POST"])
def twilio_ai():
    digits = request.form.get("Digits")
    speech = request.form.get("SpeechResult", "").strip()

    # === Sprachmenü ===
    if not digits and not speech:
        menu = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="dtmf speech" numDigits="1" timeout="10" action="/twilio-ai" method="POST">
        <Say language="de-DE">Willkommen beim Restaurant Viadukt. Für Deutsch drücken Sie die 1.</Say>
        <Say language="en-US">For English, press 2.</Say>
    </Gather>
    <Redirect>/twilio-ai</Redirect>
</Response>"""
        return Response(menu, mimetype="text/xml")

    # === Sprachauswahl ===
    if digits == "1":
        
        voice_id = VOICE_ID_DE
        system_msg = (
            "Du bist Daniel, ein ruhiger, höflicher deutschsprachiger Sprachassistent des Restaurants Viadukt in Zürich. "
            "Sprich langsam, freundlich und natürlich. Mach kurze Pausen zwischen Sätzen. "
            "Antworte nur auf Deutsch."
        )
        greeting = "Hallo, ich bin Daniel vom Restaurant Viadukt. Wie kann ich Ihnen helfen?"
    elif digits == "2":
        
        voice_id = VOICE_ID_EN
        system_msg = (
            "You are Daniel, a calm and friendly English-speaking voice assistant for Restaurant Viadukt in Zurich. "
            "Speak naturally, at a slow and clear pace, with short pauses. "
            "Respond only in English."
        )
        greeting = "Hello, this is Daniel from Restaurant Viadukt. How can I help you today?"
    else:
        
        voice_id = VOICE_ID_EN
        system_msg = "You are Daniel, a calm and friendly English-speaking voice assistant for Restaurant Viadukt."
        greeting = "Hello, this is Daniel. How can I help you?"

    # === Begrüßung nach Sprachwahl ===
    if digits:
        generate_voice(greeting, voice_id)
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>https://smavoiceai.onrender.com/static/response.mp3</Play>
</Response>"""
        return Response(twiml, mimetype="text/xml")

    # === Wenn Kunde redet ===
    completion = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": speech}
        ]
    )
    reply = completion.choices[0].message.content

    generate_voice(reply, voice_id)
    time.sleep(1.0)
    twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>https://smavoiceai.onrender.com/static/response.mp3</Play>
</Response>"""
    return Response(twiml, mimetype="text/xml")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)










