import os
import json
import time
import requests  # für ElevenLabs

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
# Flask & Config
# =========================
app = Flask(__name__, static_folder="static")
PORT = int(os.getenv("PORT", "10000"))

SHEET_ID = os.getenv("SHEET_ID", "")
CREDS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON", "")

ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY", "")
VOICE_ID_DE = os.getenv("VOICE_ID_DE", "")  # Markus Voice-ID

# { CallSid: {"step": int, "started": bool, "confirm_name": bool, "spell_mode": bool, "data": {...}} }
SESSIONS = {}

gc = None
ws = None


# =========================
# Google Sheets Setup
# =========================
def init_sheets():
    """
    Initialisiert Google Sheets und das Worksheet für SMA Voice.
    Versucht zuerst 'SMA Voice Reservation', dann 'Appointments'.
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

        # 1. Versuch: dein Tab-Name
        try:
            ws_name = "SMA Voice Reservation"
            ws_local = sh.worksheet(ws_name)
            print(f"✅ Worksheet '{ws_name}' gefunden.")
        except gspread.exceptions.WorksheetNotFound:
            # 2. Versuch: 'Appointments'
            try:
                ws_name = "Appointments"
                ws_local = sh.worksheet(ws_name)
                print(f"✅ Worksheet '{ws_name}' gefunden.")
            except gspread.exceptions.WorksheetNotFound:
                # 3. Neu anlegen mit deinem Namen
                ws_name = "SMA Voice Reservation"
                ws_local = sh.add_worksheet(title=ws_name, rows=1000, cols=10)
                ws_local.append_row(
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
                print(f"✅ Worksheet '{ws_name}' erstellt.")

        globals()["ws"] = ws_local

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
# ElevenLabs TTS (für dynamische Sätze)
# =========================
def eleven_tts(text: str, voice_id: str, out_path: str) -> bool:
    """
    Generiert mit ElevenLabs ein MP3 und speichert es unter out_path.
    Gibt True zurück, wenn es geklappt hat, sonst False.
    """
    try:
        if not (ELEVEN_API_KEY and voice_id):
            print("⚠️ ElevenLabs: API-Key oder Voice-ID fehlen.")
            return False

        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": ELEVEN_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.55,
                "similarity_boost": 0.85,
            },
        }

        r = requests.post(url, headers=headers, json=payload, timeout=25)
        if r.status_code == 200:
            with open(out_path, "wb") as f:
                f.write(r.content)
            print("✅ ElevenLabs TTS gespeichert:", out_path)
            return True

        print("❌ ElevenLabs error:", r.status_code, r.text)
        return False

    except Exception as e:
        print("❌ TTS exception:", e)
        return False


# =========================
# Helper
# =========================
def next_question_text(step: int) -> str:
    texts = [
        "Sind Sie bereits Patientin oder Patient bei uns? Bitte sagen Sie: ja, nein oder unsicher.",
        "Wie lautet Ihr Vor- und Nachname?",
        "Wie ist Ihr Geburtsdatum? Bitte nennen Sie Tag, Monat und Jahr.",
        "Worum geht es bei Ihrem Anliegen? Zum Beispiel Kontrolle, akute Beschwerden, Rezept oder etwas anderes.",
        "Für welches Datum wünschen Sie einen Termin? Sie können auch sagen: so bald wie möglich.",
        "Zu welcher Uhrzeit passt es Ihnen am besten? Morgens, nachmittags oder eine genaue Uhrzeit.",
        "Unter welcher Telefonnummer können wir Sie zurückrufen? Bitte sprechen Sie die Nummer deutlich aus.",
    ]
    return texts[step]


def question_audio_filename(step: int) -> str:
    """
    Ordnet jeden Schritt der richtigen MP3-Datei zu.
    WICHTIG: Dateinamen müssen GENAU so im static/-Ordner liegen.
    """
    files = [
        "de_q0_status.mp3",     # 0 – Status
        "de_q1_name.mp3",       # 1 – Name (kurze Version!)
        "de_q2_dob.mp3",        # 2 – Geburtsdatum
        "de_q3_reason.mp3",     # 3 – Anliegen
        "de_q4_date.mp3",       # 4 – DATUM
        "de_q5_uhrzeit.mp3",    # 5 – UHRZEIT
        "de_q6_phone.mp3",      # 6 – Telefon
    ]
    return files[step]


def play_or_say_question(gather: Gather, step: int):
    """
    Spielt die passende MP3 oder fallback mit Text.
    """
    filename = question_audio_filename(step)
    if os.path.exists(os.path.join("static", filename)):
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
    try:
        # Twilio kann Action sowohl als GET (mit Query-Params) als auch POST schicken
        if request.method == "POST":
            data = request.form
        else:
            data = request.args

        call_sid = data.get("CallSid", "NA")
        raw_speech = data.get("SpeechResult") or ""
        # leichte Bereinigung für komische Zeichen
        speech = raw_speech.strip().replace("’", "'").replace("`", "'")

        print("---- /twilio-ai ----")
        print("Method:", request.method)
        print("CallSid:", call_sid)
        print("SpeechResult (raw):", raw_speech)

        # Session holen / erstellen
        sess = SESSIONS.get(call_sid)
        if not sess:
            sess = {
                "started": False,
                "step": 0,
                "confirm_name": False,
                "spell_mode": False,
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

            # Begrüßung (Markus MP3)
            greet_url = url_for(
                "static_files", filename="de_greet.mp3", _external=True
            )
            g.play(greet_url)

            # Erste Frage (Status, Markus MP3)
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
        # 1.5) Name-Bestätigung (ja/nein/richtig/falsch)
        # =========================
        if sess.get("confirm_name"):
            if not speech:
                g = Gather(
                    input="speech",
                    timeout=8,
                    speech_timeout="auto",
                    action=url_for("twilio_ai", _external=True),
                    method="POST",
                    language="de-DE",
                )
                g.say(
                    "Bitte antworten Sie mit richtig oder falsch. Ist Ihr Name korrekt?",
                    language="de-DE",
                )
                resp.append(g)
                return str(resp)

            answer = speech.lower()
            current_name = sess["data"].get("name", "")

            if ("richtig" in answer) or ("ja" in answer):
                # Name bestätigt → weiter mit Geburtsdatum
                sess["confirm_name"] = False
                sess["spell_mode"] = False
                sess["step"] = 2  # 0=status, 1=name, 2=dob

                g = Gather(
                    input="speech",
                    timeout=10,
                    speech_timeout="auto",
                    action=url_for("twilio_ai", _external=True),
                    method="POST",
                    language="de-DE",
                )
                g.pause(length=1)
                play_or_say_question(g, sess["step"])
                resp.append(g)
                return str(resp)

            if ("falsch" in answer) or ("nein" in answer):
                # Name falsch → Spell-Mode
                sess["confirm_name"] = False
                sess["spell_mode"] = True
                sess["data"]["name"] = ""
                sess["step"] = 1  # zurück zur Namensfrage (Spell)

                spell_text = (
                    "Bitte buchstabieren Sie jetzt Ihren Vor- und Nachnamen "
                    "Buchstabe für Buchstabe. "
                    "Bei Umlauten wie ä, ö oder ü sagen Sie bitte a-e, o-e oder u-e."
                )
                file_name = f"de_spell_name_{call_sid}.mp3"
                out_path = os.path.join("static", file_name)
                used_eleven = eleven_tts(spell_text, VOICE_ID_DE, out_path)

                g = Gather(
                    input="speech",
                    timeout=15,
                    speech_timeout="auto",
                    action=url_for("twilio_ai", _external=True),
                    method="POST",
                    language="de-DE",
                )
                g.pause(length=1)

                if used_eleven:
                    g.play(url_for("static_files", filename=file_name, _external=True))
                else:
                    g.say(spell_text, language="de-DE")

                resp.append(g)
                return str(resp)

            # Weder ja/richtig noch nein/falsch → erneut Nachfrage
            g = Gather(
                input="speech",
                timeout=8,
                speech_timeout="auto",
                action=url_for("twilio_ai", _external=True),
                method="POST",
                language="de-DE",
            )
            g.say(
                f"Ich habe Ihren Namen als {current_name} verstanden. "
                "Bitte sagen Sie richtig, wenn das stimmt, oder falsch, wenn es nicht stimmt.",
                language="de-DE",
            )
            resp.append(g)
            return str(resp)

        # =========================
        # 2) Normale Fragen / Antworten sammeln
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

            play_or_say_question(g, step)
            resp.append(g)
            return str(resp)

        # Wenn was gesagt wurde → speichern
        if step < len(keys) and speech:
            key = keys[step]
            sess["data"][key] = speech
            print(f"✅ {key} = {speech}")

            # Spezieller Flow für 'name'
            if key == "name":
                # Wenn Spell-Mode aktiv war: spelled Name akzeptieren, NICHT erneut bestätigen
                if sess.get("spell_mode"):
                    sess["spell_mode"] = False
                else:
                    # Normaler Name → erst mal bestätigen lassen
                    sess["confirm_name"] = True

                    confirm_text = (
                        f"Ich habe verstanden: {speech}. "
                        "Ist das richtig? Bitte sagen Sie: richtig oder falsch."
                    )

                    file_name = f"de_confirm_name_{call_sid}.mp3"
                    out_path = os.path.join("static", file_name)

                    used_eleven = eleven_tts(confirm_text, VOICE_ID_DE, out_path)

                    g = Gather(
                        input="speech",
                        timeout=10,
                        speech_timeout="auto",
                        action=url_for("twilio_ai", _external=True),
                        method="POST",
                        language="de-DE",
                    )
                    g.pause(length=1)

                    if used_eleven:
                        g.play(
                            url_for(
                                "static_files",
                                filename=file_name,
                                _external=True,
                            )
                        )
                    else:
                        g.say(confirm_text, language="de-DE")

                    resp.append(g)
                    return str(resp)

        # Für alle anderen Felder normal weiter
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

            play_or_say_question(g, step)
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




























   











