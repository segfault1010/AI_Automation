"""AttendGuard: AI-powered attendance & performance risk automation."""
import html
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

from core import ai, notify, risk, summary
from core import timetable as tt
from core.config import THRESHOLD, secret

st.set_page_config(page_title="AttendGuard", page_icon="🎓", layout="wide")
SAMPLE = Path(__file__).parent / "data" / "sample"
STATUS_COLORS = {"CRITICAL": "#D03B3B", "WARNING": "#E8A10E", "SAFE": "#0CA30C"}  # reserved for status only
BRAND_COLORWAY = ["#2A78D6", "#EB6834", "#1BAF7A", "#E87BA4", "#4A3AA7", "#008300", "#E34948"]  # fixed order
ss = st.session_state

ASSETS = Path(__file__).parent / "assets"
st.markdown(f"<style>{(ASSETS / 'style.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

_PILL_CLASS = {"CRITICAL": "pill-critical", "WARNING": "pill-warning", "SAFE": "pill-safe"}


def pill(text):
    """Colour-coded status badge (presentational only)."""
    return f'<span class="pill {_PILL_CLASS.get(str(text), "pill-neutral")}">{text}</span>'


HERO_HTML = (ASSETS / "hero.html").read_text(encoding="utf-8")


def hero(title, subtitle, eyebrow="AttendGuard", kpis=None):
    """Animated page header: particle network, shimmering title, optional count-up KPI cards.

    kpis: [(label, value, decimals, suffix, color), ...]
    """
    cards = "".join(
        f'<div class="kpi" style="--tone:{color};animation-delay:{.15 + i * .08:.2f}s">'
        f'<div class="l">{html.escape(label)}</div>'
        f'<div class="v" data-to="{value}" data-dec="{dec}" data-suf="{suf}">0{suf}</div><div class="bar"></div></div>'
        for i, (label, value, dec, suf, color) in enumerate(kpis or []))
    title = re.sub(r"\s+", " ", re.sub(r"[^\w\s&·,.%:'()/-]", "", title)).strip()  # emoji break gradient text
    page = (HERO_HTML.replace("__EYEBROW__", html.escape(eyebrow)).replace("__TITLE__", html.escape(title))
            .replace("__SUB__", html.escape(subtitle)).replace("__N__", str(max(1, len(kpis or []))))
            .replace("__KPIS__", f'<div class="kpis">{cards}</div>' if kpis else ""))
    components.html(page, height=212 + (148 if kpis else 0))


def chart(container, fig):
    """Render a Plotly figure with consistent AttendGuard styling."""
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Inter, system-ui, sans-serif", size=12, color="#C9CBD6"),
                      title_font=dict(family="Space Grotesk, Inter, sans-serif", size=16, color="#F4F4F8"),
                      colorway=BRAND_COLORWAY, margin=dict(l=10, r=10, t=54, b=10), legend_title_text="",
                      legend=dict(orientation="h", yanchor="top", y=-0.08, x=0, bgcolor="rgba(0,0,0,0)"),
                      hoverlabel=dict(font_family="Inter, system-ui, sans-serif", bgcolor="#14141F",
                                      bordercolor="#7C5CFF", font_color="#F4F4F8"))
    fig.update_xaxes(gridcolor="rgba(255,255,255,.06)", zeroline=False, linecolor="rgba(255,255,255,.1)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,.06)", zeroline=False, linecolor="rgba(255,255,255,.1)")
    if any(t.type == "bar" for t in fig.data):  # thin surface gaps between segments, rounded ends
        fig.update_traces(marker_line_color="#0C0C16", marker_line_width=2, textposition="inside",
                          insidetextanchor="middle", textfont_color="#FFFFFF", textangle=0,
                          textfont_size=11, selector=dict(type="bar"))
        fig.update_layout(barcornerradius=4, bargap=0.35)
    container.plotly_chart(fig, theme=None)


LABELS = {"roll_no": "Roll no", "name": "Name", "department": "Dept", "status": "Status",
          "overall_pct": "Overall %", "worst_pct": "Lowest subject %", "max_need": "Attend in a row",
          "below_85": "Below 85% in", "near_85": "Close to 85% in", "weak_in": "Weak marks in",
          "falling_in": "Falling marks in", "risk": "Risk", "subject": "Subject", "classes_held": "Held",
          "classes_attended": "Attended", "att_pct": "Attendance %", "need_in_row": "Attend in a row",
          "can_miss": "Can still miss", "scores": "Test scores", "weak": "Weak", "falling": "Falling",
          "teacher": "Teacher", "students": "Students", "critical": "Critical", "warning": "Warning",
          "at_risk": "At risk", "avg_attendance": "Avg attendance %", "avg_risk": "Avg risk"}


