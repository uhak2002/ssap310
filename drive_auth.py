"""구글 드라이브 OAuth 최초 1회 로그인. 브라우저에서 로그인·동의하면 GDRIVE_REFRESH_TOKEN 을 .env 에 저장한다.

사전 준비: .env 에 GDRIVE_CLIENT_ID, GDRIVE_CLIENT_SECRET 입력 (docs/drive-setup.md 참고)
실행:     python drive_auth.py
토큰 값은 화면에 출력하지 않는다.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv, set_key

ENV = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV)

# 이미 만들어 둔 input/output 폴더(앱이 만든 폴더가 아님)에 읽고 쓰려면 drive 전체 범위가 필요하다.
# 과제가 끝나면 구글 계정의 '타사 앱 액세스'에서 연결을 해제한다.
SCOPES = ["https://www.googleapis.com/auth/drive"]


def main():
    cid, secret = os.environ.get("GDRIVE_CLIENT_ID"), os.environ.get("GDRIVE_CLIENT_SECRET")
    if not cid or not secret:
        sys.exit(".env 에 GDRIVE_CLIENT_ID 와 GDRIVE_CLIENT_SECRET 을 먼저 입력하세요.")
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_config(
        {"installed": {"client_id": cid, "client_secret": secret,
                       "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                       "token_uri": "https://oauth2.googleapis.com/token",
                       "redirect_uris": ["http://localhost"]}}, SCOPES)
    print("브라우저가 열립니다. 구글 계정으로 로그인하고 허용을 눌러 주세요.")
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    if not creds.refresh_token:
        sys.exit("refresh token 을 받지 못했습니다. 구글 계정의 '타사 앱 액세스'에서 이 앱을 삭제한 뒤 다시 실행하세요.")
    ENV.touch(exist_ok=True)
    set_key(str(ENV), "GDRIVE_REFRESH_TOKEN", creds.refresh_token)
    print("저장 완료: .env 의 GDRIVE_REFRESH_TOKEN (값은 출력하지 않습니다)")


if __name__ == "__main__":
    main()
