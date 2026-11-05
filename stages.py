"""단계별 파이프라인 (결과 캐시 지원).

전사 → 컷 편집 → 기획(Claude) → 이미지 생성 → 개인정보 탐지(OCR) → 최종 렌더
각 단계 결과는 work/<영상>-<해시>/<단계>.json 에 저장되고, 옵션·앞 단계 결과가 같으면 재사용한다.
"""
import bisect
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, fields
from pathlib import Path

import cv2

import pii
import scenes as scn

STAGES = ["transcribe", "cuts", "tone", "subtitles", "plan", "images", "pii", "render"]
LABELS = {"transcribe": "전사 (faster-whisper)", "cuts": "컷 편집", "tone": "말투 다듬기", "subtitles": "자막",
          "plan": "시각 요소 기획", "images": "이미지 생성", "pii": "개인정보 탐지", "render": "최종 렌더"}
PIPELINE_TEXT = "전사 → 컷 편집 → 말투 다듬기 → 자막 → 시각 요소 기획 → 이미지 생성 → 개인정보 탐지 → 최종 렌더"
DEPS = {"transcribe": [], "cuts": ["transcribe"], "tone": ["cuts"], "subtitles": ["tone"], "plan": ["cuts"],
        "images": ["plan"], "pii": ["cuts"], "render": ["cuts", "subtitles", "images", "pii"]}
PARAMS = {
    "transcribe": ["whisper_model", "language"],
    "tone": ["tone", "tone_style", "claude_model", "subtitle_chars"],
    "subtitles": ["subtitles", "subtitle_position", "subtitle_font", "subtitle_size"],
    "cuts": ["cut", "silence_db", "min_silence", "keep_silence", "remove_stutters"],
    "plan": ["illustrations", "logos", "max_scenes_per_min", "claude_model"],
    "images": ["image_provider", "image_model", "image_quality"],
    "pii": ["mosaic", "ocr_interval"],
    "render": ["faces", "mute_pii", "ill_mode", "codec", "quality"],
}
FILLERS = {"어", "음", "으", "으음", "어어", "음음", "아", "에", "엄", "흠"}


def _b(name, default):
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "y", "on")


@dataclass
class Cfg:
    whisper_model: str = "auto"
    whisper_device: str = "auto"
    language: str = "ko"
    cut: bool = True
    silence_db: float = -35.0
    min_silence: float = 0.6
    keep_silence: float = 0.3
    remove_stutters: bool = True
    tone: bool = False  # 말투 다듬기 (Claude, 자막 문장만 수정)
    tone_style: str = "친근하고 또렷한 존댓말, 군더더기 없이 간결하게"
    subtitles: bool = False  # 자막 입히기
    subtitle_chars: int = 16  # 한 줄 글자 수 (자막은 최대 2줄)
    subtitle_position: str = "bottom"  # bottom | center | top
    subtitle_font: str = "Malgun Gothic"
    subtitle_size: float = 0.045  # 영상 높이 대비 글자 크기
    illustrations: bool = True
    ill_mode: str = "center"  # center(중앙 카드) | cutaway(전체 화면) | pip(우측 카드)
    logos: bool = True
    logo_dir: str = "./로고"
    max_scenes_per_min: float = 1.5
    claude_model: str = "claude-opus-5-5"
    image_provider: str = "auto"
    image_model: str = "gpt-image-1"
    image_quality: str = "medium"
    image_concurrency: int = 4  # 이미지 동시 생성 개수 (API 한도에 걸리면 낮추세요)
    mosaic: bool = True
    ocr_interval: float = 0.5
    faces: bool = False
    mute_pii: bool = False
    codec: str = "auto"
    quality: int = 19
    out_dir: str = "./output"
    work_dir: str = "./work"

    @classmethod
    def from_env(cls, **overrides):
        e = os.environ.get
        c = cls(
            whisper_model=e("WHISPER_MODEL", "auto"), whisper_device=e("WHISPER_DEVICE", "auto"),
            language=e("LANGUAGE", "ko"), silence_db=float(e("SILENCE_DB", "-35")),
            min_silence=float(e("MIN_SILENCE", "0.6")), keep_silence=float(e("KEEP_SILENCE", "0.3")),
            remove_stutters=_b("REMOVE_STUTTERS", True),
            tone=_b("TONE", False), tone_style=e("TONE_STYLE", cls.tone_style),
            subtitles=_b("SUBTITLES", False), subtitle_chars=int(e("SUBTITLE_CHARS", "16")),
            subtitle_position=e("SUBTITLE_POSITION", "bottom"), subtitle_font=e("SUBTITLE_FONT", "Malgun Gothic"),
            subtitle_size=float(e("SUBTITLE_SIZE", "0.045")), illustrations=_b("ILLUSTRATIONS", True),
            ill_mode=e("ILLUSTRATION_MODE", "center"), logos=_b("LOGOS", True), logo_dir=e("LOGO_DIR", "./로고"),
            max_scenes_per_min=float(e("MAX_SCENES_PER_MIN", "1.5")), claude_model=e("CLAUDE_MODEL", "claude-opus-5-5"),
            image_provider=e("IMAGE_PROVIDER", "auto"), image_model=e("IMAGE_MODEL", "gpt-image-1"),
            image_quality=e("IMAGE_QUALITY", "medium"), image_concurrency=int(e("IMAGE_CONCURRENCY", "4")),
            mosaic=_b("MOSAIC", True),
            ocr_interval=float(e("OCR_INTERVAL", "0.5")), faces=_b("BLUR_FACES", False),
            mute_pii=_b("MUTE_SPOKEN_PII", False), codec=e("VIDEO_CODEC", "auto"), quality=int(e("VIDEO_QUALITY", "19")),
            out_dir=e("OUT_DIR", "./output"), work_dir=e("WORK_DIR", "./work"),
        )
        names = {f.name for f in fields(cls)}
        for k, v in overrides.items():
            if k in names and v is not None:
                setattr(c, k, v)
        return c


