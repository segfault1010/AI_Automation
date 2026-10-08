"""Load the generated Full demo (sample_data/) into the tables the risk engine uses, logging every fix."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

PRESENT = {"P", "OD"}  # on-duty counts as attended; ML and A count as absent
MAJOR_TESTS = ["CAT1", "CAT2"]


def _norm_roll(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.upper()


def _parse_dates(s: pd.Series) -> tuple[pd.Series, int]:
    iso = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
    dmy = pd.to_datetime(s, format="%d-%m-%Y", errors="coerce")
    fixed = int((iso.isna() & dmy.notna()).sum())
    return iso.fillna(dmy), fixed


def load_full_demo(folder: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict]]:
    """Return (attendance summary, marks wide, timetable, cleaning log)."""
    log: list[dict] = []

    def note(file: str, fix: str, count: int) -> None:
        if count:
            log.append({"file": file, "fix": fix, "rows": count})

    students = pd.read_csv(folder / "students.csv", dtype=str)
    students["roll_no"] = _norm_roll(students["roll_no"])
    known = set(students["roll_no"])

    att = pd.read_csv(folder / "attendance.csv", dtype=str)
    raw = att["roll_no"].copy()
    att["roll_no"] = _norm_roll(att["roll_no"])
    note("attendance.csv", "Normalised roll_no (trimmed spaces / upper-cased)", int((raw != att["roll_no"]).sum()))
    att["date"], fixed = _parse_dates(att["date"])
    note("attendance.csv", "Parsed DD-MM-YYYY dates", fixed)
    before = len(att)
    att = att.drop_duplicates()
    note("attendance.csv", "Dropped exact duplicate rows", before - len(att))
    unknown = ~att["roll_no"].isin(known)
    note("attendance.csv", "Dropped rows with unknown roll_no", int(unknown.sum()))
    att = att[~unknown]
    att["present"] = att["status"].str.upper().isin(PRESENT)

    summary = (att.groupby(["roll_no", "subject_code", "subject_name"], as_index=False)
               .agg(classes_held=("present", "size"), classes_attended=("present", "sum")))
    summary = summary.merge(students, on="roll_no", how="left").rename(
        columns={"subject_name": "subject", "faculty_adviser": "adviser_name"})
    summary = summary[["roll_no", "name", "email", "phone", "department", "section", "adviser_name",
                       "adviser_email", "subject", "subject_code", "classes_held", "classes_attended"]]
    code_to_name = dict(zip(summary["subject_code"], summary["subject"]))

    tests = pd.read_csv(folder / "test_results.csv", dtype={"roll_no": str})
    tests["roll_no"] = _norm_roll(tests["roll_no"])
    missing = tests["marks_obtained"].isna()
    note("test_results.csv", "Skipped rows with missing marks", int(missing.sum()))
    tests = tests[~missing]
    unknown = ~tests["roll_no"].isin(known)
    note("test_results.csv", "Skipped rows with unknown roll_no", int(unknown.sum()))
    tests = tests[~unknown & tests["test_name"].isin(MAJOR_TESTS)].copy()
    tests["pct"] = (tests["marks_obtained"] / tests["max_marks"] * 100).round(1)
    tests["subject"] = tests["subject_code"].map(code_to_name)
    marks = tests.pivot_table(index=["roll_no", "subject"], columns="test_name", values="pct", aggfunc="first")
    marks = marks.reindex(columns=MAJOR_TESTS).reset_index()
    marks.columns.name = None

    tt = pd.read_csv(folder / "teacher_timetable.csv", dtype=str)
    teaching = tt[tt["is_free"].str.lower() == "false"].copy()
    timetable = pd.DataFrame({
        "teacher": teaching["teacher_name"], "teacher_email": teaching["email"],
        "department": teaching["department"], "subject": teaching["subject_code"].map(code_to_name),
        "day": teaching["day"], "slot": teaching["start_time"] + "-" + teaching["end_time"],
    })
    return summary, marks, timetable, log
