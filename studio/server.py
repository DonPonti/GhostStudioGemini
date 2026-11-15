from pathlib import Path
import json
import os
import shutil
import subprocess
import time
import uuid

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "ui"
MEDIA = ROOT / "media"
RENDERS = ROOT / "renders"
MEDIA.mkdir(exist_ok=True)
RENDERS.mkdir(exist_ok=True)
app = FastAPI(title="Ghost Studio Gemini", version="0.2.0")
app.mount("/ui", StaticFiles(directory=UI), name="ui")


class AnalyzeRequest(BaseModel):
    filename: str
    context: str = ""
    target: str = "vertical"
    duration_seconds: int = 30


class RenderRequest(BaseModel):
    filename: str
    start_seconds: float = 0
    end_seconds: float | None = None
    output_name: str = "ghoststudio-roughcut.mp4"


def safe_media_path(filename: str) -> Path:
    path = (MEDIA / Path(filename).name).resolve()
    if path.parent != MEDIA.resolve() or not path.exists():
        raise HTTPException(404, "Media file not found.")
    return path


@app.get("/")
def home():
    return FileResponse(UI / "index.html")


@app.get("/api/status")
def status():
    return {
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-3.1-pro-preview"),
        "gemini_api": "Interactions API",
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "ffprobe": shutil.which("ffprobe") is not None,
    }


@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    allowed = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, "Choose MP4, MOV, MKV, WEBM, AVI or M4V video.")
    name = f"{uuid.uuid4().hex[:10]}_{Path(file.filename).name}"
    destination = MEDIA / name
    size = 0
    with destination.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > 4 * 1024 * 1024 * 1024:
                destination.unlink(missing_ok=True)
                raise HTTPException(413, "Video exceeds the 4 GB upload limit.")
            out.write(chunk)
    return {"filename": name, "original_name": file.filename, "size_bytes": size}


@app.get("/api/probe/{filename}")
def probe(filename: str):
    path = safe_media_path(filename)
    if not shutil.which("ffprobe"):
        raise HTTPException(503, "FFprobe is not installed or is not on PATH.")
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries",
            "format=duration,size,format_name:stream=codec_type,codec_name,width,height,r_frame_rate",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode:
        raise HTTPException(422, result.stderr[-1200:])
    data = json.loads(result.stdout)
    data["filename"] = filename
    return data


@app.post("/api/analyze")
def analyze(request: AnalyzeRequest):
    path = safe_media_path(request.filename)
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise HTTPException(400, "Add GEMINI_API_KEY to .env, then restart Ghost Studio.")

    try:
        from google import genai

        client = genai.Client(api_key=key)
        model = os.getenv("GEMINI_MODEL", "gemini-3.1-pro-preview")

        # Upload the source video, then wait until Google's file processing is complete.
        uploaded = client.files.upload(file=str(path))
        deadline = time.monotonic() + 300
        while not uploaded.state or uploaded.state.name != "ACTIVE":
            if uploaded.state and uploaded.state.name == "FAILED":
                raise RuntimeError("Google Gemini could not process the uploaded video.")
            if time.monotonic() >= deadline:
                raise TimeoutError("Gemini video processing took longer than 5 minutes.")
            time.sleep(3)
            uploaded = client.files.get(name=uploaded.name)

        prompt = (
            "You are the senior editing director inside Ghost Studio Gemini. "
            "Analyze the uploaded video. Creator context: "
            + (request.context or "No extra context.")
            + f"""
Target format: {request.target}. Desired duration: about {request.duration_seconds} seconds.
Return ONLY valid JSON using this schema:
{{
  "project_title": "short title",
  "creative_direction": "one paragraph",
  "target": "{request.target}",
  "estimated_duration_seconds": 0,
  "music_mood": "mood suggestion",
  "segments": [
    {{
      "source_start": 0.0,
      "source_end": 5.0,
      "timeline_start": 0.0,
      "purpose": "hook|story|detail|transition|payoff",
      "visual_note": "what is visible",
      "editing_note": "cut and pacing suggestion",
      "keep": true
    }}
  ],
  "caption_style": "visual direction",
  "sound_design": ["idea"],
  "next_steps": ["step"]
}}
Use real timestamps. Never invent events. Prioritize a strong hook, visual variety,
emotional continuity and a satisfying ending. Keep every source timestamp within
the actual uploaded video's duration.
"""
        )

        # Gemini 3.1 Pro Preview is accessed through the Interactions API.
        interaction = client.interactions.create(
            model=model,
            input=[
                {
                    "type": "video",
                    "uri": uploaded.uri,
                    "mime_type": uploaded.mime_type or "video/mp4",
                },
                {"type": "text", "text": prompt},
            ],
        )
        raw = (interaction.output_text or "").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        plan = json.loads(raw)

        plan_path = RENDERS / f"{path.stem}_edit_plan.json"
        plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        return {"plan": plan, "plan_file": plan_path.name}

    except json.JSONDecodeError as exc:
        raise HTTPException(502, f"Gemini returned invalid JSON: {exc}")
    except Exception as exc:
        raise HTTPException(502, f"Gemini analysis failed: {exc}")


@app.post("/api/render")
def render(request: RenderRequest):
    source = safe_media_path(request.filename)
    if not shutil.which("ffmpeg"):
        raise HTTPException(503, "FFmpeg is not installed or is not on PATH.")
    if request.start_seconds < 0 or (
        request.end_seconds is not None and request.end_seconds <= request.start_seconds
    ):
        raise HTTPException(400, "Invalid trim range.")
    output_name = Path(request.output_name).name
    if not output_name.lower().endswith(".mp4"):
        output_name += ".mp4"
    output = RENDERS / f"{uuid.uuid4().hex[:8]}_{output_name}"
    command = ["ffmpeg", "-y", "-ss", str(request.start_seconds), "-i", str(source)]
    if request.end_seconds is not None:
        command += ["-t", str(request.end_seconds - request.start_seconds)]
    command += [
        "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=3600)
    if result.returncode:
        output.unlink(missing_ok=True)
        raise HTTPException(500, result.stderr[-1800:])
    return {"render_file": output.name, "download_url": f"/api/download/{output.name}"}


@app.get("/api/download/{filename}")
def download(filename: str):
    path = (RENDERS / Path(filename).name).resolve()
    if path.parent != RENDERS.resolve() or not path.is_file():
        raise HTTPException(404, "Render not found.")
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")
