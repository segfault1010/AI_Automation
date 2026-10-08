"""LLM writer: Claude -> Gemini -> template fallback, so the demo never breaks."""
import json

from core.config import THRESHOLD, secret

SYSTEM = (
    "You are AttendGuard, a caring but direct academic advisor at an Indian engineering college. "
    "Write short, specific, encouraging messages to students and faculty. Use the exact numbers "
    "given. Plain text only: no markdown, no subject line, no placeholders."
)


def engine_name() -> str:
    if secret("ANTHROPIC_API_KEY"):
        return f"Claude ({secret('CLAUDE_MODEL', 'claude-opus-5-5')})"
    if secret("GEMINI_API_KEY"):
        return "Gemini"
    return "Template (no AI key set)"


def _claude(prompt: str) -> str | None:
    import anthropic

    client = anthropic.Anthropic(api_key=secret("ANTHROPIC_API_KEY"), timeout=60, max_retries=1)
    model = secret("CLAUDE_MODEL", "claude-opus-5-5")
    base = dict(model=model, max_tokens=8000, system=SYSTEM, output_config={"effort": "low"},
                messages=[{"role": "user", "content": prompt}])
    try:  # server-side refusal fallback (beta); retry plainly if this SDK/model rejects it
        resp = client.beta.messages.create(**base, betas=["server-side-fallback-2026-07-01"],
                                           fallbacks="default")
    except (TypeError, anthropic.BadRequestError):
        resp = client.messages.create(**base)
    if resp.stop_reason == "refusal":
        return None
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    return text or None


def _gemini(prompt: str) -> str | None:
    from google import genai

    client = genai.Client(api_key=secret("GEMINI_API_KEY"))
    resp = client.models.generate_content(model="gemini-2.5-flash", contents=f"{SYSTEM}\n\n{prompt}")
    return (resp.text or "").strip() or None


def generate(prompt: str) -> tuple[str | None, str]:
    """Return (text, engine). text is None when no AI is available or every call failed."""
    if secret("ANTHROPIC_API_KEY"):
        try:
            text = _claude(prompt)
            if text:
                return text, "Claude"
        except Exception as e:  # network, auth, rate limit: fall through
            print("Claude error:", e)
    if secret("GEMINI_API_KEY"):
        try:
            text = _gemini(prompt)
            if text:
                return text, "Gemini"
        except Exception as e:
            print("Gemini error:", e)
    return None, "Template"


# ---------- Student warning email ----------

def _student_facts(student: dict, rows: list[dict], booking_link: str) -> dict:
    return {
        "student": student["name"], "roll_no": student["roll_no"], "department": student["department"],
        "overall_attendance_pct": student["overall_pct"], "required_pct": THRESHOLD,
        "subjects": [{
            "subject": r["subject"], "attendance_pct": r["att_pct"], "status": r["status"],
            "must_attend_in_a_row": r["need_in_row"], "can_still_miss": r["can_miss"],
            "test_scores": r["scores"], "weak_marks": r["weak"], "falling_marks": r["falling"],
            "teacher": r["teacher"],
        } for r in rows if r["at_risk"]],
        "booking_link": booking_link,
    }


def student_email(student: dict, rows: list[dict], booking_link: str) -> tuple[str, str, str]:
    """Return (subject, body, engine)."""
    facts = _student_facts(student, rows, booking_link)
    subject = f"AttendGuard alert: action needed on your attendance/marks ({student['roll_no']})"
    prompt = (
        "Write a personal warning email to this student (max 170 words). Address them by first name. "
        "For each listed subject state the attendance % and, if below the required %, exactly how many "
        "classes they must attend in a row to recover; if close, how many they can still miss. Mention "
        "weak or falling test scores with one concrete study tip each. Encourage them to book a slot "
        "with the subject teacher using the booking link. Sign off as 'AttendGuard, on behalf of your "
        f"Faculty Adviser'.\n\nFACTS:\n{json.dumps(facts, indent=1)}"
    )
    text, engine = generate(prompt)
    return subject, text or _student_template(facts), engine


def _student_template(f: dict) -> str:
    first = f["student"].split()[0] if f["student"] else "Student"
    lines = [f"Dear {first},", "",
             f"Your overall attendance is {f['overall_attendance_pct']}% (required: {f['required_pct']:g}%). "
             "Here is where you stand:"]
    for s in f["subjects"]:
        line = f"- {s['subject']}: {s['attendance_pct']}%"
        if s["status"] == "CRITICAL":
            line += f" (below {f['required_pct']:g}%): attend the next {s['must_attend_in_a_row']} classes in a row to recover"
        elif s["status"] == "WARNING":
            line += f" (close to the limit): you can miss only {s['can_still_miss']} more"
        if s["weak_marks"] or s["falling_marks"]:
            line += f". Test scores {s['test_scores']} ({'weak' if s['weak_marks'] else 'falling'}): revise with your teacher {s['teacher']}"
        lines.append(line)
    if f["booking_link"]:
        lines += ["", f"Book a 1:1 slot with your subject teacher here: {f['booking_link']}"]
    lines += ["", "You can turn this around. Start with the very next class.", "",
              "AttendGuard, on behalf of your Faculty Adviser"]
    return "\n".join(lines)


# ---------- Weekly summary narrative ----------

def summary_insights(stats: dict) -> tuple[str, str]:
    prompt = (
        "You are writing the 'Key insights' section of a weekly attendance-risk report for the HOD. "
        "Give 4-5 short bullet points (use '- ') with the most important patterns and one recommended "
        f"action each. Data:\n{json.dumps(stats, indent=1, default=str)}"
    )
    text, engine = generate(prompt)
    if text:
        return text, engine
    depts = stats.get("departments", [])
    worst = depts[0]["department"] if depts else "N/A"
    subs = stats.get("subjects", [])
    worst_sub = f"{subs[0]['subject']} ({subs[0]['department']})" if subs else "N/A"
    return "\n".join([
        f"- {stats['critical']} students are below {THRESHOLD:g}% and {stats['warning']} are close to it.",
        f"- {worst} has the highest average risk; prioritise adviser check-ins there.",
        f"- {worst_sub} has the most students below {THRESHOLD:g}%; ask the subject teacher to follow up.",
        f"- {stats['weak_or_falling']} students show weak or falling marks; schedule remedial sessions.",
    ]), "Template"
