"""드라이브 자동 편집 한 번 실행: input 폴더의 새 영상 내려받기 → 편집 → output 폴더에 업로드 → 링크 출력.

    python drive_run.py --in <input 폴더 링크> --out <output 폴더 링크> --workflow [--share] [--limit 1]

--workflow : 내 워크플로우(컷 + 말투 다듬기 + 자막, 일러스트·로고·모자이크 끔). docs/workflow.md 참고
--share    : 업로드한 영상을 '링크가 있는 모든 사용자: 보기'로 공유 (붙일 때만 공유)
이미 처리한 영상은 work/drive_done.json 에 기록해 다시 처리하지 않는다.
"""
import argparse
import json
import sys
from pathlib import Path

import drive_io  # .env 를 먼저 읽는다
import stages

DONE = Path("work/drive_done.json")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="src", required=True, help="입력 폴더 링크 또는 ID")
    ap.add_argument("--out", dest="dst", required=True, help="출력 폴더 링크 또는 ID")
    ap.add_argument("--workflow", action="store_true", help="컷 + 말투 + 자막 워크플로우")
    ap.add_argument("--share", action="store_true", help="업로드한 영상 링크 공유")
    ap.add_argument("--limit", type=int, default=1, help="한 번에 처리할 영상 수 (기본 1)")
    a = ap.parse_args()

    cfg = stages.Cfg.from_env(**({"tone": True, "subtitles": True, "illustrations": False, "logos": False,
                                  "mosaic": False} if a.workflow else {}))
    done = json.loads(DONE.read_text(encoding="utf-8")) if DONE.exists() else {}
    todo = [f for f in drive_io.list_videos(a.src) if f["id"] not in done and not f["name"].endswith("_edited.mp4")]
    if not todo:
        print("처리할 새 영상이 없습니다.")
        return
    for f in todo[: a.limit]:
        print(f"━━ {f['name']} ({int(f.get('size', 0)) / 1e6:.1f}MB)")
        src = drive_io.download(f["id"], "samples")
        job = stages.Job(src, cfg)
        job.header()
        out = Path(job.ensure("render")["output"])
        print("  드라이브에 올리는 중")
        fid, link = drive_io.upload(out, a.dst, a.share)
        done[f["id"]] = {"name": f["name"], "output": out.name, "link": link}
        DONE.parent.mkdir(exist_ok=True)
        DONE.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"완료: {link}" + ("" if a.share else "  (공유는 켜지 않음: --share 로 공유)"))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
