"""Weekly summary report (used by the app button and the GitHub Actions cron)."""
from datetime import date

import pandas as pd

from core import ai
from core.config import THRESHOLD
from core.risk import department_summary, subject_summary


def build(subj: pd.DataFrame, students: pd.DataFrame) -> tuple[str, str, str]:
    """Return (subject, body, engine)."""
    depts = department_summary(students)
    subs = subject_summary(subj)
    top = students[students["at_risk"]].head(10)
    stats = {
        "students": len(students),
        "critical": int((students["status"] == "CRITICAL").sum()),
        "warning": int((students["status"] == "WARNING").sum()),
        "weak_or_falling": int(((students["weak_in"] != "") | (students["falling_in"] != "")).sum()),
        "avg_attendance": round(float(students["overall_pct"].mean()), 1),
        "departments": depts.to_dict("records"),
        "subjects": subs.head(8).to_dict("records"),
    }
    insights, engine = ai.summary_insights(stats)

    lines = [
        f"AttendGuard weekly summary: week of {date.today():%d %b %Y}", "",
        f"Students tracked: {stats['students']}  |  Below {THRESHOLD:g}%: {stats['critical']}  |  "
        f"Close to {THRESHOLD:g}%: {stats['warning']}  |  Weak/falling marks: {stats['weak_or_falling']}  |  "
        f"Avg attendance: {stats['avg_attendance']}%", "",
        "KEY INSIGHTS", insights, "",
        "DEPARTMENT-WISE RISK",
    ]
    for d in stats["departments"]:
        lines.append(f"- {d['department']}: {d['critical']} critical, {d['warning']} warning, "
                     f"avg attendance {d['avg_attendance']}%, avg risk {d['avg_risk']}")
    lines += ["", "TOP AT-RISK STUDENTS"]
    for i, s in enumerate(top.to_dict("records"), 1):
        flags = "; ".join(x for x in [
            f"below 85 in {s['below_85']}" if s["below_85"] else "",
            f"weak in {s['weak_in']}" if s["weak_in"] else "",
            f"falling in {s['falling_in']}" if s["falling_in"] else ""] if x)
        lines.append(f"{i}. {s['name']} ({s['roll_no']}, {s['department']}): overall {s['overall_pct']}%, "
                     f"risk {s['risk']:g}, needs {s['max_need']} classes in a row. {flags}")
    lines += ["", "Sent automatically by AttendGuard."]
    return f"AttendGuard weekly risk summary ({date.today():%d %b %Y})", "\n".join(lines), engine