def show_df(df, hide_index=False, column_config=None):
    """st.dataframe, falling back to plain HTML where pyarrow can't load (e.g. locked-down Windows)."""
    df = df.rename(columns=LABELS)
    column_config = {LABELS.get(k, k): v for k, v in (column_config or {}).items()}
    try:
        import pyarrow  # noqa: F401
        st.dataframe(df, hide_index=hide_index, column_config=column_config)
    except ImportError:
        fmt = {"Risk": lambda v: f'<div class="ag-bar"><span style="width:{v:.0f}%"></span></div>{v:.0f}'}
        html = df.to_html(index=not hide_index, border=0, escape=False,
                          formatters={k: f for k, f in fmt.items() if k in df.columns})
        for status in _PILL_CLASS:  # colour-code status cells
            html = html.replace(f"<td>{status}</td>", f"<td>{pill(status)}</td>")
        st.markdown(f'<div class="ag-table">{html}</div>', unsafe_allow_html=True)


# ---------------- data loading ----------------

def run_analysis(att, marks, timetable):
    subj, students = risk.analyze(att, marks, timetable)
    ss.update(att=att, marks=marks, tt=timetable, subj=subj, students=students, drafts={})
    # Automatic: call every student who just fell below the threshold.
    ss.last_calls = notify.auto_call(students)


def load_sample():
    run_analysis(pd.read_csv(SAMPLE / "attendance.csv"), pd.read_csv(SAMPLE / "marks.csv"),
                 pd.read_csv(SAMPLE / "timetable.csv"))


if "students" not in ss and st.query_params.get("roll"):
    load_sample()  # booking links from emails open straight into the app with data ready

has_data = "students" in ss

# ---------------- sidebar ----------------

PAGES = ["📤 Upload", "📊 Dashboard", "🚨 At-Risk Students", "✉️ Notify", "📅 Book a Slot", "📞 Calls & Weekly Summary"]
default_page = 4 if st.query_params.get("roll") else 0
with st.sidebar:
    st.markdown('<div class="ag-logo"><span class="mark"></span><span class="word">AttendGuard</span></div>'
                f'<div class="ag-tag">AI attendance & performance risk automation · threshold {THRESHOLD:g}%</div>',
                unsafe_allow_html=True)
    page = st.radio("Go to", PAGES, index=default_page, label_visibility="collapsed")
    st.divider()
    st.markdown("**Integrations**")
    for label, mode in (("🤖 AI", ai.engine_name()), ("✉️ Email", notify.email_mode()), ("📞 Calls", notify.call_mode())):
        live = not any(w in mode for w in ("Template", "Outbox", "Simulated"))
        dot = "#22C55E" if live else "#F59E0B"
        short = mode.split(" (")[0] if live else "Demo mode"
        st.markdown(f'<div class="ag-int" title="{mode}"><span>{label}</span>'
                    f'<span><span class="ag-dot" style="background:{dot}"></span>{short}</span></div>',
                    unsafe_allow_html=True)
    if secret("DEMO_INBOX"):
        st.caption(f"Demo mode: emails redirected to {secret('DEMO_INBOX')}")


def need_data():
    st.info("No data yet. Go to **📤 Upload** and upload sheets or click **Load sample data**.")
    st.stop()


# ---------------- pages ----------------

