# 🎓 AttendGuard: AI-powered attendance & performance risk automation

**Track:** Education · **Live demo:** _<add Streamlit link>_ · **Demo video:** _<add link>_

Faculty upload the attendance sheet, recent test results and teacher timetables. AttendGuard then automatically:

1. **Finds students below or close to 85%** (per subject and overall) and calculates **how many classes in a row** each must attend to recover.
2. **Flags weak (< 40) or falling (drop ≥ 10) marks.**
3. **Writes a personal warning email for every at-risk student with AI** (Claude, with Gemini/template fallback), and **alerts subject teachers and faculty advisers** with a digest.
4. **Syncs teacher timetables** so students can **book an appointment in a teacher's free slot**. Both sides get a confirmation email with a calendar invite (.ics).
5. **Dashboard:** department-wise and subject-wise risk, with the most at-risk students first.
6. **Weekly summary**, sent automatically every Monday via a GitHub Actions cron job (with AI-written insights).
7. **Places a phone call automatically** (Twilio text-to-speech) as soon as a student falls below 85%. No button is needed.

## How it works

```
 CSV/XLSX upload ─► Risk engine (pandas) ─► Dashboard (Streamlit + Plotly)
                         │
                         ├─► below 85% ─► Twilio auto-call (once per student)
                         ├─► at-risk  ─► LLM writes personal email ─► Gmail SMTP ─► student
                         │                                          └► teacher + adviser digests
                         └─► timetable ─► free slots ─► booking ─► email + .ics invite
 GitHub Actions cron (Mon 09:00 IST) ─► weekly_summary.py ─► LLM insights ─► HOD email
```

**Recovery formula.** To reach the required fraction p (0.85) after attending A of H classes, a student needs x consecutive classes such that (A + x)/(H + x) ≥ p:

`x = ceil((p·H − A) / (1 − p))`. For example, 30/40 (75%) needs **27** classes in a row (57/67 = 85.1%).

For students in the 85–90% band, the app shows how many classes they can still miss: `floor((A − p·H) / p)`.

**Risk score (0–100):** `4 × max(0, 90 − worst subject %) + 25 if weak marks + 15 if falling marks`, capped at 100. Students are ranked by this score.

## Tools used

| Purpose | Tool |
|---|---|
| App, UI and hosting | Python, Streamlit, Streamlit Community Cloud |
| Data and charts | pandas, Plotly |
| AI emails and insights | Anthropic Claude API (`claude-opus-5-5`), with Google Gemini and a template as fallbacks |
| Email | Gmail SMTP (App Password) |
| Automatic calls | Twilio Programmable Voice (TTS via inline TwiML) |
| Weekly schedule | GitHub Actions cron |

## Input formats

Sample files are in [`data/sample/`](data/sample). The app has a **Load sample data** button, and the templates can be downloaded from the Upload page.

- **attendance.csv**: `roll_no, name, email, phone, department, adviser_name, adviser_email, subject, classes_held, classes_attended`
- **marks.csv**: `roll_no, subject, test1, test2, test3` (any number of test columns, oldest first)
- **timetable.csv**: `teacher, teacher_email, department, subject, day, slot` (teaching periods; every other period counts as free)

## Run locally

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # optional: add keys
streamlit run app.py
python weekly_summary.py --dry-run                           # preview the weekly email
```

Every integration is optional. Without keys, emails go to an on-screen outbox, calls are simulated, and emails use a template, so the app always runs end to end.

**Demo safety:** set `DEMO_INBOX` and `DEMO_PHONE` to redirect every email and call to the team's own inbox and phone.

## Deploy

1. Push the code to GitHub.
2. On share.streamlit.io, create a new app with main file `app.py`.
3. Paste the keys from `secrets.toml.example` into the app's **Secrets**.
4. Add the same keys as GitHub **Actions secrets** for the weekly cron job. **Actions → Weekly risk summary → Run workflow** sends it on demand.

## Project structure

```
app.py               Streamlit UI (Upload, Dashboard, At-Risk, Notify, Book a Slot, Calls & Summary)
core/risk.py         attendance %, recovery formula, marks trend, risk score, department/subject rollups
core/ai.py           LLM email + insights writer (Claude → Gemini → template)
core/notify.py       Gmail SMTP sender, Twilio auto-caller, logs
core/timetable.py    free-slot finder, bookings, .ics invites
core/summary.py      weekly summary builder
weekly_summary.py    CLI used by the GitHub Actions cron
scripts/make_sample_data.py   sample data generator
```
