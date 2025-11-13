import os
import json
import threading
import time

from flask import Flask, request, send_from_directory, url_for
from twilio.twiml.voice_response import VoiceResponse, Gather
import requests
import gspread
from google.oauth2.service_account import Credentials

# =====================================
# Flask Setup
# =====================================
app = Flask(__name__, static_folder="static")

# =====================================
# Config (ENV Variablen)
# =====================================
ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY", "")
VOICE_ID_DE    = os.getenv("VOICE_ID_DE", "")  # z.B. Sarah-Stimme
VOICE_ID_EN    = os.getenv("VOICE_ID_EN", "")  # optional, sonst leer lassen
SHEET_ID       = os.getenv("SHEET_ID", "")
CREDS_JSON     = os.getenv("GOOGLE_CREDENTIALS_JSON", "")
PORT           = int(os.getenv("PORT", "10000"))

# Simple in-memory call state (für Prototyp okay)
SESSIONS = {}  # { CallSid: {"lang": "de"/"en", "step": int, "data": {...}} }

# =====================================
# Google Sheets Setup
# =====================================
gc = None
sh = None
ws = None

def init_sheets():
    """Initialisiert Google Sheets Verbindung und Worksheet 'Reservations'."""
    global gc, sh, ws
    if not (CREDS_JSON and SHEET_ID):
        print("⚠️  GOOGLE_CREDENTIALS_JSON oder SHEET_ID nicht gesetzt – Sheets disabled.")
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
            ws.append_row([
                "Timestamp", "Lang", "Name", "PartySize",
                "Date", "Time", "Allergies", "Phone"
            ])
            print("✅ Worksheet 'Reservations' erstellt.")
    except Exception as e:
        print("❌ Fehler bei init_sheets:", e)

def ensure_sheets():
    """Stellt sicher, dass ws initialisiert ist, bevor wir schreiben."""
    global ws
    if ws is None:
        init_sheets()

def save_row(lang, name, party, rdate, rtime, allergies, phone):
    """Speichert eine Reservation in Google Sheets."""
    try:
        ensure_sheets()
        if ws is None:
            print("⚠️ ws ist None – Reservation wird nicht in Sheets geschrieben.")
            return
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        ws.append_row([ts, lang, name, party, rdate, rtime, allergies, phone])
        print("✅ Reservation in Sheets gespeichert.")
    except Exception as e:
        print("❌ Sheets save error:", e)

# =====================================
# ElevenLabs TTS (für Bestätigung)
# =====================================
def eleven_tts(text, voice_id, out_path):
    """Rendert Text zu MP3 via ElevenLabs und speichert in out_path."""
    if not ELEVEN_API_KEY or not voice_id:
        print("⚠️ ELEVEN_API_KEY oder VOICE_ID fehlt – TTS wird übersprungen.")
        return False

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
            "voice_settings": {
                "stability": 0.55,
                "similarity_boost": 0.85
            }
        }
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        if r.status_code == 200:
            with open(out_path, "wb") as f:
                f.write(r.content)
            print("✅ ElevenLabs TTS erfolgreich:", out_path)
            return True

        print("❌ ElevenLabs error:", r.status_code, r.text)
    except Exception as e:
        print("❌ TTS exception:", e)

    return False

# =====================================
# Text Helper
# =====================================
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

# =====================================
# Static & Health
# =====================================
@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(app.static_folder, filename)

@app.route("/health")
def health():
    return "ok", 200

