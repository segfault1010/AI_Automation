"""Build the Vercel deployment (web/): the real Streamlit app, run in the browser with stlite.

    python scripts/build_web.py

Vercel can't host a Streamlit server, so web/index.html loads stlite (Streamlit on Pyodide/WebAssembly)
and mounts the app's own files, copied into web/app/. Re-run this after changing the app.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web"
APP = OUT / "app"
STLITE = "1.9.2"
REQUIREMENTS = ["plotly==5.24.1", "openpyxl"]
FILES = (["app.py"] + sorted(f"core/{p.name}" for p in (ROOT / "core").glob("*.py"))
         + ["assets/style.css", "assets/hero.html"]
         + sorted(str(p.relative_to(ROOT)).replace("\\", "/") for p in (ROOT / "data" / "sample").glob("*.csv"))
         + [f"sample_data/{n}" for n in ("students.csv", "attendance.csv", "test_results.csv", "teacher_timetable.csv")]
         + sorted(str(p.relative_to(ROOT)).replace("\\", "/") for p in (ROOT / "sample_data" / "templates").glob("*.csv")))
THEME = {"theme.base": "dark", "theme.primaryColor": "#7C5CFF", "theme.backgroundColor": "#07070D",
         "theme.secondaryBackgroundColor": "#12121D", "theme.textColor": "#E6E7EE", "theme.font": "sans serif",
         "client.toolbarMode": "minimal"}

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
<title>AttendGuard</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@stlite/browser@__V__/build/stlite.css">
<style>
  html, body { margin: 0; background: #07070D; }
  #boot { position: fixed; inset: 0; display: grid; place-items: center; color: #C7C9D9;
    font: 500 15px Inter, system-ui, sans-serif; background: #07070D; z-index: 0; }
  #boot b { display: block; font: 700 26px 'Space Grotesk', Inter, sans-serif; color: #fff; margin-bottom: 8px; }
  #boot .ring { width: 38px; height: 38px; margin: 0 auto 18px; border-radius: 50%;
    border: 3px solid rgba(124,92,255,.25); border-top-color: #7C5CFF; animation: spin 1s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  #root { position: fixed; inset: 0; z-index: 1; }
</style>
</head>
<body>
<div id="boot"><div style="text-align:center"><div class="ring"></div><b>AttendGuard</b>
  Starting the app in your browser… (first load takes ~20 seconds)</div></div>
<div id="root"></div>
<script type="module">
  import { mount } from "https://cdn.jsdelivr.net/npm/@stlite/browser@__V__/build/stlite.js";
  const files = Object.fromEntries(__FILES__.map(f => [f, { url: "./app/" + f }]));
  mount({ requirements: __REQS__, entrypoint: "app.py", files, streamlitConfig: __CONFIG__ },
        document.getElementById("root"));
  // Remove the boot screen once the app has rendered its sidebar.
  const boot = document.getElementById("boot");
  const timer = setInterval(() => {
    if (document.querySelector('[data-testid="stSidebar"]')) { boot.remove(); clearInterval(timer); }
  }, 300);
</script>
</body>
</html>
"""


def main() -> None:
    if APP.exists():
        shutil.rmtree(APP)
    for rel in FILES:
        dst = APP / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, dst)
    page = (PAGE.replace("__V__", STLITE).replace("__FILES__", json.dumps(FILES))
            .replace("__REQS__", json.dumps(REQUIREMENTS)).replace("__CONFIG__", json.dumps(THEME)))
    (OUT / "index.html").write_text(page, encoding="utf-8")
    print(f"Wrote web/index.html and {len(FILES)} app files to web/app/")


if __name__ == "__main__":
    main()
