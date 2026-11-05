"""서비스 계정 JSON 키 파일을 .env 의 GDRIVE_SERVICE_ACCOUNT_JSON 으로 등록한다.

    python drive_sa_setup.py "C:\\경로\\내려받은-키.json"

- 키(private_key)는 화면에 출력하지 않는다. 출력하는 것은 서비스 계정 이메일뿐이다.
- 이 이메일에 드라이브의 input / output 폴더를 '편집자'로 공유해야 한다.
- 등록 후에는 키 JSON 파일을 저장소 폴더 밖에 보관하거나 삭제한다.
"""
import json
import sys
from pathlib import Path

from dotenv import set_key

ENV = Path(__file__).resolve().parent / ".env"


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    path = Path(sys.argv[1].strip('"'))
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        sys.exit(f"JSON 파일을 읽지 못했습니다: {e}")
    if info.get("type") != "service_account" or not info.get("private_key") or not info.get("client_email"):
        sys.exit("서비스 계정 키 JSON 이 아닙니다. (type=service_account, private_key, client_email 필요)")
    ENV.touch(exist_ok=True)
    set_key(str(ENV), "GDRIVE_SERVICE_ACCOUNT_JSON", json.dumps(info, ensure_ascii=False, separators=(",", ":")))
    print("저장 완료: .env 의 GDRIVE_SERVICE_ACCOUNT_JSON (키는 출력하지 않습니다)")
    print(f"서비스 계정 이메일: {info['client_email']}")
    print("→ 이 이메일에 드라이브 input / output 폴더를 '편집자'로 공유하세요.")


if __name__ == "__main__":
    main()
