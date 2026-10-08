"""Email (Gmail SMTP) and phone calls (Twilio) with safe demo fallbacks."""
import smtplib
from datetime import datetime
from email.message import EmailMessage
from xml.sax.saxutils import escape

from core.config import MAX_CALLS_PER_RUN, THRESHOLD, secret

# Shared across sessions of the running app.
EMAIL_LOG: list[dict] = []
CALL_LOG: list[dict] = []
CALLED: set[str] = set()


def email_mode() -> str:
    if secret("SMTP_USER") and secret("SMTP_APP_PASSWORD"):
        return "Gmail SMTP"
    return "Outbox only (SMTP not set)"


def call_mode() -> str:
    if secret("TWILIO_ACCOUNT_SID") and secret("TWILIO_AUTH_TOKEN") and secret("TWILIO_FROM"):
        return "Twilio"
    return "Simulated (Twilio not set)"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def send_emails(messages: list[dict], redirect_to: str | None = None) -> list[dict]:
    """messages: [{to, subject, body, kind, ics?}]. One SMTP connection for the whole batch."""
    redirect_to = redirect_to if redirect_to is not None else secret("DEMO_INBOX")
    user, pwd = secret("SMTP_USER"), secret("SMTP_APP_PASSWORD")
    server, results = None, []
    if user and pwd and messages:
        try:
            server = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20)
            server.login(user, pwd)
        except Exception as e:
            server = None
            login_error = f"failed: SMTP login ({e.__class__.__name__})"
    for m in messages:
        actual = redirect_to or m["to"]
        rec = {"time": _now(), "kind": m.get("kind", ""), "to": m["to"], "delivered_to": actual,
               "subject": m["subject"], "body": m["body"]}
        if not actual:
            rec["status"] = "skipped: no email address"
        elif server:
            msg = EmailMessage()
            msg["From"], msg["To"] = f"AttendGuard <{user}>", actual
            msg["Subject"] = (f"[DEMO → {m['to']}] " if redirect_to else "") + m["subject"]
            msg.set_content(m["body"])
            if m.get("ics"):
                msg.add_attachment(m["ics"].encode(), maintype="text", subtype="calendar",
                                   filename="appointment.ics")
            try:
                server.send_message(msg)
                rec["status"] = "sent"
            except Exception as e:
                rec["status"] = f"failed: {e.__class__.__name__}"
        elif user and pwd:
            rec["status"] = login_error
        else:
            rec["status"] = "outbox (SMTP not configured)"
        EMAIL_LOG.append(rec)
        results.append(rec)
    if server:
        server.quit()
    return results


def call_script(student: dict) -> str:
    first = (student.get("name") or "student").split()[0]
    return (f"Hello {first}. This is an automated call from AttendGuard, your college attendance system. "
            f"Your attendance in {student.get('below_85') or 'one or more subjects'} has fallen below "
            f"{THRESHOLD:g} percent. To recover, you must attend the next {student.get('max_need', 0)} "
            "classes without missing any. A detailed email has been sent to you. Please book a meeting "
            "with your subject teacher. Thank you.")


def place_call(student: dict) -> dict:
    phone = str(student.get("phone") or "")
    actual = secret("DEMO_PHONE") or phone
    msg = call_script(student)
    rec = {"time": _now(), "roll_no": student["roll_no"], "name": student["name"], "phone": phone,
           "dialled": actual, "message": msg}
    if call_mode() != "Twilio":
        rec["status"] = "simulated"
    else:
        try:
            from twilio.rest import Client

            client = Client(secret("TWILIO_ACCOUNT_SID"), secret("TWILIO_AUTH_TOKEN"))
            say = f'<Say voice="alice" language="en-IN">{escape(msg)}</Say>'
            call = client.calls.create(to=actual, from_=secret("TWILIO_FROM"),
                                       twiml=f"<Response>{say}<Pause length=\"1\"/>{say}</Response>")
            rec["status"] = f"calling ({call.sid[:10]}…)"
        except Exception as e:
            rec["status"] = f"failed: {str(e)[:80]}"
    CALL_LOG.append(rec)
    return rec


def auto_call(students) -> list[dict]:
    """Call every student who is below the threshold and has not been called yet."""
    out, real_calls = [], 0
    critical = students[students["status"] == "CRITICAL"].sort_values("risk", ascending=False)
    for _, s in critical.iterrows():
        s = s.to_dict()
        if s["roll_no"] in CALLED:
            continue
        CALLED.add(s["roll_no"])
        if call_mode() == "Twilio" and real_calls >= MAX_CALLS_PER_RUN:
            rec = {"time": _now(), "roll_no": s["roll_no"], "name": s["name"], "phone": s["phone"],
                   "dialled": "-", "message": call_script(s),
                   "status": f"queued (demo cap {MAX_CALLS_PER_RUN} live calls/run)"}
            CALL_LOG.append(rec)
        else:
            rec = place_call(s)
            real_calls += rec["status"].startswith("calling")
        out.append(rec)
    return out
