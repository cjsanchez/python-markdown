from __future__ import annotations

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from markdown_it import MarkdownIt

app = FastAPI(title="Markdown Preview App")

# Templates + static
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Server-side markdown renderer (optional endpoint)
md = MarkdownIt("commonmark")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    # We render the preview primarily in the browser for instant feedback.
    # This page just loads the UI.
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/render", response_class=JSONResponse)
async def render_markdown(markdown_text: str = Form(...)) -> JSONResponse:
    """
    Optional: server-side render endpoint.
    Useful if you later want to save the markdown, do auth, rate limit, etc.
    """
    html = md.render(markdown_text)
    return JSONResponse({"html": html})