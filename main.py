import os
import json
import time

from flask import (
    Flask,
    request,
    send_from_directory,
    url_for,
)
from twilio.twiml.voice_response import (
    VoiceResponse,
    Gather,
)
import gspread
from google.oauth2.service_account import Credentials


# =========================
# Flask Setup
# =========================
app = Flask(__name__, static_folder="static")
PORT = int(os.getenv("PORT", "10000"))

SHEET_ID = os.getenv("SHEET_ID", "")
CREDS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON", "")

SESSIONS = {}  # { CallSid: {"lang": "de"/"en", "step": int, "data": {...}} }

gc = None
ws = None


# =========================
# Google Sheets Setup
# =========================
def init_sheets():
    global gc, ws
    if not (CREDS_JSON and SHEET_ID):
        print("⚠️  GOOGLE_CREDENTIALS_JSON oder SHEET_ID fehlt.")
        return
    try:
        info = json.loads(CREDS_JSON)
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SHEET_ID)
        try:
            ws = sh.worksheet("Reservations")
            print("✅ Worksheet 'Reservations' gefunden.")
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title="Reservations", rows=1000, cols=10)
            ws.append_row(
                ["Timestamp", "Lang", "Name", "PartySize", "Date", "Time", "Phone"]
            )
            print("✅ Worksheet 'Reservations' erstellt.")
    except Exception as e:
        print("❌ init_sheets Fehler:", e)


def save_row(lang, name, party, rdate, rtime, phone):
    try:
        if ws is None:
            print("⚠️  ws ist None – nichts gespeichert.")
            return
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        ws.append_row([ts, lang, name, party, rdate, rtime, phone])
        print("✅ Reservation gespeichert.")
    except Exception as e:
        print("❌ Sheets save error:", e)


# =========================
# Helper Fragen
# =========================
def next_question(lang, step):
    de = [
        "Wie lautet Ihr Name?",
        "Für wie viele Personen?",
        "An welchem Datum?",
        "Um welche Uhrzeit?",
        "Welche Telefonnummer darf ich notieren?",
    ]
    en = [
        "What's your name?",
        "For how many people?",
        "On which date?",
        "At what time?",
        "Which phone number can I note?",
    ]
    return de[step] if lang == "de" else en[step]


# =========================
# Static & Health
# =========================
@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(app.static_folder, filename)


@app.route("/health")
def health():
    return "ok", 200


# =========================
# Twilio Webhook
# =========================
@app.route("/twilio-ai", methods=["POST"])
def twilio_ai():
    call_sid = request.form.get("CallSid", "NA")
    digits = request.form.get("Digits")
    speech = (request.form.get("SpeechResult") or "").strip()

    sess = SESSIONS.get(call_sid)
    if not sess:
        sess = {
            "lang": None,
            "step": -1,
            "data": {"name": "", "party": "", "date": "", "time": "", "phone": ""},
        }
        SESSIONS[call_sid] = sess

    resp = VoiceResponse()

    # =========================
    # 1) Sprachwahl
    # =========================
    if not sess["lang"]:
        if not digits:
            g = Gather(
                input="dtmf",
                num_digits=1,
                timeout=5,
                action="/twilio-ai",
                method="POST",
            )
            g.say(
                "Willkommen beim Restaurant Viadukt Zürich. Für Deutsch drücken Sie die 1.",
                language="de-DE",
            )
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

        lang_code = "de-DE" if sess["lang"] == "de" else "en-US"
        sess["step"] = 0

        g = Gather(
            input="speech",
            timeout=8,
            action=url_for("twilio_ai", _external=True),
            method="POST",
            language=lang_code,
        )

        # Begrüßung mit MP3
        greet_file = "de_greet.mp3" if sess["lang"] == "de" else "en_greet.mp3"
        g.play(url_for("static_files", filename=greet_file, _external=True))

        # Erste Frage
        g.say(next_question(sess["lang"], sess["step"]), language=lang_code)
        resp.append(g)
        return str(resp)

    # =========================
    # 2) Antworten speichern
    # =========================
    keys = ["name", "party", "date", "time", "phone"]

    if sess["step"] < len(keys) and speech:
        sess["data"][keys[sess["step"]]] = speech

    sess["step"] += 1

    if sess["step"] < len(keys):
        lang = sess["lang"]
        lang_code = "de-DE" if lang == "de" else "en-US"

        g = Gather(
            input="speech",
            timeout=8,
            action=url_for("twilio_ai", _external=True),
            method="POST",
            language=lang_code,
        )

        # MP3 je Frage
        audio_map = {
            "de": [
                "de_q1_name.mp3",
                "de_q2_party.mp3",
                "de_q3_date.mp3",
                "de_q4_time.mp3",
                "de_q5_phone.mp3",
            ],
            "en": [
                "en_q1_name.mp3",
                "en_q2_party.mp3",
                "en_q3_date.mp3",
                "en_q4_time.mp3",
                "en_q5_phone.mp3",
            ],
        }

        step = sess["step"]
        filename = audio_map[lang][step] if step < len(audio_map[lang]) else None

        if filename and os.path.exists(os.path.join("static", filename)):
            g.play(url_for("static_files", filename=filename, _external=True))
        else:
            g.say(next_question(lang, step), language=lang_code)

        resp.append(g)
        return str(resp)

    # =========================
    # 3) Fertig -> Speichern + Abschied
    # =========================
    d = sess["data"]
    save_row(sess["lang"], d["name"], d["party"], d["date"], d["time"], d["phone"])

    farewell_file = "de_farewell.mp3" if sess["lang"] == "de" else "en_farewell.mp3"
    resp.play(url_for("static_files", filename=farewell_file, _external=True))

    SESSIONS.pop(call_sid, None)
    return str(resp)


# =========================
# Main
# =========================
if __name__ == "__main__":
    init_sheets()
    os.makedirs("static", exist_ok=True)
    print(f"📞 SMA Voice läuft auf Port {PORT}")
    app.run(host="0.0.0.0", port=PORT)





















   