# ---------- 공용 도구 ----------
def run(cmd, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd)
    if r.returncode != 0:
        raise RuntimeError(f"명령 실패: {' '.join(map(str, cmd[:6]))}...\n{r.stderr[-1200:]}")
    return r


def probe(path):
    r = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height:format=duration", "-of", "json", str(path)])
    j = json.loads(r.stdout)
    return float(j["format"]["duration"]), j["streams"][0]["width"], j["streams"][0]["height"]


def cuda_available():
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def device_info():
    if shutil.which("nvidia-smi"):
        r = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().splitlines()[0]
    return "CPU (GPU 없음)"


_nvenc = None


def nvenc_ok():
    global _nvenc
    if _nvenc is None:
        r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "nullsrc=s=256x256", "-frames:v", "1",
                            "-c:v", "h264_nvenc", "-f", "null", "-"], capture_output=True)
        _nvenc = r.returncode == 0
    return _nvenc


def video_args(cfg):
    codec = cfg.codec
    if codec == "auto":
        codec = "h264_nvenc" if nvenc_ok() else "libx264"
    q = str(cfg.quality)
    if codec == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-cq", q, "-preset", "p5", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-crf", q, "-pix_fmt", "yuv420p"]


def norm(word):
    return re.sub(r"[^\w가-힣]", "", word)


def map_time(t, keeps):
    """원본 시각 → 컷 편집 후 시각."""
    acc = 0.0
    for s, e in keeps:
        if t < s:
            return acc
        if t <= e:
            return acc + (t - s)
        acc += e - s
    return acc


def make_inverse(keeps):
    accs, acc = [], 0.0
    for s, e in keeps:
        accs.append(acc)
        acc += e - s

    def inv(t):
        i = max(0, bisect.bisect_right(accs, t) - 1)
        return keeps[i][0] + (t - accs[i])
    return inv


