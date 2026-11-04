"""개인정보 탐지: 대본(말)과 화면 속 글자(OCR)."""
import re

import cv2

PII_PATTERNS = {
    "전화번호": re.compile(r"01[016789][\s-]?\d{3,4}[\s-]?\d{4}"),
    "주민번호": re.compile(r"\d{6}[\s-]?[1-4]\d{6}"),
    "이메일": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    "계좌/카드번호": re.compile(r"\d{2,6}-\d{2,8}-\d{2,8}(-\d{1,4})?|\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}"),
}


def match_pii(text):
    """텍스트에서 개인정보 유형을 찾아 돌려준다. 없으면 None."""
    for label, pat in PII_PATTERNS.items():
        if pat.search(text) or pat.search(text.replace(" ", "")):
            return label
    return None


def spoken_pii(words, window=10):
    """단어 목록(원본 타임라인)에서 말로 언급된 개인정보 구간을 찾는다."""
    spans = []
    for i in range(len(words)):
        parts = [w["word"] for w in words[i:i + window]]
        joined = "".join(parts)
        for label, pat in PII_PATTERNS.items():
            m = pat.match(joined)
            if not m:
                continue
            total, last = 0, i
            for k, p in enumerate(parts):
                total += len(p)
                last = i + k
                if total >= m.end():
                    break
            span = {"type": label, "start": words[i]["start"], "end": words[last]["end"], "text": m.group(0)}
            if spans and span["start"] <= spans[-1]["end"]:
                spans[-1]["end"] = max(spans[-1]["end"], span["end"])
            else:
                spans.append(span)
            break
    return spans


class PiiOcr:
    """화면 프레임에서 개인정보로 보이는 글자의 영역을 찾는다 (EasyOCR)."""

    def __init__(self, device="auto"):
        import easyocr
        self.reader = easyocr.Reader(["ko", "en"], gpu=device in ("auto", "cuda"), verbose=False)

    def find_batch(self, frames, max_side=1280):
        """프레임 여러 장을 한 번에 인식(배치). 모든 프레임은 같은 크기여야 한다. 박스 목록의 목록을 반환."""
        if not frames:
            return []
        h, w = frames[0].shape[:2]
        scale = min(1.0, max_side / max(h, w))
        smalls = [cv2.resize(f, None, fx=scale, fy=scale) if scale < 1 else f for f in frames]
        sh, sw = smalls[0].shape[:2]
        results = self.reader.readtext_batched(smalls, n_width=sw, n_height=sh, batch_size=len(smalls))
        out = []
        for res in results:
            boxes = []
            for pts, text, _conf in res:
                label = match_pii(text)
                if label:
                    xs, ys = [p[0] / scale for p in pts], [p[1] / scale for p in pts]
                    boxes.append((int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)), label))
            out.append(boxes)
        return out

    def find(self, frame, max_side=1280):
        """속도를 위해 긴 변을 max_side 로 줄여 읽고, 좌표는 원본 기준으로 되돌린다."""
        h, w = frame.shape[:2]
        scale = min(1.0, max_side / max(h, w))
        small = cv2.resize(frame, None, fx=scale, fy=scale) if scale < 1 else frame
        boxes = []
        for pts, text, _conf in self.reader.readtext(small):
            label = match_pii(text)
            if label:
                xs, ys = [p[0] / scale for p in pts], [p[1] / scale for p in pts]
                boxes.append((int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)), label))
        return boxes
