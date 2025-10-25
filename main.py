import os  
from flask import Flask, request
from openai import OpenAI

app = Flask(__name__)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

@app.route("/twilio-ai", methods=["POST"])
def twilio_ai():
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are Daniel, the restaurant voice assistant for Restaurant Viadukt in Zurich. "
                    "You automatically detect whether the customer speaks German or English and respond in the same language. "
                    "Speak politely, warmly, and professionally. "
                    "Introduce yourself briefly and sound friendly. "
                    "If the customer greets you, respond naturally. "
                    "Keep responses short and clear so that you are easily understood over the phone. "
                    "If in German, use formal 'Sie' unless the customer uses 'du'."
                ),
            },
            {
                "role": "user",
                "content": request.form.get("SpeechResult", "Ein Kunde ruft an und spricht mit dir."),
            },
        ],
    )

    ai_text = completion.choices[0].message.content

    # 🔊 Hier wird automatisch Deutsch oder Englisch gesprochen – kein fester language-code nötig
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="daniel">{ai_text}</Say>
</Response>"""

    return twiml

if __name__ == "__main__":
app.run(host="0.0.0.0", port=10000)