def pixelate(frame, box, block=14):
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = max(0, box[0]), max(0, box[1]), min(w, box[2]), min(h, box[3])
    if x1 - x0 < 2 or y1 - y0 < 2:
        return
    small = cv2.resize(frame[y0:y1, x0:x1], (max(1, (x1 - x0) // block), max(1, (y1 - y0) // block)))
    frame[y0:y1, x0:x1] = cv2.resize(small, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST)


# ---------- 자막 ----------
def build_cues(words, keeps, max_chars):
    """컷 편집 후 타임라인 기준 자막 구간. 추임새·잘린 단어는 빼고, 쉼·길이·문장 끝에서 끊는다."""
    mapped = []
    for w in words:
        if norm(w["word"]) in FILLERS:
            continue
        s, e = map_time(w["start"], keeps), map_time(w["end"], keeps)
        if e - s > 0.02:
            mapped.append({"word": w["word"], "start": s, "end": e})
    cues, cur = [], []

    def text(ws):
        return " ".join(x["word"] for x in ws)

    def flush():
        if cur:
            cues.append({"start": round(cur[0]["start"], 2), "end": round(cur[-1]["end"], 2), "text": text(cur)})
            cur.clear()

    for w in mapped:
        if cur and (len(text(cur + [w])) > max_chars * 2 or w["end"] - cur[0]["start"] > 3.5
                    or w["start"] - cur[-1]["end"] > 0.6):
            flush()
        cur.append(w)
        if re.search(r"[.?!]$|[다요죠까]$", w["word"]) and len(text(cur)) >= max_chars:
            flush()
    flush()
    for i, q in enumerate(cues):  # 너무 짧게 스쳐가지 않도록 최소 0.6초
        nxt = cues[i + 1]["start"] if i + 1 < len(cues) else q["end"] + 0.6
        q["end"] = round(min(max(q["end"], q["start"] + 0.6), nxt), 2)
    return cues


def _wrap2(text, max_chars):
    if len(text) <= max_chars or " " not in text:
        return text
    mid = len(text) // 2
    i = min((k for k, ch in enumerate(text) if ch == " "), key=lambda k: abs(k - mid))
    return text[:i] + "\\N" + text[i + 1:]


def build_ass(cues, W, H, cfg):
    def t(sec):
        return f"{int(sec // 3600)}:{int(sec % 3600 // 60):02d}:{sec % 60:05.2f}"

    size = int(H * cfg.subtitle_size)
    align = {"bottom": 2, "center": 5, "top": 8}.get(cfg.subtitle_position, 2)
    margin_v = int(H * 0.10) if align != 5 else 0
    head = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nWrapStyle: 0\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Default,{cfg.subtitle_font},{size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,"
            f"100,100,0,0,1,{max(2, size // 12)},0,{align},{int(W * 0.06)},{int(W * 0.06)},{margin_v},1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    lines = [f"Dialogue: 0,{t(q['start'])},{t(q['end'])},Default,,0,0,0,,"
             f"{_wrap2(q['text'].replace('{', '(').replace('}', ')'), cfg.subtitle_chars)}" for q in cues]
    return head + "\n".join(lines) + "\n"


# ---------- 작업(영상 하나) ----------
class Job:
    def __init__(self, video, cfg, log=print):
        self.video, self.cfg, self.log = Path(video), cfg, log
        st = self.video.stat()
        tag = hashlib.sha1(f"{self.video.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:8]
        self.dir = Path(cfg.work_dir) / f"{self.video.stem}-{tag}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.duration, self.W, self.H = probe(self.video)
        cap = cv2.VideoCapture(str(self.video))
        self.fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.release()

    def header(self):
        """실행 시작 시 로그 머리말 (영상 정보 + 단계 목록)."""
        self.log(f"─── {self.video.name}  {self.W}x{self.H}  {self.fps:.1f}fps  {self.duration:.1f}s")
        self.log(f"  단계: {PIPELINE_TEXT}")

    # 캐시
    def _file(self, stage):
        return self.dir / f"{stage}.json"

    def load(self, stage):
        try:
            return json.loads(self._file(stage).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def expected_key(self, stage):
        h = hashlib.sha1(json.dumps({p: getattr(self.cfg, p) for p in PARAMS[stage]}, sort_keys=True).encode())
        for d in DEPS[stage]:
            up = self.load(d)
            if not up:
                return None
            h.update(up["_id"].encode())
        return h.hexdigest()[:16]

    def valid(self, stage):
        data, key = self.load(stage), self.expected_key(stage)
        if not (data and key and data.get("_key") == key):
            return False
        return stage != "render" or Path(data["output"]).exists()

    def status(self):
        return {s: self.valid(s) for s in STAGES}

    def clear(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        self.dir.mkdir(parents=True, exist_ok=True)

    def ensure(self, stage, force=False):
        for d in DEPS[stage]:
            self.ensure(d)
        if not force and self.valid(stage):
            self.log(f"✓ {LABELS[stage]} (캐시 사용)")
            return self.load(stage)
        if stage == "transcribe":
            self._extract_audio()
        self.log(f"▶ {LABELS[stage]}")
        t0 = time.time()
        key = self.expected_key(stage)
        data = getattr(self, "_" + stage)()
        data["_key"], data["_id"] = key, uuid.uuid4().hex
        self._file(stage).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        self.log(f"✓ {LABELS[stage]} ({time.time() - t0:.1f}s)")
        return data

    # 1) 전사
    def _extract_audio(self):
        wav = self.dir / "audio.wav"
        self.log("▶ 오디오 추출")
        t0 = time.time()
        if not wav.exists():
            run(["ffmpeg", "-y", "-v", "error", "-i", str(self.video), "-vn", "-ac", "1", "-ar", "16000", str(wav)])
        self.log(f"✓ 오디오 추출 ({time.time() - t0:.1f}s)")

    def _transcribe(self):
        import wave
        import numpy as np
        from faster_whisper import WhisperModel
        wav = self.dir / "audio.wav"
        with wave.open(str(wav)) as f:
            audio = np.frombuffer(f.readframes(f.getnframes()), np.int16).astype(np.float32) / 32768.0
        gpu = cuda_available() and self.cfg.whisper_device != "cpu"
        size = self.cfg.whisper_model
        if size == "auto":
            size = "large-v3" if gpu else "small"
        self.log(f"  whisper 모델 로드: {size} ({'cuda/float16' if gpu else 'cpu/int8'})")
        model = WhisperModel(size, device="cuda" if gpu else "cpu", compute_type="float16" if gpu else "int8")
        segments, _ = model.transcribe(
            audio, language=self.cfg.language, word_timestamps=True, vad_filter=False,
            initial_prompt="음... 어... 그, 어, 음, 그러니까 어... 음...")  # 필러워드 누락 방지
        words, text, n_seg = [], [], 0
        for seg in segments:
            n_seg += 1
            text.append(seg.text.strip())
            for w in seg.words or []:
                words.append({"word": w.word.strip(), "start": w.start, "end": w.end})
            self.log(f"  전사 {seg.end:.0f}/{self.duration:.0f}초")
        self.log(f"  전사 완료: 세그먼트 {n_seg}개, 단어 {len(words)}개")
        return {"words": words, "text": " ".join(text)}

    # 2) 컷 편집 (컷 구간 계산만, 렌더는 최종 단계)
    def _cuts(self):
        c, words, dur = self.cfg, self.load("transcribe")["words"], self.duration
        cuts = []
        if c.cut:
            r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(self.video), "-af",
                                f"silencedetect=noise={c.silence_db}dB:d={c.min_silence}", "-f", "null", "-"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            st = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
            en = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
            pad = c.keep_silence / 2
            cuts = [(s + pad, e - pad, "silence") for s, e in zip(st, en) if e - s > c.keep_silence]
            for i, w in enumerate(words):
                if norm(w["word"]) in FILLERS:
                    cuts.append((w["start"], w["end"], f"filler:{w['word']}"))
                elif c.remove_stutters and i + 1 < len(words):
                    n = words[i + 1]
                    if norm(w["word"]) and norm(w["word"]) == norm(n["word"]) and n["start"] - w["end"] < 0.6:
                        cuts.append((w["start"], n["start"], f"stutter:{w['word']}"))
            cuts.sort()
        merged = []
        for s, e, why in cuts:
            if merged and s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(e, merged[-1][1]), merged[-1][2])
            else:
                merged.append((s, e, why))
        cuts = [(round(max(0, s), 3), round(min(dur, e), 3), why) for s, e, why in merged if e - s > 0.05]
        keeps, pos = [], 0.0
        for s, e, _ in cuts:
            if s - pos > 0.05:
                keeps.append((pos, s))
            pos = e
        if dur - pos > 0.05:
            keeps.append((pos, dur))
        removed = sum(e - s for s, e, _ in cuts)
        spoken = pii.spoken_pii(words)
        self.log(f"  제거 구간 {len(cuts)}개, {removed:.1f}초 단축 예정 / 말로 나온 개인정보 의심 {len(spoken)}건")
        return {"cuts": cuts, "keeps": keeps, "removed": removed, "spoken": spoken,
                "edited_duration": dur - removed}

    # 3) 말투 다듬기: 자막 문장만 다듬는다 (음성은 그대로이므로 의미·고유명사는 바꾸지 않는다)
    def _tone(self):
        c = self.cfg
        keeps = [tuple(k) for k in self.load("cuts")["keeps"]] or [(0, self.duration)]
        cues = build_cues(self.load("transcribe")["words"], keeps, c.subtitle_chars)
        for q in cues:
            q["orig"] = q["text"]
        if not c.tone:
            self.log(f"  말투 다듬기 꺼짐 → 원문 그대로 (자막 {len(cues)}줄)")
            return {"cues": cues, "refined": False}
        if not os.environ.get("ANTHROPIC_API_KEY"):
            self.log("  ANTHROPIC_API_KEY 없음 → 말투 다듬기 건너뜀 (설정에서 키를 입력하세요)")
            return {"cues": cues, "refined": False}
        import anthropic
        client, changed = anthropic.Anthropic(), 0
        for i in range(0, len(cues), 50):
            chunk = [q["text"] for q in cues[i:i + 50]]
            prompt = (f"영상 자막 문장 목록입니다. 아래 말투 규칙에 맞게 다듬으세요.\n말투 규칙: {c.tone_style}\n"
                      "규칙:\n- 의미, 사실, 숫자, 고유명사(학교·지역·제도 이름)는 절대 바꾸지 않기\n"
                      "- 각 문장 길이는 원문과 비슷하게 (±20%)\n- 개수와 순서를 그대로 유지, 합치거나 나누지 않기\n"
                      f"- JSON 문자열 배열만 출력\n\n{json.dumps(chunk, ensure_ascii=False)}")
            try:
                msg = client.messages.create(model=c.claude_model, max_tokens=4000,
                                             messages=[{"role": "user", "content": prompt}])
                m = re.search(r"\[.*\]", "".join(b.text for b in msg.content if b.type == "text"), re.S)
                arr = json.loads(m.group(0))
            except Exception as e:
                err = "크레딧이 부족합니다. Anthropic 콘솔에서 충전하세요." if "credit balance" in str(e) else str(e)[:200]
                raise RuntimeError(f"말투 다듬기 실패 — {err}") from None
            if len(arr) != len(chunk):  # 개수가 어긋나면 이 묶음은 원문 유지
                self.log("  경고: 응답 개수가 달라 이 묶음은 원문 유지")
                continue
            for j, new in enumerate(arr):
                new = str(new).strip()
                if new and new != chunk[j] and len(new) <= len(chunk[j]) * 1.5 + 4:
                    cues[i + j]["text"] = new
                    changed += 1
        self.log(f"  자막 {len(cues)}줄 중 {changed}줄 말투 수정")
        return {"cues": cues, "refined": True}

    # 4) 자막 파일(ASS) 생성. 입히기는 최종 렌더에서
    def _subtitles(self):
        if not self.cfg.subtitles:
            self.log("  자막 꺼짐 → 건너뜀")
            return {"ass": None, "count": 0}
        cues = self.load("tone")["cues"]
        (self.dir / "subs.ass").write_text(build_ass(cues, self.W, self.H, self.cfg), encoding="utf-8-sig")
        self.log(f"  자막 {len(cues)}줄 생성 (위치 {self.cfg.subtitle_position}, 글꼴 {self.cfg.subtitle_font})")
        return {"ass": "subs.ass", "count": len(cues)}

    # 5) 기획 (Claude)
    def _logo_files(self):
        d = Path(self.cfg.logo_dir)
        files = [p for ext in ("png", "jpg", "jpeg", "webp") for p in d.glob(f"*.{ext}")] if d.is_dir() else []
        return {p.stem: str(p) for p in files}

    def _plan(self):
        c = self.cfg
        out = {"scenes": [], "logos": []}
        if not (c.illustrations or c.logos):
            self.log("  설명 일러스트·로고 모두 꺼짐 → 건너뜀")
            return out
        if not os.environ.get("ANTHROPIC_API_KEY"):
            self.log("  ANTHROPIC_API_KEY 없음 → 기획 건너뜀 (설정에서 키를 입력하세요)")
            return out
        cuts, words = self.load("cuts"), self.load("transcribe")["words"]
        keeps = cuts["keeps"]
        mapped = [{"word": w["word"], "start": map_time(w["start"], keeps), "end": map_time(w["end"], keeps)}
                  for w in words if norm(w["word"]) not in FILLERS]
        logos = self._logo_files() if c.logos else {}
        try:
            scenes, logo_items = scn.plan_scenes(scn.lines_from_words(mapped), cuts["edited_duration"], c,
                                                 list(logos) if logos else [])
        except Exception as e:
            msg = str(e)
            if "credit balance" in msg:
                msg = "Claude API 크레딧이 부족합니다. Anthropic 콘솔 Plans & Billing 에서 충전하세요."
            raise RuntimeError(f"Claude 기획 실패 — {msg[:200]}") from None
        if not c.illustrations:
            scenes = []
        out["scenes"] = scenes
        out["logos"] = [{**l, "image": logos[l["name"]]} for l in logo_items if l.get("name") in logos]
        self.log(f"  일러스트 {len(out['scenes'])}장면, 로고 {len(out['logos'])}개 기획됨")
        return out

    # 4) 이미지 생성
    def _images(self):
        from concurrent.futures import ThreadPoolExecutor, as_completed
        scenes = self.load("plan")["scenes"]
        o = "portrait" if self.H > self.W * 1.1 else "landscape" if self.W > self.H * 1.1 else "square"
        n = len(scenes)
        if not n:
            return {"scenes": []}
        workers = max(1, min(self.cfg.image_concurrency, n))
        self.log(f"  이미지 {n}장 병렬 생성 (동시 {workers}개)")
        paths = [None] * n
        # 이미지 생성은 API 대기 시간이 대부분이라 스레드로 동시에 요청한다.
        with ThreadPoolExecutor(workers) as ex:
            futs = {ex.submit(scn.make_image, s, self.cfg, o, self.dir): i for i, s in enumerate(scenes)}
            for k, f in enumerate(as_completed(futs), 1):
                i = futs[f]
                paths[i] = str(f.result())
                self.log(f"  이미지 {k}/{n} 완료: {scenes[i].get('caption') or scenes[i]['image_prompt'][:30]}")
        return {"scenes": [{**s, "image": p} for s, p in zip(scenes, paths)]}

    # 5) 개인정보 탐지 (화면 글자 OCR)
    def _pii(self):
        c = self.cfg
        out = {"interval": c.ocr_interval, "samples": []}
        if not c.mosaic:
            self.log("  화면 글자 모자이크 꺼짐 → 건너뜀")
            return out
        try:
            ocr = pii.PiiOcr(c.whisper_device)
        except ImportError:
            self.log("  easyocr 미설치 → 건너뜀 (pip install easyocr)")
            return out
        import numpy as np
        cuts = self.load("cuts")["cuts"]
        cap = cv2.VideoCapture(str(self.video))
        fps = cap.get(cv2.CAP_PROP_FPS)
        step = max(1, int(fps * c.ocr_interval))
        idx, last_ocr, last_small = 0, None, None
        pending, ocr_n, static_n = [], 0, 0  # pending: (샘플 번호, 프레임)
        samples = out["samples"]

        def flush():
            nonlocal ocr_n
            if not pending:
                return
            for (i, _), boxes in zip(pending, ocr.find_batch([f for _, f in pending])):
                samples[i]["boxes"] = [list(b) for b in boxes]
            ocr_n += len(pending)
            pending.clear()
            self.log(f"  화면 검사 {samples[-1]['t']:.0f}/{self.duration:.0f}초 (OCR {ocr_n}회, 정적 화면 건너뜀 {static_n}회)")

        while True:
            if not cap.grab():
                break
            t = idx / fps
            if idx % step == 0 and not any(s <= t <= e for s, e, _ in cuts):
                ok, frame = cap.retrieve()
                if ok:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    small = cv2.resize(gray, (96, max(1, 96 * gray.shape[0] // gray.shape[1]))).astype(np.int16)
                    samples.append({"t": round(t, 2), "boxes": []})
                    if last_small is not None and np.abs(small - last_small).mean() < 1.5:
                        samples[-1]["same_as"] = last_ocr  # 화면이 안 바뀜 → 이전 OCR 결과 재사용
                        static_n += 1
                    else:
                        last_small, last_ocr = small, len(samples) - 1
                        pending.append((last_ocr, frame))
                        if len(pending) >= 4:
                            flush()
            idx += 1
        cap.release()
        flush()
        for s in samples:
            if "same_as" in s:
                s["boxes"] = samples[s.pop("same_as")]["boxes"]
        hit = sum(1 for s in samples if s["boxes"])
        self.log(f"  화면 {len(samples)}회 검사(OCR {ocr_n}회, 정적 화면 건너뜀 {static_n}회), 개인정보 글자 검출 {hit}회")
        return out

    # 6) 최종 렌더
    def _render(self):
        c = self.cfg
        cuts, plan_imgs, plan, pi = self.load("cuts"), self.load("images"), self.load("plan"), self.load("pii")
        keeps = [tuple(k) for k in cuts["keeps"]] or [(0, self.duration)]
        temps, cur = [], self.video
        mutes = [(s["start"], s["end"]) for s in cuts["spoken"]] if c.mute_pii else []
        if cuts["cuts"] or mutes:
            self.log("  컷 편집 적용 중")
            cur = self.dir / "cut.mp4"
            self._apply_cuts(cur, keeps, mutes)
            temps.append(cur)
        inv = make_inverse(keeps) if cuts["cuts"] else (lambda t: t)
        samples = pi["samples"]
        if any(s["boxes"] for s in samples) or c.faces:
            self.log("  모자이크 적용 중")
            nxt = self.dir / "mosaic.mp4"
            self._mosaic(cur, nxt, inv, samples, pi["interval"])
            cur = nxt
            temps.append(nxt)
        items = [{**s, "kind": "scene"} for s in plan_imgs["scenes"]] + [{**l, "kind": "logo"} for l in plan["logos"]]
        final = Path(c.out_dir) / f"{self.video.stem}_edited.mp4"
        final.parent.mkdir(parents=True, exist_ok=True)
        sub = self.load("subtitles")
        if items:
            self.log(f"  오버레이 {len(items)}개 합성 중")
            nxt = self.dir / "overlay.mp4" if sub["ass"] else final
            self._overlay(cur, nxt, items)
            if sub["ass"]:
                temps.append(nxt)
            cur = nxt
        if sub["ass"]:
            self.log(f"  자막 {sub['count']}줄 입히는 중")
            self._burn(cur, final, sub["ass"])
        elif Path(cur) != final:
            shutil.copy2(cur, final)
        for t in temps:
            t.unlink(missing_ok=True)
        self.log(f"  저장: {final}")
        return {"output": str(final.resolve())}

    def _burn(self, src, dst, ass_name):
        """ASS 자막을 영상에 입힌다. 경로 이스케이프를 피하려고 작업 폴더에서 실행한다."""
        fonts = os.environ.get("SUBTITLE_FONTS_DIR") or ("C:/Windows/Fonts" if Path("C:/Windows/Fonts").is_dir() else "")
        # 윈도 경로의 ':' 는 따옴표 안에서 '\:' 로 이스케이프해야 필터 파서가 인식한다
        flt = f"subtitles={ass_name}" + (f":fontsdir='{fonts.replace(':', chr(92) + ':')}'" if fonts else "")
        run(["ffmpeg", "-y", "-hide_banner", "-i", str(Path(src).resolve()), "-vf", flt, *video_args(self.cfg),
             "-c:a", "copy", str(Path(dst).resolve())], cwd=str(self.dir))

    def _apply_cuts(self, dst, keeps, mutes):
        expr = "+".join(f"between(t,{s:.3f},{e:.3f})" for s, e in keeps)
        script = f"[0:v]select='{expr}',setpts=N/FRAME_RATE/TB[v];[0:a]aselect='{expr}',asetpts=N/SR/TB"
        if mutes:
            m = "+".join(f"between(t,{map_time(s, keeps):.3f},{map_time(e, keeps):.3f})" for s, e in mutes)
            script += f",volume=enable='{m}':volume=0"
        script += "[a]"
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(script)
        try:
            run(["ffmpeg", "-y", "-hide_banner", "-i", str(self.video), "-/filter_complex", f.name,
                 "-map", "[v]", "-map", "[a]", *video_args(self.cfg), "-c:a", "aac", str(dst)])
        finally:
            Path(f.name).unlink(missing_ok=True)

    def _mosaic(self, src, dst, inv, samples, interval):
        ts = [s["t"] for s in samples]
        if self.cfg.faces:
            d = cv2.data.haarcascades
            front = cv2.CascadeClassifier(d + "haarcascade_frontalface_default.xml")
            profile = cv2.CascadeClassifier(d + "haarcascade_profileface.xml")
        cap = cv2.VideoCapture(str(src))
        fps = cap.get(cv2.CAP_PROP_FPS)
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        silent = Path(str(dst) + ".silent.mp4")
        ff = subprocess.Popen(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
             "-s", f"{w}x{h}", "-r", f"{fps}", "-i", "-", *video_args(self.cfg), str(silent)], stdin=subprocess.PIPE)
        face_boxes, hold, idx = [], 0, 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            ot = inv(idx / fps)
            i = bisect.bisect_right(ts, ot) - 1
            if i >= 0 and ot - ts[i] <= interval * 1.5:
                for b in samples[i]["boxes"]:
                    pixelate(frame, (b[0] - 8, b[1] - 8, b[2] + 8, b[3] + 8))
            if self.cfg.faces:
                if idx % 3 == 0:
                    gray = cv2.equalizeHist(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
                    found = list(front.detectMultiScale(gray, 1.1, 5, minSize=(60, 60)))
                    found += list(profile.detectMultiScale(gray, 1.1, 5, minSize=(60, 60)))
                    if len(found):
                        face_boxes, hold = found, 12
                    elif hold <= 0:
                        face_boxes = []
                hold -= 1
                for (x, y, bw, bh) in face_boxes:
                    p = int(bw * 0.25)
                    pixelate(frame, (x - p, y - p, x + bw + p, y + bh + p))
            ff.stdin.write(frame.tobytes())
            idx += 1
            if idx % max(1, total // 5) == 0:
                self.log(f"  모자이크 {idx * 100 // total}%")
        cap.release()
        ff.stdin.close()
        ff.wait()
        run(["ffmpeg", "-y", "-hide_banner", "-i", str(silent), "-i", str(src), "-map", "0:v", "-map", "1:a?",
             "-c", "copy", "-shortest", str(dst)])
        silent.unlink(missing_ok=True)

    def _overlay(self, src, dst, items):
        dur, W, H = probe(src)
        cmd = ["ffmpeg", "-y", "-hide_banner", "-i", str(src)]
        for o in items:
            cmd += ["-loop", "1", "-i", str(o["image"])]
        chains, last = [], "0:v"
        for i, o in enumerate(items, 1):
            en = f"enable='between(t,{o['start']:.2f},{o['end']:.2f})'"
            if o["kind"] == "logo":
                f, pos = f"scale={int(W * 0.16)}:-1", "W-w-24:24"
            elif self.cfg.ill_mode == "cutaway":
                f, pos = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}", "0:0"
            elif self.cfg.ill_mode == "pip":
                f, pos = f"scale={int(W * 0.5)}:{int(H * 0.4)}:force_original_aspect_ratio=decrease", "W-w-24:H-h-24"
            else:
                f, pos = f"scale={int(W * 0.8)}:{int(H * 0.8)}:force_original_aspect_ratio=decrease", "(W-w)/2:(H-h)/2"
            chains.append(f"[{i}:v]{f}[s{i}];[{last}][s{i}]overlay={pos}:{en}[o{i}]")
            last = f"o{i}"
        run([*cmd, "-filter_complex", ";".join(chains), "-map", f"[{last}]", "-map", "0:a?",
             *video_args(self.cfg), "-c:a", "copy", "-t", f"{dur:.3f}", str(dst)])
