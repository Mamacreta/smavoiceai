from flask import Flask, Response, request
import openai
import os

app = Flask(__name__)

openai.api_key = os.environ.get("OPENAI_API_KEY")

@app.route("/twilio-ai", methods=["POST"])
def twilio_ai():
    completion = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Du bist Daniel, ein freundlicher Restaurant-Assistent."},
            {"role": "user", "content": "Du bist Daniel, der Restaurant-Assistent vom Restaurant Viadukt in Zürich. Du sprichst höflich, ruhig und professionell, mit einem warmen Ton. Begrüsse jeden Anrufer freundlich und stelle dich vor: 'Guten Tag, hier ist Daniel vom Restaurant Viadukt.' Frage danach respektvoll, ob der Kunde eine Reservierung machen, Informationen zum Menü erhalten oder eine andere Frage stellen möchte. Antworte kurz, klar und so, dass man dich am Telefon gut versteht."}
        ]
    )

    ai_text = completion.choices[0].message.content

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="daniel" language="de-DE">{ai_text}</Say>
</Response>"""

    return Response(twiml, mimetype="text/xml")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
