import os
import json
import time
import re

from flask import Flask, request, send_from_directory
from twilio.twiml.voice_response import VoiceResponse, Gather
import gspread
from google.oauth2.service_account import Credentials

# =========================
# Flask & Config
# =========================
app = Flask(__name__, static_folder="static")
PORT = int(os.getenv("PORT", "10000"))

SHEET_ID = os.getenv("SHEET_ID", "")
CREDS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON", "")

# Deine öffentliche Render-URL
BASE_URL = os.getenv("BASE_URL", "https://smavoiceai.onrender.com").rstrip("/")

SESSIONS = {}
gc = None
ws = None


def static_url(filename: str) -> str:
    """Absolute URL für MP3s."""
    return f"{BASE_URL}/static/{filename}"


def action_url() -> str:
    """Absolute URL für /twilio-ai."""
    return f"{BASE_URL}/twilio-ai"


# =========================
# Google Sheets
# =========================
def init_sheets():
    global gc, ws
    if not (CREDS_JSON and SHEET_ID):
        print("⚠️ GOOGLE_CREDENTIALS_JSON oder SHEET_ID fehlt.")
        return

    try:
        info = json.loads(CREDS_JSON)
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        gc = gspread.authorize(creds)

        sheet_key = SHEET_ID
        if "https://docs.google.com" in sheet_key:
            try:
                sheet_key = sheet_key.split("/d/")[1].split("/")[0]
            except Exception as e:
                print("❌ sheet_key extract error:", e)
                return

        sh = gc.open_by_key(sheet_key)

        try:
            ws_local = sh.worksheet("SMA Voice Reservation")
            print("✅ Worksheet 'SMA Voice Reservation' gefunden.")
        except gspread.exceptions.WorksheetNotFound:
            ws_local = sh.add_worksheet("SMA Voice Reservation", rows=1000, cols=10)
            ws_local.append_row(
                [
                    "Timestamp",
                    "Status",
                    "Nachname",
                    "Geburtsdatum",
                    "Anliegen",
                    "Wunschdatum",
                    "Wunschzeit",
                    "Telefon",
                    "Notiz",
                ]
            )
            print("✅ Worksheet 'SMA Voice Reservation' erstellt.")

        ws = ws_local
        globals()["ws"] = ws

    except Exception as e:
        print("❌ init_sheets error:", e)


def save_row(data):
    if ws is None:
        print("⚠️ ws ist None – nichts gespeichert.")
        return
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        ws.append_row(
            [
                ts,
                data.get("status", ""),
                data.get("lastname", ""),
                data.get("dob", ""),
                data.get("reason", ""),
                data.get("date", ""),
                data.get("time", ""),
                data.get("phone", ""),
                data.get("note", ""),
            ]
        )
        print("✅ Termin gespeichert.")
    except Exception as e:
        print("❌ save_row error:", e)


# =========================
# Helpers
# =========================
def clean_name(raw: str) -> str:
    if not raw:
        return ""
    return raw.strip().strip(" .,;:!")


def clean_phone(raw: str) -> str:
    return re.sub(r"\D", "", raw or "")


def format_dob_from_digits(digits: str) -> str:
    """
    Erwartet 6 (DDMMYY) oder 8 (DDMMYYYY) Ziffern.
    Gibt z.B. '01.08.2007' zurück.
    """
    d = re.sub(r"\D", "", digits or "")
    if len(d) == 6:
        dd = d[0:2]
        mm = d[2:4]
        yy = d[4:6]
        yy_int = int(yy)
        if yy_int <= 30:
            year = f"20{yy}"
        else:
            year = f"19{yy}"
        return f"{dd}.{mm}.{year}"
    elif len(d) == 8:
        dd = d[0:2]
        mm = d[2:4]
        year = d[4:8]
        return f"{dd}.{mm}.{year}"
    else:
        return d


def next_question_text(step: int) -> str:
    texts = [
        "Sind Sie bereits Patientin oder Patient bei uns? Bitte sagen Sie: ja, nein oder unsicher.",
        "Wie lautet Ihr Nachname? Die Praxis wird Ihren Namen beim Rückruf bestätigen.",
        "Bitte geben Sie jetzt Ihr Geburtsdatum als sechsstellige Zahl ein, zum Beispiel 010807 für den ersten August zweitausendsieben.",
        "Worum geht es bei Ihrem Anliegen? Bitte sagen Sie: Kontrolle, Rezept, akute Beschwerden, administrativ oder anderes Anliegen.",
        "Wann wünschen Sie ungefähr den Termin? Sagen Sie: heute, diese Woche, nächste Woche oder egal.",
        "Zu welcher Tageszeit passt es Ihnen am besten? Sagen Sie: morgens, nachmittags oder egal.",
        "Bitte geben Sie jetzt Ihre Telefonnummer mit zehn Ziffern über die Telefontastatur ein.",
    ]
    return texts[step]


