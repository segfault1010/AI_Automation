"""Attendance + marks risk engine."""
import math

import pandas as pd

from core.config import FALL_DROP, THRESHOLD, WARNING_BAND, WEAK_MARK

ATT_REQUIRED = ["roll_no", "subject", "classes_held", "classes_attended"]
ATT_OPTIONAL = ["name", "email", "phone", "department", "adviser_name", "adviser_email"]


def classes_needed(attended: float, held: float, threshold: float = THRESHOLD) -> int:
    """Consecutive classes a student must attend to reach the threshold.

    Solves (A + x) / (H + x) >= p  ->  x >= (p*H - A) / (1 - p).
    """
    p = threshold / 100
    if held <= 0:
        return 0
    x = (p * held - attended) / (1 - p)
    return max(0, math.ceil(x - 1e-9))


def classes_can_miss(attended: float, held: float, threshold: float = THRESHOLD) -> int:
    """Classes a student can still skip and stay at/above the threshold."""
    p = threshold / 100
    if held <= 0:
        return 0
    return max(0, math.floor((attended - p * held) / p + 1e-9))


def status_of(pct: float) -> str:
    if pct < THRESHOLD:
        return "CRITICAL"
    if pct < THRESHOLD + WARNING_BAND:
        return "WARNING"
    return "SAFE"


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    for col in ("roll_no", "subject", "department"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    return df


def read_table(file) -> pd.DataFrame:
    name = getattr(file, "name", str(file)).lower()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(file)
    return pd.read_csv(file)


def _marks_features(marks: pd.DataFrame) -> pd.DataFrame:
    test_cols = [c for c in marks.columns
                 if c not in ("roll_no", "subject") and pd.api.types.is_numeric_dtype(marks[c])]
    rows = []
    for _, r in marks.iterrows():
        scores = [float(r[c]) for c in test_cols if pd.notna(r[c])]
        latest = scores[-1] if scores else float("nan")
        prev = scores[-2] if len(scores) >= 2 else latest
        steady_fall = len(scores) >= 3 and all(b < a for a, b in zip(scores, scores[1:])) \
            and scores[0] - latest >= FALL_DROP
        rows.append({
            "roll_no": r["roll_no"], "subject": r["subject"],
            "scores": " → ".join(f"{s:g}" for s in scores),
            "latest_mark": latest,
            "weak": bool(scores) and latest < WEAK_MARK,
            "falling": bool(scores) and (prev - latest >= FALL_DROP or steady_fall),
        })
    return pd.DataFrame(rows)


def analyze(att: pd.DataFrame, marks: pd.DataFrame | None = None,
            timetable: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (per-subject rows, per-student summary sorted most-at-risk first)."""
    att = _clean(att)
    missing = [c for c in ATT_REQUIRED if c not in att.columns]
    if missing:
        raise ValueError(f"Attendance sheet is missing columns: {', '.join(missing)}")
    for col in ATT_OPTIONAL:
        if col not in att.columns:
            att[col] = ""
        att[col] = att[col].fillna("").astype(str)

    att["classes_held"] = pd.to_numeric(att["classes_held"], errors="coerce").fillna(0)
    att["classes_attended"] = pd.to_numeric(att["classes_attended"], errors="coerce").fillna(0)
    held, done = att["classes_held"], att["classes_attended"]
    att["att_pct"] = (done / held.where(held > 0) * 100).fillna(100).round(1)
    att["status"] = att["att_pct"].map(status_of)
    att["need_in_row"] = [classes_needed(a, h) for a, h in zip(done, held)]
    att["can_miss"] = [classes_can_miss(a, h) for a, h in zip(done, held)]

    # Marks
    if marks is not None and not marks.empty:
        feats = _marks_features(_clean(marks))
        att = att.merge(feats, on=["roll_no", "subject"], how="left")
    else:
        att["scores"], att["latest_mark"] = "", float("nan")
        att["weak"], att["falling"] = False, False
    att["scores"] = att["scores"].fillna("")
    att["weak"] = att["weak"].fillna(False).astype(bool)
    att["falling"] = att["falling"].fillna(False).astype(bool)

    # Subject teacher from the timetable
    att["teacher"], att["teacher_email"] = "", ""
    if timetable is not None and not timetable.empty:
        tt = _clean(timetable)
        by_dept = tt.drop_duplicates(["department", "subject"]).set_index(["department", "subject"])
        by_subj = tt.drop_duplicates("subject").set_index("subject")
        for i, r in att.iterrows():
            key = (r["department"], r["subject"])
            src = by_dept.loc[key] if key in by_dept.index else (
                by_subj.loc[r["subject"]] if r["subject"] in by_subj.index else None)
            if src is not None:
                att.at[i, "teacher"] = src["teacher"]
                att.at[i, "teacher_email"] = src["teacher_email"]

    att["at_risk"] = (att["status"] != "SAFE") | att["weak"] | att["falling"]
    subj = att

    # Per-student summary
    g = subj.groupby("roll_no", sort=False)
    st = g.agg(name=("name", "first"), email=("email", "first"), phone=("phone", "first"),
               department=("department", "first"), adviser_name=("adviser_name", "first"),
               adviser_email=("adviser_email", "first"), held=("classes_held", "sum"),
               attended=("classes_attended", "sum"), worst_pct=("att_pct", "min"),
               avg_mark=("latest_mark", "mean"))

    def subjects_where(mask):
        return subj[mask].groupby("roll_no")["subject"].apply(", ".join).reindex(st.index).fillna("")

    st["overall_pct"] = (st["attended"] / st["held"].where(st["held"] > 0) * 100).fillna(100).round(1)
    st["need_overall"] = [classes_needed(a, h) for a, h in zip(st["attended"], st["held"])]
    st["status"] = st["worst_pct"].map(status_of)
    st["below_85"] = subjects_where(subj["status"] == "CRITICAL")
    st["near_85"] = subjects_where(subj["status"] == "WARNING")
    st["weak_in"] = subjects_where(subj["weak"])
    st["falling_in"] = subjects_where(subj["falling"])
    st["max_need"] = g["need_in_row"].max()
    weak, falling = st["weak_in"] != "", st["falling_in"] != ""
    st["risk"] = ((90 - st["worst_pct"]).clip(lower=0) * 4 + weak * 25 + falling * 15).clip(upper=100).round(0)
    st["at_risk"] = (st["status"] != "SAFE") | weak | falling
    st["avg_mark"] = st["avg_mark"].round(1)

    st = st.reset_index().sort_values(["risk", "worst_pct"], ascending=[False, True])
    return subj, st.reset_index(drop=True)


def department_summary(students: pd.DataFrame) -> pd.DataFrame:
    return (students.groupby("department")
            .agg(students=("roll_no", "count"),
                 critical=("status", lambda s: (s == "CRITICAL").sum()),
                 warning=("status", lambda s: (s == "WARNING").sum()),
                 at_risk=("at_risk", "sum"),
                 avg_attendance=("overall_pct", "mean"),
                 avg_risk=("risk", "mean"))
            .round(1).sort_values("avg_risk", ascending=False).reset_index())


def subject_summary(subj: pd.DataFrame) -> pd.DataFrame:
    return (subj.groupby(["department", "subject"])
            .agg(students=("roll_no", "count"),
                 below_85=("status", lambda s: (s == "CRITICAL").sum()),
                 near_85=("status", lambda s: (s == "WARNING").sum()),
                 weak_marks=("weak", "sum"), falling_marks=("falling", "sum"),
                 avg_attendance=("att_pct", "mean"), avg_mark=("latest_mark", "mean"))
            .round(1).sort_values(["below_85", "avg_attendance"], ascending=[False, True])
            .reset_index())
