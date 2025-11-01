from flask import Flask, request, Response
import os, time, json
import openai

# ========= Basic setup =========
app = Flask(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")
PORT = int(os.getenv("PORT", "10000"))

# In-memory state by CallSid (simple & effective for one dyno)
CALLS = {}  # { call_sid: {"lang":"de"/"en", "step":"greeting"/..., "data":{...}} }

# ========= Helpers =========
def app_base_url():
    # e.g. "https://smavoiceai.onrender.com/"
    return request.host_url.rstrip("/") + "/"

def ensure_static_dir():
    os.makedirs("static", exist_ok=True)

def tts(text, lang):
    """Generate speech mp3 via OpenAI TTS and return relative path under static/"""
    ensure_static_dir()
    voice = "verse" if lang == "de" else "alloy"  # calm German vs neutral English
    out_path = f"static/{request.values.get('CallSid','resp')}_{lang}.mp3"
    try:
        with openai.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice=voice,
            input=text
        ) as resp:
            resp.stream_to_file(out_path)
        return out_path
    except Exception as e:
        print("TTS error:", e)
        return None

def get_state(call_sid):
    if call_sid not in CALLS:
        CALLS[call_sid] = {"lang":"de", "step":"greeting", "data": {
            "intent": None,    # "reservation" or "info"
            "date": None,
            "time": None,
            "party_size": None,
            "name": None,
            "phone": None
        }}
    return CALLS[call_sid]

def set_lang(state, lang_choice):
    state["lang"] = "de" if lang_choice == "1" else "en"
    state["step"] = "greeting"

def opening_hours_text(lang):
    if lang == "de":
        return ("Unsere Öffnungszeiten sind: Montag bis Freitag 08:00 bis 00:00, "
                "Samstag 10:00 bis 00:00 und Sonntag 09:00 bis 00:00.")
    else:
        return ("Our opening hours are: Monday to Friday 8:00 AM to 12:00 AM, "
                "Saturday 10:00 AM to 12:00 AM, and Sunday 9:00 AM to 12:00 AM.")

def system_prompt(lang, state):
    if lang == "de":
        return (
            "Du bist Daniel, ein ruhiger und höflicher Kundenservice-Assistent des Restaurants Viadukt in Zürich. "
            "Sprich kurz, freundlich und natürlich, wie ein Mensch am Telefon. "
            "Wenn der Anrufer eine Reservierung machen möchte, führe einen Dialog und erfasse Schritt für Schritt: "
            "Datum (z. B. 31.10. oder morgen), Uhrzeit (z. B. 19 Uhr), Personenzahl, Name, Telefonnummer. "
            "Frage jeweils nur EINE Sache gleichzeitig. "
            "Wenn Informationen unklar sind, frage gezielt nach, z. B. 'Für wie viele Personen?' "
            f"{opening_hours_text('de')} "
            "Wenn der Anrufer eher allgemeine Fragen stellt, beantworte sie knapp. "
            "Antworte ausschließlich auf Deutsch."
        )
    else:
        return (
            "You are Daniel, a calm and polite customer service assistant for Restaurant Viadukt in Zurich. "
            "Speak briefly, friendly, and naturally, like a human on the phone. "
            "If the caller wants a reservation, run a step-by-step dialog to collect: "
            "date (e.g., Oct 31 or tomorrow), time (e.g., 7 PM), party size, name, phone. "
            "Ask only ONE item at a time. "
            "If info is unclear, ask specifically (e.g., 'For how many people?'). "
            f"{opening_hours_text('en')} "
            "If the caller asks general questions, answer concisely. "
            "Reply only in English."
        )

def ai_next_reply(user_text, lang, state):
    """
    Ask OpenAI to (1) decide intent and slots, (2) produce next short reply,
    (3) return updated state.
    """
    # Package current known data so GPT can fill missing slots
    data = state["data"]
    context_json = json.dumps(data, ensure_ascii=False)

    messages = [
        {"role":"system","content":system_prompt(lang, state)},
        {"role":"user","content":(
            f"Current collected reservation data: {context_json}\n"
            f"User said: {user_text}\n\n"
            "Task:\n"
            "1) If this is a reservation intent (or continues one), update the JSON fields (date, time, party_size, name, phone) when clearly provided.\n"
            "2) If fields are missing, ask exactly ONE next polite question to collect the next needed field.\n"
            "3) If user asks general info (like opening hours), answer briefly.\n"
            "4) Return your reply to the caller as plain text first.\n"
            "5) Then on a new line, output a single line starting with TAG:STATE= <JSON> of the updated collected data (keys: intent,date,time,party_size,name,phone)."
        )}
    ]

    try:
        resp = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.3
        )
        full = resp.choices[0].message.content.strip()
        # Split out the TAG:STATE= line if present
        lines = full.splitlines()
        bot = []
        new_state_json = None
        for ln in lines:
            if ln.strip().startswith("TAG:STATE="):
                new_state_json = ln.strip().replace("TAG:STATE=","").strip()
            else:
                bot.append(ln)
        bot_text = "\n".join(bot).strip()
        if new_state_json:
            try:
                ns = json.loads(new_state_json)
                # merge safe
                for k in ["intent","date","time","party_size","name","phone"]:
                    if k in ns:
                        state["data"][k] = ns[k]
            except Exception as e:
                print("STATE parse error:", e)
        return bot_text, state
    except Exception as e:
        print("AI error:", e)
        if lang == "de":
            return "Entschuldigung, es gab ein technisches Problem. Bitte wiederholen Sie.", state
        else:
            return "Sorry, there was a technical issue. Please repeat.", state

