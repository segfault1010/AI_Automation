"""Weekly summary job: run by GitHub Actions every Monday (or manually).

    python weekly_summary.py --dry-run          # print only
    python weekly_summary.py --data-dir data/sample
"""
import argparse
from pathlib import Path

import pandas as pd

from core import notify, risk, summary
from core.config import secret


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", default=str(Path(__file__).parent / "data" / "sample"))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    d = Path(args.data_dir)
    marks = pd.read_csv(d / "marks.csv") if (d / "marks.csv").exists() else None
    tt = pd.read_csv(d / "timetable.csv") if (d / "timetable.csv").exists() else None
    subj, students = risk.analyze(pd.read_csv(d / "attendance.csv"), marks, tt)
    subject, body, engine = summary.build(subj, students)
    print(subject, f"(insights: {engine})\n")
    print(body)

    if args.dry_run:
        return
    to = secret("SUMMARY_TO") or secret("DEMO_INBOX")
    if not to:
        raise SystemExit("Set SUMMARY_TO to send the summary.")
    res = notify.send_emails([{"to": to, "kind": "summary", "subject": subject, "body": body}], redirect_to="")
    print("\nEmail status:", res[0]["status"])


if __name__ == "__main__":
    main()
