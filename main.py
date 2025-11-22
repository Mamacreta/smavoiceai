import os
import json
import time

from flask import Flask, request, send_from_directory, url_for
from twilio.twiml.voice_response import VoiceResponse, Gather
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__, static_folder="static")
PORT = int(os.getenv("PORT", "10000"))

SHEET_ID = os.getenv("SHEET_ID", "")
CREDS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON", "")

SESSIONS = {}
gc = None
ws = None


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
                print("ℹ️ SHEET_ID aus URL extrahiert:", sheet_key)
            except Exception as e:
                print("❌ Konnte SHEET_ID aus URL nicht extrahieren:", e)
                return

        sh = gc.open_by_key(sheet_key)

        try:
            ws_name = "SMA Voice Reservation"
            ws_local = sh.worksheet(ws_name)
            print(f"✅ Worksheet '{ws_name}' gefunden.")
        except gspread.exceptions.WorksheetNotFound:
            try:
                ws_name = "Appointments"
                ws_local = sh.worksheet(ws_name)
                print(f"✅ Worksheet '{ws_name}' gefunden.")
            except gspread.exceptions.WorksheetNotFound:
                ws_name = "SMA Voice Reservation"
                ws_local = sh.add_worksheet(title=ws_name, rows=1000, cols=10)
                ws_local.append_row(
                    [
                        "Timestamp",
                        "Status",      # bestehend / neu
                        "Nachname",
                        "Geburtsdatum",
                        "Anliegen",
                        "Wunschdatum",
                        "Wunschzeit",
                        "Telefon",
                        "NameNotiz",   # Name unsicher / falsch erkannt
                    ]
                )
                print(f"✅ Worksheet '{ws_name}' erstellt.")

        ws = ws_local

    except Exception as e:
        print("❌ init_sheets Fehler:", e)


def save_row(data: dict):
    try:
        if ws is None:
            print("⚠️ ws ist None – nichts gespeichert.")
            return
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
                data.get("name_note", ""),
            ]
        )
        print("✅ Termin gespeichert.")
    except Exception as e:
        print("❌ Sheets save error:", e)


# =========================
# Helper für Fragen
# =========================
def next_question_text(step: int) -> str:
    texts = [
        "Sind Sie bereits Patientin oder Patient bei uns? Bitte sagen Sie: ja, nein oder unsicher.",
        "Wie lautet Ihr Nachname? Falls das System Ihren Namen nicht korrekt versteht, sagen Sie bitte: falsch. Wir klären das im Rückruf.",
        "Wie ist Ihr Geburtsdatum? Bitte nennen Sie Tag, Monat und Jahr.",
        "Worum geht es bei Ihrem Anliegen? Zum Beispiel Kontrolle, akute Beschwerden, Rezept oder etwas anderes.",
        "Für welches Datum wünschen Sie einen Termin? Sie können auch sagen: so bald wie möglich.",
        "Zu welcher Uhrzeit passt es Ihnen am besten? Morgens, nachmittags oder eine genaue Uhrzeit.",
        "Unter welcher Telefonnummer können wir Sie zurückrufen? Bitte sprechen Sie die Nummer deutlich aus.",
    ]
    return texts[step]


def question_audio_filename(step: int) -> str:
    files = [
        "de_q0_status.mp3",      # 0 – Status
        "de_q1_lastname.mp3",    # 1 – Nachname
        "de_q2_dob.mp3",         # 2 – Geburtsdatum
        "de_q3_reason.mp3",      # 3 – Anliegen
        "de_q4_date.mp3",        # 4 – Wunschdatum
        "de_q5_uhrzeit.mp3",     # 5 – Uhrzeit
        "de_q6_phone.mp3",       # 6 – Telefon
    ]
    return files[step]


def play_or_say_question(gather: Gather, step: int):
    filename = question_audio_filename(step)
    path = os.path.join("static", filename)
    if os.path.exists(path):
        gather.play(url_for("static_files", filename=filename, _external=True))
    else:
        gather.say(next_question_text(step), language="de-DE")


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
@app.route("/twilio-ai", methods=["GET", "POST"])
def twilio_ai():
    resp = VoiceResponse()
    try:
        data = request.form if request.method == "POST" else request.args

        call_sid = data.get("CallSid", "NA")
        raw_speech = data.get("SpeechResult") or ""
        speech = raw_speech.strip()

        print("---- /twilio-ai ----")
        print("Method:", request.method)
        print("CallSid:", call_sid)
        print("SpeechResult (raw):", raw_speech)

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
                    "name_note": "",
                },
            }
            SESSIONS[call_sid] = sess

        # 1) Erster Durchlauf: Begrüßung + erste Frage
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

            greet_url = url_for("static_files", filename="de_greet.mp3", _external=True)
            g.play(greet_url)

            q0_url = url_for("static_files", filename="de_q0_status.mp3", _external=True)
            g.play(q0_url)

            resp.append(g)
            return str(resp)

        # 2) spätere Schritte: Antworten sammeln
        keys = ["status", "lastname", "dob", "reason", "date", "time", "phone"]
        step = sess["step"]

        # nichts verstanden → gleiche Frage nochmal
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
            play_or_say_question(g, step)
            resp.append(g)
            return str(resp)

        # etwas gesagt
        if step < len(keys) and speech:
            key = keys[step]

            # Spezialfall Nachname
            if key == "lastname":
                text_lower = speech.lower()

                # Patient meldet, dass Nachname falsch erkannt wurde
                if (
                    "falsch" in text_lower
                    or "nicht richtig" in text_lower
                    or "stimmt nicht" in text_lower
                ):
                    sess["data"]["name_note"] = (
                        "Patient meldet: Nachname wurde falsch erkannt – bitte im Rückruf klären."
                    )
                    print("⚠️ Patient meldet: Name nicht richtig. Flag in Sheet gesetzt.")

                    # optional: trotzdem den erkannten Text speichern
                    sess["data"]["lastname"] = speech

                    sess["step"] += 1
                    next_step = sess["step"]

                    g = Gather(
                        input="speech",
                        timeout=10,
                        speech_timeout="auto",
                        action=url_for("twilio_ai", _external=True),
                        method="POST",
                        language="de-DE",
                    )
                    g.pause(length=1)

                    g.say(
                        "Alles klar. Ich notiere, dass wir Ihren Namen beim Rückruf klären. "
                        "Fahren wir fort.",
                        language="de-DE",
                    )

                    play_or_say_question(g, next_step)

                    resp.append(g)
                    return str(resp)

            # normaler Fall: Feld speichern
            sess["data"][key] = speech
            print(f"✅ {key} = {speech}")

        # nächste Frage
        sess["step"] += 1
        step = sess["step"]

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
            play_or_say_question(g, step)
            resp.append(g)
            return str(resp)

        # 3) fertig → speichern + Verabschiedung
        save_row(sess["data"])

        farewell_url = url_for("static_files", filename="de_farewell.mp3", _external=True)
        resp.play(farewell_url)

        SESSIONS.pop(call_sid, None)
        return str(resp)

    except Exception as e:
        print("❌ twilio_ai error:", e)
        resp.say(
            "Leider ist ein technischer Fehler aufgetreten. Bitte rufen Sie später erneut an.",
            language="de-DE",
        )
        return str(resp)


# =========================
# Init & Main
# =========================
init_sheets()
os.makedirs("static", exist_ok=True)
print("✅ SMA Voice – Sheets init beim Import ausgeführt.")

if __name__ == "__main__":
    print(f"📞 SMA Voice – Arztpraxis läuft lokal auf Port {PORT}")
    app.run(host="0.0.0.0", port=PORT)





























   











