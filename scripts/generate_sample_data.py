"""Generate the deterministic "Full demo" dataset into sample_data/.

    python scripts/generate_sample_data.py            # seed 42 -> sample_data/
    python scripts/generate_sample_data.py --seed 7 --out /tmp/demo

Files (all share roll_no / subject_code / teacher ids):
  students.csv, attendance.csv (long, one row per student per session), attendance_summary.xlsx (wide),
  test_results.csv, teacher_timetable.csv, templates/*.csv, traps.json (deliberate data-quality issues).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import random
import re
import zipfile
from datetime import date, timedelta
from pathlib import Path

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
PERIODS = [("09:00", "10:00"), ("10:00", "11:00"), ("11:15", "12:15"),
           ("12:15", "13:15"), ("14:00", "15:00"), ("15:00", "16:00")]
SEMESTER_START = date(2026, 7, 6)          # Monday
WEEKS = 12
HOLIDAYS = {date(2026, 8, 26), date(2026, 9, 14)}  # Onam (Wed), Ganesh Chaturthi (Mon)
SECTIONS = ["A", "B"]
STUDENTS_PER_SECTION = 30
DEPTS: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "CSE": ("CS", [("CS301", "Data Structures"), ("CS302", "Database Systems"), ("CS303", "Operating Systems"),
                   ("CS304", "Computer Networks"), ("CS305", "Software Engineering"), ("CS306", "Theory of Computation")]),
    "ECE": ("EC", [("EC301", "Signals & Systems"), ("EC302", "Digital Electronics"), ("EC303", "Microprocessors"),
                   ("EC304", "Communication Theory"), ("EC305", "Control Systems"), ("EC306", "Electromagnetics")]),
    "ME": ("ME", [("ME301", "Thermodynamics"), ("ME302", "Fluid Mechanics"), ("ME303", "Machine Design"),
                  ("ME304", "Manufacturing Technology"), ("ME305", "Heat Transfer"), ("ME306", "Kinematics of Machines")]),
    "EEE": ("EE", [("EE301", "Electrical Machines"), ("EE302", "Power Systems"), ("EE303", "Power Electronics"),
                   ("EE304", "Control Engineering"), ("EE305", "Measurements & Instrumentation"), ("EE306", "Circuit Theory")]),
    "Civil": ("CV", [("CV301", "Structural Analysis"), ("CV302", "Geotechnical Engineering"), ("CV303", "Surveying"),
                     ("CV304", "Transportation Engineering"), ("CV305", "Environmental Engineering"),
                     ("CV306", "Concrete Technology")]),
}
FIRST = ["Aarav", "Diya", "Rohan", "Ananya", "Karthik", "Meera", "Vivek", "Ishita", "Arjun", "Sneha", "Rahul", "Pooja",
         "Aditya", "Nivetha", "Siddharth", "Kavya", "Harish", "Shreya", "Varun", "Lavanya", "Nikhil", "Divya",
         "Pranav", "Swathi", "Akash", "Deepika", "Manoj", "Keerthana", "Gokul", "Priyanka", "Sanjay", "Aishwarya",
         "Vignesh", "Harini", "Naveen", "Janani", "Surya", "Revathi", "Ashwin", "Bhavana"]
LAST = ["Sharma", "Iyer", "Reddy", "Nair", "Menon", "Rao", "Kumar", "Pillai", "Gupta", "Krishnan", "Subramanian",
        "Patel", "Das", "Bose", "Joshi", "Venkatesh", "Raman", "Chandran", "Balaji", "Mishra"]
TEACHER_FIRST = ["Priya", "Arjun", "Kavitha", "Rahul", "Suresh", "Anitha", "Vikram", "Divya", "Ganesh", "Lakshmi",
                 "Karthik", "Sneha", "Ramesh", "Meena", "Anand", "Padma", "Srinivasan", "Geetha", "Murali", "Uma",
                 "Rajesh", "Kalpana", "Senthil", "Revathi", "Balaji"]
TESTS = [("Quiz1", 10, 2), ("CAT1", 50, 4), ("Quiz2", 10, 6), ("CAT2", 50, 8), ("Assignment", 20, 10)]  # (name, max, week)
# Category mix: ~70% safe, ~10% borderline, ~10% at risk, ~5% critical, ~5% good attendance but falling marks.
CATEGORY_SHARE = [("safe", 0.70), ("borderline", 0.10), ("at_risk", 0.10), ("critical", 0.05), ("falling", 0.05)]
ATT_RANGE = {"safe": (0.91, 0.99), "borderline": (0.845, 0.86), "at_risk": (0.68, 0.82),
             "critical": (0.50, 0.63), "falling": (0.91, 0.98)}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", ".", text.lower()).strip(".")


def make_teachers(rng: random.Random) -> list[dict]:
    teachers, n = [], 0
    for dept in DEPTS:
        for _ in range(5):
            first = TEACHER_FIRST[n]
            name = f"{rng.choice(['Dr.', 'Prof.'])} {first} {rng.choice(LAST)}"
            n += 1
            teachers.append({"teacher_id": f"T{n:02d}", "teacher_name": name, "department": dept,
                             "email": f"{slug(first)}.t{n:02d}@example.edu"})
    return teachers


def build_timetable(rng: random.Random, teachers: list[dict]) -> tuple[list[dict], dict]:
    """Conflict-free weekly timetable. Returns (rows, schedule[(dept, section, code)] -> [(day, period)])."""
    for _attempt in range(200):
        busy_teacher: dict[str, set] = {t["teacher_id"]: set() for t in teachers}
        schedule, assign, ok = {}, {}, True
        for dept, (_, subjects) in DEPTS.items():
            dept_teachers = [t for t in teachers if t["department"] == dept]
            pairs = [(sec, code) for sec in SECTIONS for code, _ in subjects]
            for i, (sec, code) in enumerate(pairs):
                assign[(dept, sec, code)] = dept_teachers[i % len(dept_teachers)]
            for sec in SECTIONS:
                busy_section: set = set()
                for j, (code, _) in enumerate(subjects):
                    teacher = assign[(dept, sec, code)]
                    # The first subject meets 5x/week on Tue/Thu/Fri only (no holidays) -> exactly 60 classes.
                    want, days = (5, ["Tue", "Thu", "Fri"]) if j == 0 else (4, DAYS)
                    slots = [(d, p) for d in days for p in range(1, 7)
                             if (d, p) not in busy_section and (d, p) not in busy_teacher[teacher["teacher_id"]]]
                    rng.shuffle(slots)
                    chosen, used_days = [], set()
                    for d, p in slots:  # spread across days first
                        if d not in used_days or len(used_days) == len(days):
                            chosen.append((d, p)); used_days.add(d)
                        if len(chosen) == want:
                            break
                    if len(chosen) < want:
                        ok = False; break
                    schedule[(dept, sec, code)] = sorted(chosen, key=lambda x: (DAYS.index(x[0]), x[1]))
                    busy_section.update(chosen); busy_teacher[teacher["teacher_id"]].update(chosen)
                if not ok:
                    break
            if not ok:
                break
        if ok:
            break
    else:
        raise RuntimeError("could not build a conflict-free timetable")

    teaching = {}
    for (dept, sec, code), slots in schedule.items():
        for d, p in slots:
            teaching[(assign[(dept, sec, code)]["teacher_id"], d, p)] = (code, sec)
    rows = []
    for t in teachers:
        for d in DAYS:
            for p, (start, end) in enumerate(PERIODS, 1):
                code, sec = teaching.get((t["teacher_id"], d, p), ("", ""))
                rows.append({"teacher_id": t["teacher_id"], "teacher_name": t["teacher_name"], "email": t["email"],
                             "department": t["department"], "day": d, "period": p, "start_time": start,
                             "end_time": end, "subject_code": code, "section": sec,
                             "is_free": "false" if code else "true"})
    return rows, {"schedule": schedule, "assign": assign}


def class_dates(slots: list[tuple[str, int]]) -> list[tuple[date, int]]:
    out = []
    for w in range(WEEKS):
        monday = SEMESTER_START + timedelta(weeks=w)
        for d, p in slots:
            day = monday + timedelta(days=DAYS.index(d))
            if day not in HOLIDAYS:
                out.append((day, p))
    return sorted(out)


def categories(rng: random.Random, n: int) -> list[str]:
    counts = [(c, round(n * s)) for c, s in CATEGORY_SHARE]
    cats = [c for c, k in counts for _ in range(k)]
    cats += ["safe"] * (n - len(cats))
    rng.shuffle(cats)
    return cats


def generate(seed: int = 42) -> dict:
    rng = random.Random(seed)
    teachers = make_teachers(rng)
    tt_rows, plan = build_timetable(rng, teachers)
    schedule, assign = plan["schedule"], plan["assign"]

    students, att_rows, test_rows, summary = [], [], [], {}
    total = len(DEPTS) * len(SECTIONS) * STUDENTS_PER_SECTION
    cats = categories(rng, total)
    low_marks = set()
    idx, exact_done, phone_n = 0, False, 0
    for dept, (dcode, subjects) in DEPTS.items():
        for sec in SECTIONS:
            adviser = assign[(dept, sec, subjects[1][0])]
            for k in range(1, STUDENTS_PER_SECTION + 1):
                cat = cats[idx]; idx += 1
                roll = f"23{dcode}{sec}{k:03d}"
                first, last = rng.choice(FIRST), rng.choice(LAST)
                phone_n += 1
                if cat in ("at_risk", "critical") and rng.random() < 0.25:
                    low_marks.add(roll)
                students.append({"roll_no": roll, "name": f"{first} {last}", "department": dept, "year": 3,
                                 "section": sec, "email": f"{slug(first)}.{roll.lower()}@example.edu",
                                 "phone": f"+91 90000 {phone_n:05d}", "faculty_adviser": adviser["teacher_name"],
                                 "adviser_email": adviser["email"], "_category": cat})
                rate = rng.uniform(*ATT_RANGE[cat])
                ability = rng.uniform(0.62, 0.9)
                for j, (code, name) in enumerate(subjects):
                    sessions = class_dates(schedule[(dept, sec, code)])
                    held = len(sessions)
                    if cat == "borderline" and not exact_done and j == 0 and held == 60:
                        present_n, exact_done = 51, True            # exactly 85.0% edge case
                        students[-1]["_exact85"] = code
                    elif students[-1].get("_exact85"):
                        present_n = round(held * rng.uniform(0.92, 0.98))
                    else:
                        r = min(1.0, max(0.0, rate + rng.uniform(-0.01, 0.01)))
                        present_n = round(held * r)
                    absent = set(rng.sample(range(held), held - present_n))
                    for i, (day, period) in enumerate(sessions):
                        if i in absent:
                            status = "ML" if rng.random() < 0.1 else "A"
                        else:
                            status = "OD" if rng.random() < 0.03 else "P"
                        att_rows.append({"roll_no": roll, "date": day.isoformat(), "subject_code": code,
                                         "subject_name": name, "period": period, "status": status})
                    summary[(roll, code)] = (present_n, held)
                    # Marks
                    cat1 = rng.uniform(0.65, 0.92) if cat == "falling" else ability + rng.uniform(-0.03, 0.03)
                    for tname, mx, week in TESTS:
                        if roll in low_marks:
                            frac = rng.uniform(0.18, 0.38)
                        elif cat == "falling":
                            frac = cat1 if tname in ("Quiz1", "CAT1") else cat1 * rng.uniform(0.55, 0.72)
                        else:
                            frac = (cat1 if tname == "CAT1" else ability) + rng.uniform(-0.03, 0.03)
                        frac = min(1.0, max(0.0, frac))
                        tdate = SEMESTER_START + timedelta(weeks=week, days=2)
                        test_rows.append({"roll_no": roll, "subject_code": code, "test_name": tname,
                                          "max_marks": mx, "marks_obtained": round(frac * mx, 1),
                                          "test_date": tdate.isoformat()})

    # ---- deliberate data-quality traps (documented in traps.json) ----
    traps = {}
    dup = att_rows[10]
    att_rows.insert(11, dict(dup)); traps["duplicate_attendance_row"] = dup
    ws_row = next(r for r in att_rows if r["roll_no"] == "23CSA005")
    ws_row["roll_no"] = " 23csa005 "; traps["messy_roll_no"] = " 23csa005 "
    dd_row = att_rows[500]
    d = date.fromisoformat(dd_row["date"]); dd_row["date"] = d.strftime("%d-%m-%Y")
    traps["ddmmyyyy_date"] = dd_row["date"]
    test_rows[7]["marks_obtained"] = ""; traps["missing_marks"] = {k: test_rows[7][k] for k in ("roll_no", "subject_code", "test_name")}
    test_rows.append({"roll_no": "23XXZ999", "subject_code": "CS301", "test_name": "CAT1", "max_marks": 50,
                      "marks_obtained": 31, "test_date": (SEMESTER_START + timedelta(weeks=4, days=2)).isoformat()})
    traps["unknown_roll_no"] = "23XXZ999"
    exact = next(s for s in students if s.get("_exact85"))
    traps["exact_85_percent"] = {"roll_no": exact["roll_no"], "subject_code": exact["_exact85"]}
    return {"teachers": teachers, "timetable": tt_rows, "students": students, "attendance": att_rows,
            "tests": test_rows, "summary": summary, "traps": traps}


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader(); w.writerows(rows)


def write_xlsx_deterministic(path: Path, header: list[str], rows: list[list]) -> None:
    """openpyxl stamps the current time into the file; normalise it so reruns are byte-identical."""
    from openpyxl import Workbook

    wb = Workbook(); ws = wb.active; ws.title = "attendance_summary"
    ws.append(header)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO(); wb.save(buf)
    src = zipfile.ZipFile(io.BytesIO(buf.getvalue()))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for name in sorted(src.namelist()):
            data = src.read(name)
            if name == "docProps/core.xml":
                data = re.sub(rb"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z", b"2026-01-01T00:00:00Z", data)
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            dst.writestr(info, data)
    path.write_bytes(out.getvalue())


def write_all(data: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "templates").mkdir(exist_ok=True)
    s_fields = ["roll_no", "name", "department", "year", "section", "email", "phone", "faculty_adviser", "adviser_email"]
    a_fields = ["roll_no", "date", "subject_code", "subject_name", "period", "status"]
    t_fields = ["roll_no", "subject_code", "test_name", "max_marks", "marks_obtained", "test_date"]
    tt_fields = ["teacher_id", "teacher_name", "email", "department", "day", "period", "start_time", "end_time",
                 "subject_code", "section", "is_free"]
    write_csv(out / "students.csv", data["students"], s_fields)
    write_csv(out / "attendance.csv", data["attendance"], a_fields)
    write_csv(out / "test_results.csv", data["tests"], t_fields)
    write_csv(out / "teacher_timetable.csv", data["timetable"], tt_fields)

    codes = [c for _, subs in DEPTS.values() for c, _ in subs]
    header = ["roll_no"] + [f"{c}_{k}" for c in codes for k in ("attended", "total")]
    rows = []
    for s in data["students"]:
        row = [s["roll_no"]]
        for c in codes:
            a, t = data["summary"].get((s["roll_no"], c), (None, None))
            row += [a, t]
        rows.append(row)
    write_xlsx_deterministic(out / "attendance_summary.xlsx", header, rows)

    clean_att = [r for r in data["attendance"] if r["roll_no"] == r["roll_no"].strip().upper()]
    write_csv(out / "templates" / "students.csv", data["students"][:2], s_fields)
    write_csv(out / "templates" / "attendance.csv", clean_att[:2], a_fields)
    write_csv(out / "templates" / "test_results.csv", data["tests"][:2], t_fields)
    write_csv(out / "templates" / "teacher_timetable.csv", data["timetable"][:2], tt_fields)
    with open(out / "templates" / "attendance_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n"); w.writerow(header[:5]); w.writerows(r[:5] for r in rows[:2])
    (out / "traps.json").write_text(json.dumps(data["traps"], indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "sample_data"))
    args = ap.parse_args()
    data = generate(args.seed)
    write_all(data, Path(args.out))
    print(f"Wrote {len(data['students'])} students, {len(data['attendance'])} attendance rows, "
          f"{len(data['tests'])} test rows, {len(data['timetable'])} timetable rows to {args.out}")


if __name__ == "__main__":
    main()
