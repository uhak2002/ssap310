"""유튜브 자동 편집 웹 화면 (로컬 전용).   실행: python app.py  → http://127.0.0.1:8766"""
import os
import threading
import time
from pathlib import Path

from dotenv import load_dotenv, set_key

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
load_dotenv(ENV_PATH)

import uvicorn  # noqa: E402
from fastapi import FastAPI, File, HTTPException, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse  # noqa: E402

import stages  # noqa: E402

UPLOADS, SAMPLES = ROOT / "uploads", ROOT / "samples"
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
OPTION_KEYS = {"cut", "illustrations", "logos", "mosaic", "faces", "mute_pii", "ill_mode", "whisper_model",
               "image_provider", "silence_db", "min_silence", "keep_silence", "ocr_interval", "image_quality",
               "max_scenes_per_min", "remove_stutters"}
KEYS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}

app = FastAPI()
state = {"running": False, "logs": [], "label": ""}
lock = threading.Lock()


def log(msg):
    with lock:
        state["logs"].append(f"{time.strftime('%H:%M:%S')}  {msg}")


def find_video(name):
    for d in (UPLOADS, SAMPLES):
        p = d / Path(name).name  # 경로 이탈 방지: 파일명만 사용
        if p.is_file() and p.suffix.lower() in VIDEO_EXT:
            return p
    raise HTTPException(404, "영상을 찾을 수 없습니다")


def make_cfg(opts):
    clean = {k: v for k, v in (opts or {}).items() if k in OPTION_KEYS}
    return stages.Cfg.from_env(**clean)


def mask(key):
    v = os.environ.get(key, "")
    return f"{v[:6]}...{v[-4:]}" if len(v) > 12 else ""


@app.get("/", response_class=HTMLResponse)
def index():
    return (ROOT / "web" / "index.html").read_text(encoding="utf-8")


@app.get("/api/state")
def get_state(since: int = 0):
    with lock:
        logs = state["logs"][since:]
        n = len(state["logs"])
    return {"device": stages.device_info(), "running": state["running"], "label": state["label"],
            "logs": logs, "next": n, "keys": {k: bool(os.environ.get(v)) for k, v in KEYS.items()},
            "masked": {k: mask(v) for k, v in KEYS.items()}}


@app.get("/api/videos")
def videos():
    out = []
    for d in (UPLOADS, SAMPLES):
        if d.is_dir():
            for p in sorted(d.iterdir()):
                if p.suffix.lower() in VIDEO_EXT:
                    out.append({"name": p.name, "folder": d.name, "mb": round(p.stat().st_size / 1e6, 1)})
    return out


@app.post("/api/status")
def status(body: dict):
    job = stages.Job(find_video(body["video"]), make_cfg(body.get("opts")), log=lambda m: None)
    st = job.status()
    out = job.load("render") if st["render"] else None
    return {"stages": st, "output": Path(out["output"]).name if out else None}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    UPLOADS.mkdir(exist_ok=True)
    name = Path(file.filename or "video.mp4").name
    if Path(name).suffix.lower() not in VIDEO_EXT:
        raise HTTPException(400, "지원하지 않는 형식입니다")
    with open(UPLOADS / name, "wb") as f:
        while chunk := await file.read(1 << 20):
            f.write(chunk)
    return {"name": name}


@app.post("/api/run")
def run_stage(body: dict):
    video, stage = find_video(body["video"]), body.get("stage", "render")
    if stage not in stages.STAGES:
        raise HTTPException(400, "알 수 없는 단계")
    with lock:
        if state["running"]:
            raise HTTPException(409, "이미 실행 중입니다")
        state["running"], state["label"] = True, stages.LABELS[stage]
    cfg, force = make_cfg(body.get("opts")), bool(body.get("force"))

    def work():
        try:
            log(f"── {video.name}  {stages.probe(video)[0]:.1f}초")
            stages.Job(video, cfg, log=log).ensure(stage, force=force)
            log("완료")
        except Exception as e:  # 단계 실패가 서버를 죽이지 않게
            log(f"✗ 오류: {e}")
        finally:
            state["running"] = False

    threading.Thread(target=work, daemon=True).start()
    return {"ok": True}


@app.post("/api/clear-cache")
def clear_cache(body: dict):
    if state["running"]:
        raise HTTPException(409, "실행 중에는 삭제할 수 없습니다")
    stages.Job(find_video(body["video"]), make_cfg(body.get("opts")), log=log).clear()
    log("캐시를 삭제했습니다")
    return {"ok": True}


@app.post("/api/settings")
def save_settings(body: dict):
    """API 키를 .env 에 저장. 빈 값은 무시(기존 키 유지)."""
    ENV_PATH.touch(exist_ok=True)
    for k, env in KEYS.items():
        v = (body.get(k) or "").strip()
        if v:
            set_key(str(ENV_PATH), env, v)
            os.environ[env] = v
    return {"ok": True}


@app.get("/api/output/{name}")
def output(name: str):
    p = Path(stages.Cfg.from_env().out_dir) / Path(name).name
    if not p.is_file():
        raise HTTPException(404)
    return FileResponse(p, media_type="video/mp4")


if __name__ == "__main__":
    print("http://127.0.0.1:8766")
    uvicorn.run(app, host="127.0.0.1", port=8766, log_level="warning")
