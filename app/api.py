# file: app/api.py  (if you import app.env here too, guard it the same way)
from __future__ import annotations
try:
    import app.env  # noqa: F401
except Exception:
    pass

from typing import Annotated
from fastapi import FastAPI, Depends
from fastapi.responses import PlainTextResponse
from app.config import SETTINGS
from app import journal

API = FastAPI(title="ICT Watchlists Journal API")
# ... rest unchanged ...

API_KEY = os.getenv("JOURNAL_API_KEY", "").strip()
PATH = journal.PATH

app = FastAPI(title="ICT Watchlists Journal API")

def _auth_ok(req: Request) -> bool:
    if not API_KEY:
        return True
    return req.headers.get("x-api-key") == API_KEY

@app.get("/health", response_class=PlainTextResponse)
async def health():
    return "ok"

@app.get("/journal.csv")
async def get_csv(request: Request):
    if not _auth_ok(request):
        raise HTTPException(status_code=401, detail="unauthorized")
    # prefer local cache
    if os.path.exists(PATH):
        with open(PATH, "rb") as f:
            return Response(content=f.read(), media_type="text/csv")
    # fallback to GitHub
    data = journal._remote_download_bytes()
    if not data:
        raise HTTPException(status_code=404, detail="no journal yet")
    return Response(content=data, media_type="text/csv")

@app.get("/journal.json")
async def get_json(request: Request):
    if not _auth_ok(request):
        raise HTTPException(status_code=401, detail="unauthorized")
    rows = journal.read_last(1000)
    return {"rows": rows, "count": len(rows)}

@app.get("/journal")
async def get_html(request: Request):
    if not _auth_ok(request):
        raise HTTPException(status_code=401, detail="unauthorized")
    rows = journal.read_last(500)
    if not rows:
        return HTMLResponse("<h3>No journal rows yet</h3>")
    cols = journal.FIELDS
    def esc(s):
        return ("" if s is None else str(s)).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    head = "".join(f"<th>{c}</th>" for c in cols)
    body = "".join("<tr>" + "".join(f"<td>{esc(r.get(c,''))}</td>" for c in cols) + "</tr>" for r in rows[::-1])
    html = f"""
    <html><head><meta charset="utf-8"><title>Journal</title>
    <style>table{{border-collapse:collapse}}td,th{{border:1px solid #ddd;padding:4px;font:12px system-ui}}</style>
    </head><body>
    <h3>Last {len(rows)} journal rows</h3>
    <p>Use <code>/journal.csv</code> to download; <code>/journal.json</code> for API.</p>
    <table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>
    </body></html>"""
    return HTMLResponse(html)
