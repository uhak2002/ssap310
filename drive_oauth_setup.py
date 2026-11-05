"""OAuth 클라이언트 JSON(client_secret_*.json)을 .env 의 GDRIVE_CLIENT_ID / GDRIVE_CLIENT_SECRET 으로 등록한다.

    python drive_oauth_setup.py "C:\\경로\\client_secret_....json"

- 보안 비밀번호는 화면에 출력하지 않는다. (클라이언트 ID 앞부분만 확인용으로 출력)
- 등록 후에는 내려받은 JSON 파일을 삭제하거나 저장소 폴더 밖에 보관한다.
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
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        sys.exit(f"JSON 파일을 읽지 못했습니다: {e}")
    info = data.get("installed") or data.get("web") or {}
    cid, secret = info.get("client_id"), info.get("client_secret")
    if not cid or not secret:
        sys.exit("OAuth 클라이언트 JSON 이 아닙니다. (installed.client_id / client_secret 필요)")
    ENV.touch(exist_ok=True)
    set_key(str(ENV), "GDRIVE_CLIENT_ID", cid)
    set_key(str(ENV), "GDRIVE_CLIENT_SECRET", secret)
    print("저장 완료: .env 의 GDRIVE_CLIENT_ID, GDRIVE_CLIENT_SECRET (보안 비밀번호는 출력하지 않습니다)")
    print(f"클라이언트 ID: {cid[:14]}...")
    print("→ 다음: python drive_auth.py")


if __name__ == "__main__":
    main()