def question_audio_filename(step: int) -> str:
    files = [
        "de_q0_status.mp3",   # 0 Status
        "de_q1_lastname.mp3", # 1 Nachname
        "de_q2_dob.mp3",      # 2 Geburtsdatum (DTMF)
        "de_q3_reason.mp3",   # 3 Anliegen
        "de_q4_date.mp3",     # 4 Zeitraum
        "de_q5_uhrzeit.mp3",  # 5 Tageszeit
        "de_q6_phone.mp3",    # 6 Telefon (DTMF)
    ]
    return files[step]


def play_question(g: Gather, step: int):
    filename = question_audio_filename(step)
    path = os.path.join("static", filename)
    if os.path.exists(path):
        g.play(static_url(filename))
    else:
        g.say(next_question_text(step), language="de-DE")


def create_gather(step: int) -> Gather:
    """
    step 0,1,3,4,5 = Speech
    step 2 (dob)   = DTMF (bis 8 Ziffern)
    step 6 (phone) = DTMF (10 Ziffern)
    """
    is_dob = (step == 2)
    is_phone = (step == 6)

    if is_dob:
        g = Gather(
            input="dtmf",
            timeout=15,
            num_digits=8,   # erlaubt 6 oder 8 Ziffern (z.B. 010807 oder 01082007)
            action=action_url(),
            method="POST",
        )
    elif is_phone:
        g = Gather(
            input="dtmf",
            timeout=15,
            num_digits=10,  # z.B. 0761234567
            action=action_url(),
            method="POST",
        )
    else:
        g = Gather(
            input="speech",
            timeout=10,
            speech_timeout="auto",
            action=action_url(),
            method="POST",
            language="de-DE",
        )

    g.pause(length=1)
    play_question(g, step)
    return g


# =========================
# Static
# =========================
@app.route("/static/<path:f>")
def static_files(f):
    return send_from_directory(app.static_folder, f)


@app.route("/health")
def health():
    return "ok", 200


# =========================
# Twilio Webhook
# =========================
@app.route("/twilio-ai", methods=["GET", "POST"])
def twilio_ai():
    resp = VoiceResponse()
    try:
        data = request.form if request.method == "POST" else request.args

        call_sid = data.get("CallSid", "NA")
        speech = (data.get("SpeechResult") or "").strip()
        digits = (data.get("Digits") or "").strip()

        print("---- /twilio-ai ----")
        print("CallSid:", call_sid)
        print("SpeechResult:", speech)
        print("Digits:", digits)

        sess = SESSIONS.get(call_sid)
        if not sess:
            sess = {
                "started": False,
                "step": 0,
                "data": {
                    "status": "",
                    "lastname": "",
                    "dob": "",
                    "reason": "",
                    "date": "",
                    "time": "",
                    "phone": "",
                    "note": "",
                },
            }
            SESSIONS[call_sid] = sess

        # Start: Begrüßung + Status
        if not sess["started"]:
            sess["started"] = True

            g = Gather(
                input="speech",
                timeout=10,
                speech_timeout="auto",
                action=action_url(),
                method="POST",
                language="de-DE",
            )
            g.pause(length=1)
            g.play(static_url("de_greet.mp3"))
            g.play(static_url("de_q0_status.mp3"))

            resp.append(g)
            return str(resp)

        keys = ["status", "lastname", "dob", "reason", "date", "time", "phone"]
        step = sess["step"]

        # Wenn gar nichts gesagt/getippt wurde → gleiche Frage wiederholen
        if not speech and not digits and step < len(keys):
            print("⚠️ Keine Eingabe – Frage wird wiederholt, step =", step)
            g = create_gather(step)
            resp.append(g)
            return str(resp)

        # Wenn wir schon alles haben → speichern & Goodbye
        if step >= len(keys):
            save_row(sess["data"])
            resp.play(static_url("de_farewell.mp3"))
            SESSIONS.pop(call_sid, None)
            return str(resp)

        key = keys[step]

        # Antwort speichern je nach Feld
        if key == "phone":
            phone_clean = clean_phone(digits)
            sess["data"]["phone"] = phone_clean
            print("✅ phone =", phone_clean)

        elif key == "dob":
            dob_formatted = format_dob_from_digits(digits)
            sess["data"]["dob"] = dob_formatted
            print("✅ dob =", dob_formatted)

        elif key == "lastname":
            sess["data"]["lastname"] = clean_name(speech)
            print("✅ lastname =", sess["data"]["lastname"])

        else:
            sess["data"][key] = speech
            print(f"✅ {key} =", speech)

        # Nächster Schritt
        sess["step"] += 1
        step = sess["step"]

        if step < len(keys):
            g = create_gather(step)
            resp.append(g)
            return str(resp)

        # Alles eingesammelt → speichern & Verabschiedung
        save_row(sess["data"])
        resp.play(static_url("de_farewell.mp3"))
        SESSIONS.pop(call_sid, None)
        return str(resp)

    except Exception as e:
        print("❌ twilio_ai error:", e)
        resp.say("Leider ist ein Fehler aufgetreten.", language="de-DE")
        return str(resp)


# =========================
# Init & Start
# =========================
init_sheets()
os.makedirs("static", exist_ok=True)
print("✅ SMA Voice – Arztpraxis gestartet mit BASE_URL:", BASE_URL)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)

































   











