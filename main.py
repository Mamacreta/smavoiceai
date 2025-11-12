import os, json, threading, time
from flask import Flask, request, Response, send_from_directory
from twilio.twiml.voice_response import VoiceResponse, Gather
import requests
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__, static_folder="static")

# ==== Config ====
ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY", "")
VOICE_ID_DE    = os.getenv("VOICE_ID_DE", "")
VOICE_ID_EN    = os.getenv("VOICE_ID_EN", "")
SHEET_ID       = os.getenv("SHEET_ID", "")
CREDS_JSON     = os.getenv("GOOGLE_CREDENTIALS_JSON", "")
PORT           = int(os.getenv("PORT", "10000"))

# simple in-memory call state (prototype only)
SESSIONS = {}  # { CallSid: {"lang": "de"|"en", "step": int, "data": {...}} }

# ==== Google Sheets setup ====
gc = None
sh = None
ws = None

def init_sheets():
    global gc, sh, ws
    if not (CREDS_JSON and SHEET_ID):
        return
    info = json.loads(CREDS_JSON)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    # create or open "Reservations" sheet
    try:
        ws = sh.worksheet("Reservations")
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title="Reservations", rows=1000, cols=10)
        ws.append_row(["Timestamp","Lang","Name","PartySize","Date","Time","Allergies","Phone"])

def save_row(lang, name, party, rdate, rtime, allergies, phone):
    try:
        if ws is None:
            return
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        ws.append_row([ts, lang, name, party, rdate, rtime, allergies, phone])
    except Exception as e:
        print("Sheets save error:", e)

# ==== ElevenLabs TTS (final confirmation only) ====
def eleven_tts(text, voice_id, out_path):
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": ELEVEN_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg"
        }
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.55, "similarity_boost": 0.85}
        }
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        if r.status_code == 200:
            with open(out_path, "wb") as f:
                f.write(r.content)
            return True
        print("ElevenLabs error:", r.status_code, r.text)
    except Exception as e:
        print("TTS exception:", e)
    return False

# helper: build next prompt based on state
def next_question(lang, step):
    de = [
        "Wie lautet Ihr Name?",
        "Für wie viele Personen?",
        "An welchem Datum?",
        "Um welche Uhrzeit?",
        "Gibt es Allergien oder besondere Wünsche?",
        "Welche Telefonnummer darf ich notieren?"
    ]
    en = [
        "What's your name?",
        "For how many people?",
        "On which date?",
        "At what time?",
        "Any allergies or special requests?",
        "Which phone number can I note?"
    ]
    arr = de if lang == "de" else en
    return arr[step]

def thanks_line(lang):
    return "Vielen Dank. Ich bestätige kurz." if lang == "de" else "Thank you. Let me confirm."

def open_hours(lang):
    if lang == "de":
        return ("Unsere Öffnungszeiten: Montag bis Freitag 08:00–00:00, "
                "Samstag 10:00–00:00 und Sonntag 09:00–00:00.")
    return ("Opening hours: Monday to Friday 8:00–00:00, "
            "Saturday 10:00–00:00 and Sunday 9:00–00:00.")

def greet(lang):
    if lang == "de":
        return "Willkommen bei Restaurant Viadukt Zürich. Wie kann ich helfen?"
    return "Welcome to Restaurant Viadukt Zurich. How may I help you?"

def farewell(lang):
    return "Vielen Dank, einen schönen Tag!" if lang == "de" else "Thank you, have a great day!"

@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(app.static_folder, filename)

@app.route("/health")
def health():
    return "ok", 200

