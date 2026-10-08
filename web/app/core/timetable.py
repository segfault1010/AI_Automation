"""Teacher timetable -> free slots -> appointment bookings."""
from datetime import date, datetime, timedelta

import pandas as pd

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
SLOTS = ["09:00-10:00", "10:00-11:00", "11:15-12:15", "12:15-13:15", "14:00-15:00", "15:00-16:00"]

# Shared across all sessions of the running app (good enough for a demo; swap for a DB later).
BOOKINGS: list[dict] = []


def _clean(tt: pd.DataFrame) -> pd.DataFrame:
    tt = tt.copy()
    tt.columns = [str(c).strip().lower().replace(" ", "_") for c in tt.columns]
    for c in ("teacher", "day", "slot"):
        tt[c] = tt[c].astype(str).str.strip()
    tt["day"] = tt["day"].str[:3].str.title()
    return tt


def teachers(tt: pd.DataFrame) -> pd.DataFrame:
    return _clean(tt)[["teacher", "teacher_email", "department", "subject"]].drop_duplicates()


def week_grid(tt: pd.DataFrame, teacher: str) -> pd.DataFrame:
    """Day x slot grid with Class / Free for one teacher."""
    tt = _clean(tt)
    busy = tt[tt["teacher"] == teacher]
    grid = pd.DataFrame("🟢 Free", index=DAYS, columns=SLOTS)
    for _, r in busy.iterrows():
        if r["day"] in grid.index and r["slot"] in grid.columns:
            grid.loc[r["day"], r["slot"]] = f"📘 {r.get('subject', 'Class')}"
    return grid


def free_slots(tt: pd.DataFrame, teacher: str, days_ahead: int = 7,
               today: date | None = None) -> list[dict]:
    """Upcoming free (not teaching, not already booked) slots for a teacher."""
    tt = _clean(tt)
    busy = set(zip(tt.loc[tt["teacher"] == teacher, "day"], tt.loc[tt["teacher"] == teacher, "slot"]))
    booked = {(b["date"], b["slot"]) for b in BOOKINGS if b["teacher"] == teacher}
    today = today or date.today()
    out = []
    for i in range(1, days_ahead + 1):
        d = today + timedelta(days=i)
        day = d.strftime("%a")
        if day not in DAYS:
            continue
        for slot in SLOTS:
            if (day, slot) not in busy and (d.isoformat(), slot) not in booked:
                out.append({"date": d.isoformat(), "day": day, "slot": slot,
                            "label": f"{day} {d.strftime('%d %b')} · {slot}"})
    return out


def book(student: dict, teacher: dict, slot: dict, subject: str, note: str = "") -> dict:
    booking = {
        "booked_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "roll_no": student["roll_no"], "student": student["name"], "student_email": student["email"],
        "teacher": teacher["teacher"], "teacher_email": teacher["teacher_email"],
        "subject": subject, "date": slot["date"], "slot": slot["slot"], "note": note,
    }
    BOOKINGS.append(booking)
    return booking


def make_ics(booking: dict) -> str:
    start, end = booking["slot"].split("-")
    d = booking["date"].replace("-", "")
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//AttendGuard//EN", "METHOD:REQUEST",
        "BEGIN:VEVENT",
        f"UID:{booking['roll_no']}-{d}-{start.replace(':', '')}@attendguard",
        f"DTSTAMP:{stamp}",
        f"DTSTART;TZID=Asia/Kolkata:{d}T{start.replace(':', '')}00",
        f"DTEND;TZID=Asia/Kolkata:{d}T{end.replace(':', '')}00",
        f"SUMMARY:Academic support: {booking['student']} with {booking['teacher']} ({booking['subject']})",
        f"DESCRIPTION:{booking['note'] or 'Attendance / performance recovery meeting'}",
        f"ORGANIZER:mailto:{booking['teacher_email']}",
        f"ATTENDEE:mailto:{booking['student_email']}",
        "END:VEVENT", "END:VCALENDAR", "",
    ])
