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

# { CallSid: {"step": int, "started": bool, "data": {...}} }
SESSIONS = {}

gc = None
ws = None


# =========================
# Google Sheets Setup
# =========================
def init_sheets():
    """
    Initialisiert Google Sheets und das Worksheet 'Appointments'.
    """
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
            ws = sh.worksheet("Appointments")
            print("✅ Worksheet 'Appointments' gefunden.")
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title="Appointments", rows=1000, cols=10)
            ws.append_row(
                [
                    "Timestamp",
                    "Status",      # bestehend / neu
                    "Name",
                    "Geburtsdatum",
                    "Anliegen",
                    "Wunschdatum",
                    "Wunschzeit",
                    "Telefon",
                ]
            )
            print("✅ Worksheet 'Appointments' erstellt.")
    except Exception as e:
        print("❌ init_sheets Fehler:", e)


def save_row(data: dict):
    """
    Speichert einen Termin in Google Sheets.
    """
    try:
        if ws is None:
            print("⚠️  ws ist None – nichts gespeichert.")
            return
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        ws.append_row(
            [
                ts,
                data.get("status", ""),
                data.get("name", ""),
                data.get("dob", ""),
                data.get("reason", ""),
                data.get("date", ""),
                data.get("time", ""),
                data.get("phone", ""),
            ]
        )
        print("✅ Termin gespeichert.")
    except Exception as e:
        print("❌ Sheets save error:", e)


# =========================
# Helper
# =========================
def next_question_text(step: int) -> str:
    texts = [
        "Sind Sie bereits Patientin oder Patient bei uns? Bitte sagen Sie: ja, nein oder unsicher.",
        "Wie lautet Ihr Vor- und Nachname? Bitte sprechen Sie langsam und deutlich. Wenn Ihr Name schwierig ist, können Sie ihn auch Buchstabe für Buchstabe sagen.",
        "Wie ist Ihr Geburtsdatum? Bitte nennen Sie Tag, Monat und Jahr.",
        "Worum geht es bei Ihrem Anliegen? Zum Beispiel Kontrolle, akute Beschwerden, Rezept oder etwas anderes.",
        "Für welches Datum wünschen Sie einen Termin? Sie können auch sagen: so bald wie möglich.",
        "Zu welcher Uhrzeit passt es Ihnen am besten? Morgens, nachmittags oder eine genaue Uhrzeit.",
        "Unter welcher Telefonnummer können wir Sie zurückrufen? Bitte sprechen Sie die Nummer deutlich aus.",
    ]
    return texts[step]


def question_audio_filename(step: int) -> str:
    files = [
        "de_q0_status.mp3",
        "de_q1_name.mp3",
        "de_q2_dob.mp3",
        "de_q3_reason.mp3",
        "de_q4_date.mp3",
        "de_q5_time.mp3",
        "de_q6_phone.mp3",
    ]
    return files[step]


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
    try:
        call_sid = request.form.get("CallSid", "NA")
        raw_speech = request.form.get("SpeechResult") or ""
        # leichte Bereinigung für komische Zeichen
        speech = raw_speech.strip().replace("’", "'").replace("`", "'")

        print("---- /twilio-ai ----")
        print("CallSid:", call_sid)
        print("SpeechResult (raw):", raw_speech)

        # Session holen / erstellen
        sess = SESSIONS.get(call_sid)
        if not sess:
            sess = {
                "started": False,
                "step": 0,
                "data": {
                    "status": "",
                    "name": "",
                    "dob": "",
                    "reason": "",
                    "date": "",
                    "time": "",
                    "phone": "",
                },
            }
            SESSIONS[call_sid] = sess

        resp = VoiceResponse()

        # =========================
        # 1) Begrüßung + erste Frage
        # =========================
        if not sess["started"]:
            sess["started"] = True

            g = Gather(
                input="speech",
                timeout=10,
                speech_timeout="auto",
                action=url_for("twilio_ai", _external=True),
                method="POST",
                language="de-DE",
            )
            g.pause(length=1)

            # Begrüßung
            greet_url = url_for(
                "static_files", filename="de_greet.mp3", _external=True
            )
            g.play(greet_url)

            # Erste Frage (Status)
            q0_url = url_for(
                "static_files", filename="de_q0_status.mp3", _external=True
            )
            g.play(q0_url)

            resp.append(g)
            resp.say(
                "Leider habe ich Sie nicht verstanden. Bitte rufen Sie später erneut an.",
                language="de-DE",
            )
            return str(resp)

        # =========================
        # 2) Antworten sammeln
        # =========================
        keys = ["status", "name", "dob", "reason", "date", "time", "phone"]
        step = sess["step"]

        # Wenn nichts verstanden wurde → gleiche Frage nochmal
        if not speech and step < len(keys):
            g = Gather(
                input="speech",
                timeout=10,
                speech_timeout="auto",
                action=url_for("twilio_ai", _external=True),
                method="POST",
                language="de-DE",
            )
            g.pause(length=1)

            filename = question_audio_filename(step)
            audio_path = os.path.join("static", filename)

            if os.path.exists(audio_path):
                g.play(url_for("static_files", filename=filename, _external=True))
            else:
                g.say(next_question_text(step), language="de-DE")

            resp.append(g)
            return str(resp)

        # Wenn was gesagt wurde → speichern
        if step < len(keys) and speech:
            key = keys[step]
            sess["data"][key] = speech
            print(f"✅ {key} = {speech}")

        sess["step"] += 1
        step = sess["step"]

        # Noch Fragen offen?
        if step < len(keys):
            g = Gather(
                input="speech",
                timeout=10,
                speech_timeout="auto",
                action=url_for("twilio_ai", _external=True),
                method="POST",
                language="de-DE",
            )
            g.pause(length=1)

            filename = question_audio_filename(step)
            audio_path = os.path.join("static", filename)

            if os.path.exists(audio_path):
                g.play(url_for("static_files", filename=filename, _external=True))
            else:
                g.say(next_question_text(step), language="de-DE")

            resp.append(g)
            return str(resp)

        # =========================
        # 3) Fertig -> Speichern + Abschied
        # =========================
        save_row(sess["data"])

        farewell_url = url_for(
            "static_files", filename="de_farewell.mp3", _external=True
        )
        resp.play(farewell_url)

        SESSIONS.pop(call_sid, None)
        return str(resp)

    except Exception as e:
        # Fängt alles ab, damit Twilio nicht "Application Error" schreit
        print("❌ twilio_ai error:", e)
        resp = VoiceResponse()
        resp.say(
            "Leider ist ein technischer Fehler aufgetreten. Bitte rufen Sie später erneut an.",
            language="de-DE",
        )
        return str(resp)


# =========================
# Main
# =========================
if __name__ == "__main__":
    init_sheets()
    os.makedirs("static", exist_ok=True)
    print(f"📞 SMA Voice – Arztpraxis läuft auf Port {PORT}")
    app.run(host="0.0.0.0", port=PORT)























   











