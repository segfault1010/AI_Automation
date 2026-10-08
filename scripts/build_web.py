"""Build the static Vercel page (web/index.html) from the Full demo dataset.

    python scripts/build_web.py --app-url https://your-app.streamlit.app

Vercel can't run Streamlit (it needs a long-lived server + websockets), so Vercel serves this
static snapshot and links to the live Streamlit app.
"""
from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import risk  # noqa: E402
from core.demo_data import load_full_demo  # noqa: E402

TEMPLATE = (ROOT / "web" / "template.html").read_text(encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-url", default="")
    args = ap.parse_args()

    summary, marks, timetable, log = load_full_demo(ROOT / "sample_data")
    subj, st = risk.analyze(summary, marks, timetable)

    kpis = [("Students tracked", len(st), "", "#7C5CFF"),
            ("Below 85%", int((st.status == "CRITICAL").sum()), "", "#FF5A5A"),
            ("Close to the limit", int((st.status == "WARNING").sum()), "", "#FAB219"),
            ("Weak / falling marks", int(((st.weak_in != "") | (st.falling_in != "")).sum()), "", "#F472B6"),
            ("Avg attendance", round(float(st.overall_pct.mean()), 1), "%", "#22D3EE")]
    kpi_html = "".join(
        f'<div class="kpi" style="--tone:{c};--d:{i * 0.08:.2f}s"><div class="l">{html.escape(l)}</div>'
        f'<div class="v" data-to="{v}" data-suf="{s}" data-dec="{1 if isinstance(v, float) else 0}">0</div>'
        f'<div class="bar"></div></div>' for i, (l, v, s, c) in enumerate(kpis))

    depts = risk.department_summary(st)
    dept_html = ""
    for i, d in enumerate(depts.itertuples()):
        safe = d.students - d.critical - d.warning
        seg = lambda n, cls, lab: (f'<span class="seg {cls}" style="flex:{n}" title="{n} {lab}">{n}</span>' if n else "")
        dept_html += (f'<div class="drow" style="--d:{i * 0.1:.1f}s"><div class="dname">{d.department}</div>'
                      f'<div class="stack">{seg(d.critical, "crit", "below 85%")}{seg(d.warning, "warn", "close")}'
                      f'{seg(safe, "safe", "safe")}</div><div class="dmeta">{d.avg_attendance}% avg</div></div>')

    top = st[st.at_risk].head(10)
    rows = ""
    for r in top.itertuples():
        level, cls = ("Below 85%", "crit") if r.status == "CRITICAL" else (("Close", "warn") if r.status == "WARNING"
                                                                            else ("Marks", "neutral"))
        flags = "; ".join(x for x in [f"weak: {r.weak_in}" if r.weak_in else "",
                                      f"falling: {r.falling_in}" if r.falling_in else ""] if x)
        rows += (f"<tr><td>{r.roll_no}</td><td>{html.escape(r.name)}</td><td>{r.department}</td>"
                 f'<td><span class="pill {cls}">{level}</span></td><td>{r.overall_pct}%</td>'
                 f"<td>{r.max_need}</td><td>{html.escape(flags) or '-'}</td>"
                 f'<td><div class="rbar"><span style="width:{r.risk:.0f}%"></span></div>{r.risk:.0f}</td></tr>')

    page = (TEMPLATE.replace("__KPIS__", kpi_html).replace("__DEPTS__", dept_html).replace("__ROWS__", rows)
            .replace("__FIXES__", str(sum(x["rows"] for x in log)))
            .replace("__APP_URL__", html.escape(args.app_url)))
    (ROOT / "web" / "index.html").write_text(page, encoding="utf-8")
    print("Wrote web/index.html", "(app url: %s)" % (args.app_url or "not set"))


if __name__ == "__main__":
    main()