def twiml_play_and_listen(mp3_url, lang):
    # After playing, immediately listen again for the next user input (speech)
    say_ack = "Ich höre zu." if lang == "de" else "I'm listening."
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>{mp3_url}</Play>
    <Gather input="speech" speechTimeout="auto" action="/handle" language="{ 'de-DE' if lang=='de' else 'en-US' }">
        <Say language="{ 'de-DE' if lang=='de' else 'en-US' }">{say_ack}</Say>
    </Gather>
    <Say>Auf Wiedersehen.</Say>
</Response>"""

def twiml_say_and_listen(text, lang):
    # Fallback if TTS fails
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="{ 'de-DE' if lang=='de' else 'en-US' }">{text}</Say>
    <Gather input="speech" speechTimeout="auto" action="/handle" language="{ 'de-DE' if lang=='de' else 'en-US' }"/>
    <Say>Goodbye.</Say>
</Response>"""

# ========= Routes =========
@app.route("/twilio-ai", methods=["POST"])
def twilio_ai():
    """
    Entry & language menu. If no Digits -> play menu.
    If Digits=1/2 -> set language and start dialog.
    """
    call_sid = request.values.get("CallSid", "NA")
    digits   = request.values.get("Digits", "")
    state    = get_state(call_sid)

    # Language menu
    if not digits:
        return Response(f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather input="dtmf" numDigits="1" timeout="6" action="/twilio-ai">
    <Say language="de-DE">Willkommen beim Restaurant Viadukt. Für Deutsch drücken Sie die 1.</Say>
    <Pause length="2"/>
    <Say language="en-US">Welcome to Restaurant Viadukt. For English, press 2.</Say>
  </Gather>
  <Say language="de-DE">Kein Input erkannt. Auf Wiedersehen.</Say>
</Response>""", mimetype="text/xml")

    # Set language and greet
    set_lang(state, digits)
    lang = state["lang"]
    greet = ("Hallo, hier ist Daniel vom Restaurant Viadukt. Wie kann ich Ihnen helfen?"
             if lang=="de" else
             "Hello, this is Daniel from Restaurant Viadukt. How can I help you?")
    path = tts(greet, lang)
    time.sleep(1)
    base = app_base_url()
    if path:
        return Response(twiml_play_and_listen(base + path, lang), mimetype="text/xml")
    else:
        return Response(twiml_say_and_listen(greet, lang), mimetype="text/xml")

@app.route("/handle", methods=["POST"])
def handle():
    """
    Handles ongoing speech turns. Uses GPT to:
      - detect/continue reservation or info
      - ask for next missing slot
      - confirm when all set
    """
    call_sid = request.values.get("CallSid", "NA")
    speech   = (request.values.get("SpeechResult") or "").strip()
    state    = get_state(call_sid)
    lang     = state["lang"]

    # Safety: empty input?
    if not speech:
        prompt = ("Entschuldigung, ich habe nichts verstanden. Können Sie das bitte wiederholen?"
                  if lang=="de" else
                  "Sorry, I didn’t catch that. Could you repeat, please?")
        path = tts(prompt, lang)
        base = app_base_url()
        if path:
            return Response(twiml_play_and_listen(base + path, lang), mimetype="text/xml")
        else:
            return Response(twiml_say_and_listen(prompt, lang), mimetype="text/xml")

    # Ask AI for next reply + update state
    bot_text, state = ai_next_reply(speech, lang, state)

    # If reservation seemingly complete, add a short confirm
    d = state["data"]
    complete = all([d.get("date"), d.get("time"), d.get("party_size"), d.get("name"), d.get("phone")])
    if complete:
        if lang == "de":
            bot_text += " — Vielen Dank. Möchten Sie diese Reservierung bestätigen?"
        else:
            bot_text += " — Thank you. Would you like to confirm this reservation?"

    # TTS and keep gathering
    path = tts(bot_text, lang)
    time.sleep(1)
    base = app_base_url()
    if path:
        return Response(twiml_play_and_listen(base + path, lang), mimetype="text/xml")
    else:
        return Response(twiml_say_and_listen(bot_text, lang), mimetype="text/xml")

@app.route("/", methods=["GET"])
def health():
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)








   