@app.route("/twilio-ai", methods=["POST"])
def twilio_ai():
    call_sid = request.form.get("CallSid", "NA")
    digits = request.form.get("Digits")
    speech = (request.form.get("SpeechResult") or "").strip()

    # get or create session
    sess = SESSIONS.get(call_sid)
    if not sess:
        sess = {"lang": None, "step": -1, "data": {"name":"","party":"","date":"","time":"","allergies":"","phone":""}}
        SESSIONS[call_sid] = sess

    resp = VoiceResponse()

    # === language menu if no lang chosen ===
    if not sess["lang"]:
        if not digits:
            g = Gather(input="dtmf speech", num_digits=1, timeout=4, action="/twilio-ai", method="POST")
            g.say("Willkommen beim Restaurant Viadukt Zürich. Für Deutsch drücken Sie die 1.", language="de-DE")
            g.pause(length=1)
            g.say("For English, press 2.", language="en-US")
            resp.append(g)
            resp.say("Kein Input erkannt. Auf Wiedersehen.", language="de-DE")
            return str(resp)

        if digits == "1":
            sess["lang"] = "de"
        elif digits == "2":
            sess["lang"] = "en"
        else:
            resp.say("Ungültige Eingabe. Bitte erneut versuchen.", language="de-DE")
            return str(resp)

        # greet + first question immediately
        resp.say(greet(sess["lang"]), language="de-DE" if sess["lang"]=="de" else "en-US")
        sess["step"] = 0
        g = Gather(input="speech", timeout=6, action="/twilio-ai", method="POST")
        g.say(next_question(sess["lang"], sess["step"]),
              language="de-DE" if sess["lang"]=="de" else "en-US")
        resp.append(g)
        return str(resp)

    # === collect answers ===
    if sess["step"] >= 0:
        # write previous answer to correct field
        keys = ["name","party","date","time","allergies","phone"]
        if sess["step"] < len(keys) and speech:
            sess["data"][keys[sess["step"]]] = speech

        sess["step"] += 1

        # ask next or finish
        if sess["step"] < len(keys):
            g = Gather(input="speech", timeout=6, action="/twilio-ai", method="POST")
            g.say(next_question(sess["lang"], sess["step"]),
                  language="de-DE" if sess["lang"]=="de" else "en-US")
            resp.append(g)
            return str(resp)

        # finished collecting → save + confirm
        d = sess["data"]
        save_row(sess["lang"], d["name"], d["party"], d["date"], d["time"], d["allergies"], d["phone"])

        # quick immediate response while we render TTS
        resp.say(thanks_line(sess["lang"]), language="de-DE" if sess["lang"]=="de" else "en-US")

        # build confirmation text
        if sess["lang"] == "de":
            conf = (f"Reservierung für {d['name']}, {d['party']} Personen, am {d['date']} um {d['time']}. "
                    f"Allergien: {d['allergies'] or 'keine angegeben'}. "
                    f"Wir sind erreichbar unter der Nummer {d['phone']}. {open_hours('de')} {farewell('de')}")
            voice_id = VOICE_ID_DE
            out = "static/confirm_de.mp3"
        else:
            conf = (f"Reservation for {d['name']}, {d['party']} people, on {d['date']} at {d['time']}. "
                    f"Allergies: {d['allergies'] or 'none provided'}. "
                    f"We can reach you at {d['phone']}. {open_hours('en')} {farewell('en')}")
            voice_id = VOICE_ID_EN
            out = "static/confirm_en.mp3"

        # render TTS in background and then let Twilio fetch it
        def render_and_log():
            ok = eleven_tts(conf, voice_id, out)
            print("TTS ready:", ok, "->", out)

        threading.Thread(target=render_and_log, daemon=True).start()
        time.sleep(1)  # tiny pad so the file likely exists before Twilio fetch

        file_url = f"https://{request.host}/{out}"
        resp.play(file_url)
        # cleanup session
        try:
            del SESSIONS[call_sid]
        except:
            pass
        return str(resp)

    # fallback
    resp.say("Ein Fehler ist aufgetreten. Bitte versuchen Sie es später erneut.", language="de-DE")
    return str(resp)

if __name__ == "__main__":
    init_sheets()
    os.makedirs("static", exist_ok=True)
    print(f"📞 SMA Voice AI läuft auf Port {PORT}")
    app.run(host="0.0.0.0", port=PORT)


















   











