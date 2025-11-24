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

# WICHTIG: deine öffentliche Render-URL
BASE_URL = os.getenv("BASE_URL", "https://smavoiceai.onrender.com").rstrip("/")

SESSIONS = {}
gc = None
ws = None


def static_url(filename: str) -> str:
    """Absolute URL für MP3s, die Twilio abspielen soll."""
    return f"{BASE_URL}/static/{filename}"


def action_url() -> str:
    """Absolute URL für das nächste /twilio-ai."""
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
            ws_local.append_row([
                "Timestamp",
                "Status",
                "Nachname",
                "Geburtsdatum",
                "Anliegen",
                "Wunschdatum",
                "Wunschzeit",
                "Telefon",
                "Notiz",
            ])
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
        ws.append_row([
            ts,
            data.get("status", ""),
            data.get("lastname", ""),
            data.get("dob", ""),
            data.get("reason", ""),
            data.get("date", ""),
            data.get("time", ""),
            data.get("phone", ""),
            data.get("note", ""),
        ])
        print("✅ Termin gespeichert.")
    except Exception as e:
        print("❌ save_row error:", e)


# =========================
# Helpers
# =========================
def clean_name(raw):
    if not raw:
        return ""
    return raw.strip().strip(" .,;:!")


def clean_phone(raw):
    return re.sub(r"\D", "", raw or "")


def next_question_text(step):
    texts = [
        "Sind Sie bereits Patientin oder Patient bei uns? Bitte sagen Sie: ja, nein oder unsicher.",
        "Wie lautet Ihr Nachname? Die Praxis wird Ihren Namen beim Rückruf bestätigen.",
        "Wie ist Ihr Geburtsdatum? Bitte sagen Sie Tag, Monat und Jahr.",
        "Worum geht es bei Ihrem Anliegen? Bitte sagen Sie: Kontrolle, Rezept, akute Beschwerden, administrativ oder anderes Anliegen.",
        "Wann wünschen Sie ungefähr den Termin? Sagen Sie: heute, diese Woche, nächste Woche oder egal.",
        "Zu welcher Tageszeit passt es Ihnen am besten? Sagen Sie: morgens, nachmittags oder egal.",
        "Bitte geben Sie jetzt Ihre Telefonnummer über die Telefontastatur ein.",
    ]
    return texts[step]


def question_audio_filename(step):
    files = [
        "de_q0_status.mp3",
        "de_q1_lastname.mp3",
        "de_q2_dob.mp3",
        "de_q3_reason.mp3",
        "de_q4_date.mp3",
        "de_q5_uhrzeit.mp3",
        "de_q6_phone.mp3",
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
    """Gather für den jeweiligen Schritt bauen."""
    is_phone = (step == 6)

    if is_phone:
        g = Gather(
            input="dtmf",
            timeout=10,
            num_digits=15,
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

            # Begrüßung + erste Frage
            g.play(static_url("de_greet.mp3"))
            g.play(static_url("de_q0_status.mp3"))

            resp.append(g)
            return str(resp)

        # Weitere Schritte
        keys = ["status", "lastname", "dob", "reason", "date", "time", "phone"]
        step = sess["step"]

        if step >= len(keys):
            # schon alles gesammelt → speichern & Goodbye
            save_row(sess["data"])
            resp.play(static_url("de_farewell.mp3"))
            SESSIONS.pop(call_sid, None)
            return str(resp)

        key = keys[step]

        # Antwort speichern
        if key == "phone":
            phone_clean = clean_phone(digits or speech)
            sess["data"]["phone"] = phone_clean
            print("✅ phone =", phone_clean)
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

        # Alles gesammelt → speichern & Goodbye
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
































   











