"""설명 화면: Claude로 구간 기획 → 이미지 생성(OpenAI, 없으면 플레이스홀더)."""
import base64
import hashlib
import json
import math
import os
import re
from pathlib import Path

STYLE = ("플랫 벡터 일러스트 + 핸드드로잉 카툰 스타일, 따뜻한 파스텔 색감, 단순하고 깔끔한 배경, "
         "화면 속 글자는 넣지 않거나 최소한으로")
SIZES = {"portrait": "1024x1536", "landscape": "1536x1024", "square": "1024x1024"}


def lines_from_words(words, gap=0.7):
    """단어들을 쉼 기준으로 문장 단위로 묶는다. 입력은 편집 후 타임라인 기준."""
    lines, cur = [], []
    for w in words:
        if cur and w["start"] - cur[-1]["end"] > gap:
            lines.append(cur)
            cur = []
        cur.append(w)
    if cur:
        lines.append(cur)
    return [{"start": l[0]["start"], "end": l[-1]["end"], "text": " ".join(x["word"] for x in l)} for l in lines]


def plan_scenes(lines, duration, cfg, logo_names=()):
    """대본에서 설명 일러스트 구간과 로고·아이콘 표시 구간을 Claude가 고른다. (scenes, logos) 반환."""
    import anthropic
    max_n = max(1, math.ceil(cfg.max_scenes_per_min * duration / 60))
    script = "\n".join(f"[{l['start']:.1f}-{l['end']:.1f}] {l['text']}" for l in lines)
    logo_rule = ""
    if logo_names:
        logo_rule = (f'- logos: 대본에서 아래 이름이 언급되는 구간에 로고를 표시: {list(logo_names)}. '
                     '목록에 있는 이름만 사용, 구간은 언급 시점부터 2~4초\n')
    prompt = (
        f"아래는 영상 대본입니다 (시간은 초 단위, 편집 후 영상 기준, 총 {duration:.1f}초).\n"
        f"scenes: 시청자의 이해를 돕는 설명 일러스트가 꼭 필요한 구간만 최대 {max_n}개 고르세요.\n"
        "- 각 구간은 2~6초, 서로 겹치지 않게\n"
        "- 이해를 해치지 않는 선에서만 고르고, 추상적이거나 단순 인사 구간은 제외\n"
        f"{logo_rule}"
        'JSON 객체만 출력: {"scenes":[{"start":숫자,"end":숫자,"caption":"8자 이내 한글(없으면 빈 문자열)",'
        '"image_prompt":"영어로 장면 묘사, 글자 없는 그림"}],"logos":[{"start":숫자,"end":숫자,"name":"이름"}]}\n\n'
        f"대본:\n{script}"
    )
    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 환경변수 사용
    msg = client.messages.create(model=cfg.claude_model, max_tokens=2500,
                                 messages=[{"role": "user", "content": prompt}])
    text = "".join(b.text for b in msg.content if b.type == "text")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("Claude 응답에서 JSON을 찾지 못했습니다")
    data = json.loads(m.group(0))
    scenes, last_end = [], 0.0
    for s in sorted(data.get("scenes", []), key=lambda x: float(x["start"])):
        start, end = max(float(s["start"]), last_end), min(float(s["end"]), duration)
        if end - start >= 1.5 and s.get("image_prompt"):
            scenes.append({"start": start, "end": end, "caption": s.get("caption", ""),
                           "image_prompt": s["image_prompt"]})
            last_end = end
    logos = [{"start": float(l["start"]), "end": min(float(l["end"]), duration), "name": l["name"]}
             for l in data.get("logos", []) if l.get("name") in logo_names and float(l["end"]) > float(l["start"])]
    return scenes[:max_n], logos


def _placeholder(path, size, caption):
    from PIL import Image, ImageDraw, ImageFont
    w, h = (int(x) for x in size.split("x"))
    img = Image.new("RGB", (w, h), (255, 244, 222))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((w * 0.08, h * 0.08, w * 0.92, h * 0.92), radius=48, fill=(255, 255, 255),
                        outline=(240, 160, 90), width=10)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", int(w * 0.075))
    except OSError:
        font = ImageFont.load_default()
    d.text((w / 2, h / 2), caption or "설명 화면", fill=(90, 60, 30), font=font, anchor="mm")
    img.save(path)


def make_image(scene, cfg, orientation, work_dir):
    """장면 이미지를 만들어 경로를 돌려준다. 같은 프롬프트는 캐시를 재사용해 API 비용을 아낀다."""
    size = SIZES[orientation]
    prompt = f"{STYLE}. {scene['image_prompt']}"
    key = hashlib.sha1(f"{cfg.image_model}|{cfg.image_quality}|{size}|{prompt}".encode()).hexdigest()[:12]
    path = Path(work_dir) / f"scene_{key}.png"
    if path.exists():
        return path
    provider = cfg.image_provider
    if provider == "auto":
        provider = "openai" if os.environ.get("OPENAI_API_KEY") else "placeholder"
    if provider == "openai":
        from openai import OpenAI
        # 계정에 해당 모델이 없으면(does not exist) 다음 후보 모델로 재시도
        models = [cfg.image_model] + [m for m in ("gpt-image-1-mini",) if m != cfg.image_model]
        for model in models:
            try:
                r = OpenAI().images.generate(model=model, prompt=prompt, size=size, quality=cfg.image_quality, n=1)
                path.write_bytes(base64.b64decode(r.data[0].b64_json))
                return path
            except Exception as e:  # 결제/한도/정책 오류 등 어떤 경우에도 영상 작업은 계속
                print(f"  경고: 이미지 생성 실패[{model}]({type(e).__name__}: {str(e)[:120]})")
                if "does not exist" not in str(e):
                    break
        print("  → 플레이스홀더로 대체")
    _placeholder(path, size, scene.get("caption", ""))
    return path
