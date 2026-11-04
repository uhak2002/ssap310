"""명령줄 실행. 웹 화면은 `python app.py` 로 띄웁니다.

    python autoedit.py 영상.mp4 --dry-run          # 전사+컷 계산까지만 (API 비용 없음)
    python autoedit.py 영상.mp4                    # 전체 실행 → OUT_DIR/영상_edited.mp4
    python autoedit.py 영상.mp4 --stage pii --force  # 특정 단계만(앞 단계는 캐시 사용) 강제 재실행
"""
import argparse
import json

from dotenv import load_dotenv

load_dotenv()

import stages  # noqa: E402  (.env 를 먼저 읽어야 함)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--stage", choices=stages.STAGES, default="render")
    ap.add_argument("--force", action="store_true", help="지정한 단계의 캐시를 무시하고 다시 실행")
    ap.add_argument("--dry-run", action="store_true", help="전사와 컷 계산까지만 실행")
    ap.add_argument("--no-cut", action="store_true")
    ap.add_argument("--no-illustrations", action="store_true")
    ap.add_argument("--no-logos", action="store_true")
    ap.add_argument("--no-mosaic", action="store_true")
    ap.add_argument("--faces", action="store_true")
    ap.add_argument("--mute-pii", action="store_true")
    ap.add_argument("--mode", choices=["center", "cutaway", "pip"], help="일러스트 위치")
    a = ap.parse_args()

    cfg = stages.Cfg.from_env(
        cut=False if a.no_cut else None, illustrations=False if a.no_illustrations else None,
        logos=False if a.no_logos else None, mosaic=False if a.no_mosaic else None,
        faces=True if a.faces else None, mute_pii=True if a.mute_pii else None, ill_mode=a.mode)
    job = stages.Job(a.video, cfg)
    target = "cuts" if a.dry_run else a.stage
    job.ensure(target, force=a.force)
    if a.dry_run:
        c = job.load("cuts")
        print(json.dumps({"cuts": c["cuts"], "removed": round(c["removed"], 1), "spoken": c["spoken"]},
                         ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