# =====================================
# Twilio Webhook
# =====================================
@app.route("/twilio-ai", methods=["POST"])
def twilio_ai():
    call_sid = request.form.get("CallSid", "NA")
    digits = request.form.get("Digits")
    speech = (request.form.get("SpeechResult") or "").strip()

    print("---- /twilio-ai ----")
    print("CallSid:", call_sid)
    print("Digits:", digits)
    print("SpeechResult:", speech)
    print("Form:", dict(request.form))

    # Session holen / erstellen
    sess = SESSIONS.get(call_sid)
    if not sess:
        sess = {
            "lang": None,
            "step": -1,
            "data": {
                "name": "",
                "party": "",
                "date": "",
                "time": "",
                "allergies": "",
                "phone": ""
            }
        }
        SESSIONS[call_sid] = sess

    resp = VoiceResponse()

    # =================================
    # 1) Sprachwahl
    # =================================
    if not sess["lang"]:
        # noch keine Sprache gesetzt
        if not digits:
            # Erstes Mal oder kein Input → Menü
            g = Gather(
                input="dtmf speech",
                num_digits=1,
                timeout=5,
                action=url_for("twilio_ai", _external=True),
                method="POST",
                language="de-DE"  # Sprache für STT, hier egal, wir nutzen DTMF
            )
            g.say(
                "Willkommen beim Restaurant Viadukt Zürich. Für Deutsch drücken Sie die 1.",
                language="de-DE"
            )
            g.pause(length=1)
            g.say("For English, press 2.", language="en-US")
            resp.append(g)

            # falls NICHTS kommt nach dem Gather:
            resp.say("Kein Input erkannt. Auf Wiedersehen.", language="de-DE")
            return str(resp)

        # Digit wurde übergeben
        if digits == "1":
            sess["lang"] = "de"
        elif digits == "2":
            sess["lang"] = "en"
        else:
            resp.say("Ungültige Eingabe. Bitte erneut versuchen.", language="de-DE")
            return str(resp)

        lang_code = "de-DE" if sess["lang"] == "de" else "en-US"

        # Begrüßung + erste Frage
        resp.say(greet(sess["lang"]), language=lang_code)
        sess["step"] = 0

        g = Gather(
            input="speech",
            timeout=8,
            action=url_for("twilio_ai", _external=True),
            method="POST",
            language=lang_code
        )
        g.say(next_question(sess["lang"], sess["step"]), language=lang_code)
        resp.append(g)
        return str(resp)

    # =================================
    # 2) Antworten einsammeln
    # =================================
    if sess["step"] >= 0:
        lang_code = "de-DE" if sess["lang"] == "de" else "en-US"
        keys = ["name", "party", "date", "time", "allergies", "phone"]

        # sind wir noch mitten in den Fragen?
        if sess["step"] < len(keys):
            # Wenn nix erkannt → gleiche Frage wiederholen
            if not speech:
                g = Gather(
                    input="speech",
                    timeout=8,
                    action=url_for("twilio_ai", _external=True),
                    method="POST",
                    language=lang_code
                )
                if sess["lang"] == "de":
                    g.say(
                        "Entschuldigung, ich habe Sie nicht verstanden. "
                        + next_question(sess["lang"], sess["step"]),
                        language=lang_code
                    )
                else:
                    g.say(
                        "Sorry, I didn't catch that. "
                        + next_question(sess["lang"], sess["step"]),
                        language=lang_code
                    )
                resp.append(g)
                return str(resp)

            # Etwas wurde erkannt → speichern
            key = keys[sess["step"]]
            sess["data"][key] = speech
            print(f"✅ Gespeichert: {key} = {speech}")

            # nächste Frage
            sess["step"] += 1

        # Haben wir noch Fragen offen?
        if sess["step"] < len(keys):
            g = Gather(
                input="speech",
                timeout=8,
                action=url_for("twilio_ai", _external=True),
                method="POST",
                language=lang_code
            )
            g.say(next_question(sess["lang"], sess["step"]), language=lang_code)
            resp.append(g)
            return str(resp)

        # =================================
        # 3) Fertig gesammelt → speichern + bestätigen
        # =================================
        d = sess["data"]
        save_row(
            sess["lang"],
            d["name"],
            d["party"],
            d["date"],
            d["time"],
            d["allergies"],
            d["phone"],
        )

        resp.say(thanks_line(sess["lang"]), language=lang_code)

        # Bestätigungstext bauen
        if sess["lang"] == "de":
            conf = (
                f"Reservierung für {d['name']}, {d['party']} Personen, am {d['date']} um {d['time']}. "
                f"Allergien: {d['allergies'] or 'keine angegeben'}. "
                f"Wir sind erreichbar unter der Nummer {d['phone']}. "
                f"{open_hours('de')} {farewell('de')}"
            )
            voice_id = VOICE_ID_DE
            out = "static/confirm_de.mp3"
        else:
            conf = (
                f"Reservation for {d['name']}, {d['party']} people, on {d['date']} at {d['time']}. "
                f"Allergies: {d['allergies'] or 'none provided'}. "
                f"We can reach you at {d['phone']}. "
                f"{open_hours('en')} {farewell('en')}"
            )
            voice_id = VOICE_ID_EN or VOICE_ID_DE  # fallback
            out = "static/confirm_en.mp3"

        # TTS im Hintergrund rendern
        def render_and_log():
            ok = eleven_tts(conf, voice_id, out)
            print("TTS ready:", ok, "->", out)

        threading.Thread(target=render_and_log, daemon=True).start()
        time.sleep(1)  # kleiner Buffer

        file_url = f"https://{request.host}/{out}"
        print("▶️ Spiele Bestätigung:", file_url)
        resp.play(file_url)

        # Session cleanup
        try:
            del SESSIONS[call_sid]
        except Exception as e:
            print("Session cleanup error:", e)

        return str(resp)

    # Fallback
    resp.say("Ein Fehler ist aufgetreten. Bitte versuchen Sie es später erneut.", language="de-DE")
    return str(resp)

# =====================================
# Main (lokal)
# =====================================
if __name__ == "__main__":
    os.makedirs("static", exist_ok=True)
    init_sheets()
    print(f"📞 SMA Voice AI läuft auf Port {PORT}")
    app.run(host="0.0.0.0", port=PORT)



















   