if page == PAGES[0]:
    hero("📤 Upload attendance, test results & timetables",
         "Drop in attendance sheets, recent test results and teacher timetables. AttendGuard scores every student instantly.",
         "Step 1 · Data")
    steps = [("1", "Upload", "Attendance, test results and teacher timetables (CSV or Excel)."),
             ("2", "Analyse", "Attendance %, classes needed in a row, and weak or falling marks."),
             ("3", "Alert", "AI-written emails to students, teachers and advisers; auto-call below 85%."),
             ("4", "Recover", "Students book a teacher's free slot; a weekly summary goes to the HOD.")]
    st.markdown('<div class="ag-steps">' + "".join(
        f'<div class="ag-step"><div class="ag-num">{n}</div><div><b>{t}</b><p>{d}</p></div></div>'
        for n, t, d in steps) + "</div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    f_att = c1.file_uploader("Attendance sheet (CSV/XLSX)", type=["csv", "xlsx"])
    f_marks = c2.file_uploader("Recent test results (CSV/XLSX)", type=["csv", "xlsx"])
    f_tt = c3.file_uploader("Teachers' timetable (CSV/XLSX)", type=["csv", "xlsx"])
    b1, b2 = st.columns([1, 1])
    if b1.button("🚀 Analyze uploaded files", type="primary", disabled=f_att is None):
        try:
            run_analysis(risk.read_table(f_att), risk.read_table(f_marks) if f_marks else None,
                         risk.read_table(f_tt) if f_tt else pd.read_csv(SAMPLE / "timetable.csv"))
            st.success("Analysis complete.")
        except Exception as e:
            st.error(f"Could not process files: {e}")
    if b2.button("🧪 Load sample data (3 departments, 42 students)"):
        load_sample()
        st.success("Sample data loaded and analysed.")

    if "students" in ss:
        s = ss.students
        st.markdown(f"**{len(s)} students analysed** · 🔴 {int((s.status == 'CRITICAL').sum())} below {THRESHOLD:g}% · "
                    f"🟠 {int((s.status == 'WARNING').sum())} close · "
                    f"📉 {int(((s.weak_in != '') | (s.falling_in != '')).sum())} weak/falling marks")
        calls = ss.get("last_calls", [])
        if calls:
            st.warning(f"📞 Auto-call triggered for {len(calls)} student(s) below {THRESHOLD:g}% "
                       "(see **Calls & Weekly Summary**).")

    with st.expander("📄 Expected file formats & templates"):
        st.markdown(
            "- **Attendance**: `roll_no, name, email, phone, department, adviser_name, adviser_email, subject, classes_held, classes_attended`\n"
            "- **Test results**: `roll_no, subject, test1, test2, test3, …` (any number of test columns, oldest first)\n"
            "- **Timetable** (teaching periods): `teacher, teacher_email, department, subject, day (Mon-Fri), slot (e.g. 09:00-10:00)`")
        d1, d2, d3 = st.columns(3)
        for col, name in zip((d1, d2, d3), ("attendance.csv", "marks.csv", "timetable.csv")):
            col.download_button(f"⬇️ {name}", (SAMPLE / name).read_bytes(), file_name=name, mime="text/csv")

elif page == PAGES[1]:
    if not has_data:
        hero("📊 Risk dashboard", "Load data on the Upload page to light this up.", "Overview")
        need_data()
    s, subj = ss.students, ss.subj
    hero("📊 Risk dashboard", f"Attendance and marks risk across departments at a glance · threshold {THRESHOLD:g}%.",
         "Live overview", kpis=[
             ("Students", len(s), 0, "", "#7C5CFF"),
             (f"Below {THRESHOLD:g}%", int((s.status == "CRITICAL").sum()), 0, "", "#FF5A5A"),
             ("Close to limit", int((s.status == "WARNING").sum()), 0, "", "#FAB219"),
             ("Weak / falling marks", int(((s.weak_in != "") | (s.falling_in != "")).sum()), 0, "", "#F472B6"),
             ("Avg attendance", round(float(s.overall_pct.mean()), 1), 1, "%", "#22D3EE")])

    order = {"status": ["CRITICAL", "WARNING", "SAFE"]}
    c1, c2 = st.columns([2, 3])
    dept_status = s.groupby(["department", "status"]).size().reset_index(name="students")
    chart(c1, px.bar(dept_status, x="department", y="students", color="status", text="students",
                     color_discrete_map=STATUS_COLORS, category_orders=order,
                     title="Department-wise risk (students)", height=420)
          .update_layout(xaxis_title=None, yaxis_title=None))

    subj_status = (subj.assign(label=subj.department + " · " + subj.subject)
                   .groupby(["label", "status"]).size().reset_index(name="students"))
    crit_rank = (subj_status[subj_status.status == "CRITICAL"].set_index("label").students
                 .reindex(subj_status.label.unique()).fillna(0).sort_values())
    chart(c2, px.bar(subj_status, y="label", x="students", color="status", orientation="h", text="students",
                     color_discrete_map=STATUS_COLORS, category_orders=order | {"label": list(crit_rank.index[::-1])},
                     title="Subject-wise risk (most students below 85% on top)", height=420)
          .update_layout(xaxis_title=None, yaxis_title=None, showlegend=False))

    fig = px.scatter(s, x="overall_pct", y="avg_mark", color="status", size="risk", size_max=18,
                     hover_name="name", hover_data={"roll_no": True, "department": True, "risk": True},
                     color_discrete_map=STATUS_COLORS, category_orders=order,
                     labels={"overall_pct": "Overall attendance %", "avg_mark": "Average latest mark"},
                     title="Attendance vs marks: bottom-left is the danger zone", height=380)
    fig.add_vline(x=THRESHOLD, line_dash="dot", line_color="#6B7280", annotation_text=f"{THRESHOLD:g}% rule")
    fig.add_hline(y=40, line_dash="dot", line_color="#6B7280", annotation_text="weak-mark line")
    chart(st, fig)

    st.subheader("🔥 Most at-risk students")
    show_df(s[s.at_risk][["roll_no", "name", "department", "overall_pct", "worst_pct", "max_need",
                               "below_85", "weak_in", "falling_in", "risk"]].head(15), hide_index=True,
                 column_config={"risk": st.column_config.ProgressColumn("risk", min_value=0, max_value=100, format="%d"),
                                "max_need": st.column_config.NumberColumn("classes needed in a row")})
    st.subheader("🏫 Department summary")
    show_df(risk.department_summary(s), hide_index=True)

elif page == PAGES[2]:
    hero("🚨 At-risk students", "Most at-risk first. Filter by department and status, then drill into any student.",
         "Triage")
    if not has_data:
        need_data()
    s, subj = ss.students, ss.subj
    f1, f2, f3 = st.columns(3)
    depts = f1.multiselect("Department", sorted(s.department.unique()))
    statuses = f2.multiselect("Attendance status", ["CRITICAL", "WARNING", "SAFE"], default=["CRITICAL", "WARNING"])
    marks_only = f3.checkbox("Include students flagged only for weak/falling marks", value=True)
    view = s.copy()
    if depts:
        view = view[view.department.isin(depts)]
    mask = view.status.isin(statuses)
    if marks_only:
        mask |= (view.weak_in != "") | (view.falling_in != "")
    view = view[mask]
    show_df(view[["roll_no", "name", "department", "status", "overall_pct", "worst_pct", "below_85",
                       "max_need", "near_85", "weak_in", "falling_in", "risk"]], hide_index=True,
                 column_config={"risk": st.column_config.ProgressColumn("risk", min_value=0, max_value=100, format="%d"),
                                "max_need": st.column_config.NumberColumn("attend N in a row")})

    st.subheader("🔍 Student detail")
    if len(view):
        pick = st.selectbox("Student", view.roll_no + " · " + view.name)
        roll = pick.split(" · ")[0]
        rows = subj[subj.roll_no == roll]
        show_df(rows[["subject", "classes_held", "classes_attended", "att_pct", "status", "need_in_row",
                           "can_miss", "scores", "weak", "falling", "teacher"]], hide_index=True,
                     column_config={"need_in_row": "attend N in a row to reach 85%",
                                    "can_miss": "can still miss"})
        long = rows[["subject", "scores"]].copy()
        long = long[long.scores != ""]
        if len(long):
            pts = [{"subject": r.subject, "test": f"Test {i + 1}", "score": float(v)}
                   for r in long.itertuples() for i, v in enumerate(r.scores.split(" → "))]
            chart(st, px.line(pd.DataFrame(pts), x="test", y="score", color="subject", markers=True,
                                    title="Test score trend").add_hline(y=40, line_dash="dot",
                                                                         annotation_text="weak line"))

elif page == PAGES[3]:
    hero("✉️ Personal warnings & faculty alerts",
         "AI-written personal emails for students, plus digests for subject teachers and faculty advisers.",
         "Outreach")
    if not has_data:
        need_data()
    s, subj = ss.students, ss.subj
    targets = s[s.at_risk]
    app_url = secret("APP_URL").rstrip("/")
    st.write(f"**{len(targets)} at-risk students** will get a personal AI-written email. Subject teachers and "
             "faculty advisers get a digest of their at-risk students.")
    redirect = st.text_input("Demo inbox: redirect every email here (leave blank to send to real addresses)",
                             value=secret("DEMO_INBOX"))

    if st.button("✨ 1. Generate AI warning emails", type="primary"):
        def draft(row):
            stu = row.to_dict()
            rows = subj[subj.roll_no == stu["roll_no"]].to_dict("records")
            link = f"{app_url}/?roll={stu['roll_no']}" if app_url else ""
            return stu["roll_no"], ai.student_email(stu, rows, link)

        with st.spinner(f"Drafting {len(targets)} personalised emails…"):
            with ThreadPoolExecutor(max_workers=8) as pool:
                ss.drafts = dict(pool.map(draft, [r for _, r in targets.iterrows()]))
        engines = pd.Series([d[2] for d in ss.drafts.values()]).value_counts().to_dict()
        st.success(f"Drafted {len(ss.drafts)} emails · engines used: {engines}")

    drafts = ss.get("drafts", {})
    if drafts:
        pick = st.selectbox("Preview", [f"{r} · {s.set_index('roll_no').loc[r, 'name']}" for r in drafts])
        roll = pick.split(" · ")[0]
        subj_line, body, engine = drafts[roll]
        st.caption(f"Written by: {engine}")
        new_body = st.text_area("Email body (editable)", body, height=280)
        drafts[roll] = (subj_line, new_body, engine)

        # Teacher + adviser digests
        risky = subj[subj.at_risk]
        digests = []
        for (teacher, email), grp in risky.groupby(["teacher", "teacher_email"]):
            if not email:
                continue
            lines = [f"- {r.name} ({r.roll_no}), {r.subject}: attendance {r.att_pct}% [{r.status}]"
                     + (f", needs {r.need_in_row} classes in a row" if r.need_in_row else "")
                     + (f", scores {r.scores}" if r.weak or r.falling else "") for r in grp.itertuples()]
            digests.append({"to": email, "kind": "teacher", "subject": f"AttendGuard: {len(grp)} at-risk students in your subjects",
                            "body": f"Dear {teacher},\n\nThe following students need your attention:\n\n" + "\n".join(lines)
                            + "\n\nThey have been asked to book a slot during your free periods.\n\nAttendGuard"})
        for (adviser, email), grp in targets.groupby(["adviser_name", "adviser_email"]):
            if not email:
                continue
            lines = [f"- {r.name} ({r.roll_no}): overall {r.overall_pct}%, risk {r.risk:g}"
                     + (f", below 85 in {r.below_85}" if r.below_85 else "")
                     + (f", weak in {r.weak_in}" if r.weak_in else "")
                     + (f", falling in {r.falling_in}" if r.falling_in else "") for r in grp.itertuples()]
            digests.append({"to": email, "kind": "adviser", "subject": f"AttendGuard: {len(grp)} of your advisees are at risk",
                            "body": f"Dear {adviser},\n\nAt-risk advisees (most at-risk first):\n\n" + "\n".join(lines)
                            + "\n\nEach student has received a personal warning email.\n\nAttendGuard"})
        with st.expander(f"👩‍🏫 {len(digests)} teacher/adviser digests"):
            for d in digests:
                st.markdown(f"**{d['kind'].title()} → {d['to']}**: {d['subject']}")
                st.text(d["body"])

        if st.button(f"📨 2. Send {len(drafts)} student emails + {len(digests)} faculty alerts"):
            msgs = [{"to": s.set_index("roll_no").loc[r, "email"], "kind": "student", "subject": d[0], "body": d[1]}
                    for r, d in drafts.items()] + digests
            with st.spinner("Sending…"):
                res = notify.send_emails(msgs, redirect_to=redirect.strip())
            st.success(f"Processed {len(res)} emails.")
            show_df(pd.DataFrame(res)[["kind", "to", "delivered_to", "subject", "status"]], hide_index=True)

elif page == PAGES[4]:
    hero("📅 Book a slot with your subject teacher",
         "Pick a free period from your teacher's timetable. Both of you get a confirmation and calendar invite.",
         "Appointments")
    if not has_data:
        need_data()
    s, subj = ss.students, ss.subj
    options = list(s.roll_no + " · " + s.name)
    qroll = st.query_params.get("roll")
    idx = next((i for i, o in enumerate(options) if o.split(" · ")[0] == qroll), 0)
    pick = st.selectbox("I am", options, index=idx)
    roll = pick.split(" · ")[0]
    stu = s.set_index("roll_no").loc[roll].to_dict() | {"roll_no": roll}
    rows = subj[subj.roll_no == roll].sort_values("att_pct")
    flagged = rows[rows.at_risk]
    st.markdown(f"<span style='color:#6B7280'>Overall attendance <b>{stu['overall_pct']}%</b></span> &nbsp;{pill(stu['status'])}",
                unsafe_allow_html=True)
    subject_opts = list(flagged.subject) or list(rows.subject)
    subject = st.selectbox("Subject (at-risk subjects listed first)",
                           subject_opts + [x for x in rows.subject if x not in subject_opts])
    r = rows[rows.subject == subject].iloc[0]
    if not r.teacher:
        st.warning("No timetable found for this subject's teacher.")
        st.stop()
    st.markdown(f"**Teacher:** {r.teacher} · attendance {r.att_pct}% · "
                + (f"attend next **{r.need_in_row}** in a row" if r.need_in_row else f"can miss {r.can_miss}"))
    with st.expander(f"🗓️ {r.teacher}'s weekly timetable (synced from upload)"):
        show_df(tt.week_grid(ss.tt, r.teacher))
    slots = tt.free_slots(ss.tt, r.teacher)
    if not slots:
        st.warning("No free slots in the next 7 days.")
        st.stop()
    choice = st.selectbox("Free slots (next 7 days)", [x["label"] for x in slots])
    note = st.text_input("What do you need help with?", f"Recovering attendance / marks in {subject}")
    if st.button("✅ Book appointment", type="primary"):
        slot = next(x for x in slots if x["label"] == choice)
        b = tt.book(stu, {"teacher": r.teacher, "teacher_email": r.teacher_email}, slot, subject, note)
        ics = tt.make_ics(b)
        body = (f"Appointment booked via AttendGuard\n\nStudent: {b['student']} ({b['roll_no']})\nTeacher: {b['teacher']}\n"
                f"Subject: {subject}\nWhen: {slot['label']}\nNote: {note}\n\nCalendar invite attached.")
        notify.send_emails([
            {"to": r.teacher_email, "kind": "booking", "subject": f"Appointment: {b['student']} · {slot['label']}", "body": body, "ics": ics},
            {"to": stu["email"], "kind": "booking", "subject": f"Confirmed: meeting with {r.teacher} · {slot['label']}", "body": body, "ics": ics},
        ])
        st.success(f"Booked {slot['label']} with {r.teacher}. Confirmation + calendar invite sent to both.")
        st.download_button("⬇️ Add to calendar (.ics)", ics, file_name="appointment.ics", mime="text/calendar")
    if tt.BOOKINGS:
        st.subheader("All bookings")
        show_df(pd.DataFrame(tt.BOOKINGS), hide_index=True)

elif page == PAGES[5]:
    hero("📞 Automatic calls & 🗓️ weekly summary",
         "Voice calls fire automatically for students below the threshold; a weekly digest goes out every Monday.",
         "Automation")
    if not has_data:
        need_data()
    st.markdown(f"Calls fire **automatically** whenever data is analysed and a student is below {THRESHOLD:g}% "
                f"in any subject (once per student). Mode: `{notify.call_mode()}`")
    c1, c2 = st.columns(2)
    if c1.button("🔁 Re-check now"):
        new = notify.auto_call(ss.students)
        st.info(f"{len(new)} new call(s) placed.")
    if c2.button("♻️ Reset call memory (demo)"):
        notify.CALLED.clear()
        st.info("Call memory cleared. Next analysis will call again.")
    if notify.CALL_LOG:
        show_df(pd.DataFrame(notify.CALL_LOG)[["time", "roll_no", "name", "dialled", "status", "message"]].iloc[::-1],
                     hide_index=True)

    st.divider()
    st.subheader("🗓️ Weekly summary")
    st.markdown("Sent **automatically every Monday 09:00 IST** by a GitHub Actions cron job "
                "(`.github/workflows/weekly-summary.yml`). You can also preview or send it now.")
    if st.button("👀 Preview weekly summary"):
        with st.spinner("Writing summary…"):
            ss.summary = summary.build(ss.subj, ss.students)
    if "summary" in ss:
        subj_line, body, engine = ss.summary
        st.caption(f"Insights written by: {engine}")
        st.text_area(subj_line, body, height=380)
        to = st.text_input("Send to", secret("SUMMARY_TO") or secret("DEMO_INBOX"))
        if st.button("📨 Send summary now") and to:
            res = notify.send_emails([{"to": to, "kind": "summary", "subject": subj_line, "body": body}], redirect_to="")
            st.success(f"Summary: {res[0]['status']}")

    if notify.EMAIL_LOG:
        with st.expander(f"📬 Email log / outbox ({len(notify.EMAIL_LOG)})"):
            show_df(pd.DataFrame(notify.EMAIL_LOG)[["time", "kind", "to", "delivered_to", "subject", "status"]].iloc[::-1],
                         hide_index=True)
