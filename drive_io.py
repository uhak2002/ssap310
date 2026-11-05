"""구글 드라이브 영상 입출력 (Drive API, OAuth 환경변수 사용).

    python drive_io.py list <폴더 링크 또는 ID>                  # 폴더의 영상 목록
    python drive_io.py download <파일 링크 또는 ID> [--out samples]  # 내려받기
    python drive_io.py upload output/영상_edited.mp4 [--folder <폴더 링크 또는 ID>] [--share]

필요한 환경변수: GDRIVE_CLIENT_ID, GDRIVE_CLIENT_SECRET, GDRIVE_REFRESH_TOKEN (키 값은 출력하지 않는다)
--share 는 '링크가 있는 모든 사용자: 보기' 로 공유를 켠다. 명시했을 때만 공유한다.
"""
import argparse
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

# 이미 만들어 둔 input/output 폴더(앱이 만든 폴더가 아님)에 올리려면 drive.file 만으로는 부족해서 drive 전체 범위를 쓴다
SCOPES = ["https://www.googleapis.com/auth/drive"]
NEED = ["GDRIVE_CLIENT_ID", "GDRIVE_CLIENT_SECRET", "GDRIVE_REFRESH_TOKEN"]


def service():
    """OAuth 세 값이 모두 있으면 OAuth(내 계정, 내 용량)를, 없으면 서비스 계정을 쓴다."""
    from googleapiclient.discovery import build
    sa_json, sa_file = os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON"), os.environ.get("GDRIVE_SERVICE_ACCOUNT_FILE")
    if (sa_json or sa_file) and not all(os.environ.get(k) for k in NEED):
        import json
        from google.oauth2 import service_account
        info = json.loads(sa_json) if sa_json else json.loads(Path(sa_file).read_text(encoding="utf-8"))
        # 서비스 계정은 자신에게 공유된 폴더만 볼 수 있어서 전체 drive 범위를 써도 접근 범위가 제한된다
        creds = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/drive"])
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    missing = [k for k in NEED if not os.environ.get(k)]
    if missing:
        sys.exit("드라이브 인증 정보가 없습니다. 서비스 계정(GDRIVE_SERVICE_ACCOUNT_JSON) 또는 OAuth "
                 f"({', '.join(NEED)}) 를 설정하세요. docs/drive-setup.md 참고")
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    creds = Credentials(None, refresh_token=os.environ["GDRIVE_REFRESH_TOKEN"], token_uri="https://oauth2.googleapis.com/token",
                        client_id=os.environ["GDRIVE_CLIENT_ID"], client_secret=os.environ["GDRIVE_CLIENT_SECRET"], scopes=SCOPES)
    creds.refresh(Request())  # 액세스 토큰은 1시간마다 만료되므로 매번 refresh token 으로 갱신
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def file_id(s):
    """공유 링크 또는 ID 문자열에서 파일/폴더 ID 를 뽑는다."""
    m = re.search(r"/d/([\w-]+)|/folders/([\w-]+)|[?&]id=([\w-]+)", s)
    return next(g for g in m.groups() if g) if m else s.strip()


def list_videos(folder, only_video=True):
    """폴더의 파일 목록. only_video=False 면 영상 외 파일(pptx, docx, pdf 등)도 포함."""
    svc = service()
    kind = " and mimeType contains 'video/'" if only_video else " and mimeType != 'application/vnd.google-apps.folder'"
    q = f"'{file_id(folder)}' in parents{kind} and trashed = false"
    res = svc.files().list(q=q, fields="files(id,name,size,modifiedTime)", orderBy="modifiedTime desc",
                           pageSize=100, supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    return res.get("files", [])


def download(fid, out_dir="samples"):
    from googleapiclient.http import MediaIoBaseDownload
    svc, fid = service(), file_id(fid)
    meta = svc.files().get(fileId=fid, fields="name,size", supportsAllDrives=True).execute()
    dest = Path(out_dir) / meta["name"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    total = int(meta.get("size", 0)) or 1
    with open(dest, "wb") as f:
        dl = MediaIoBaseDownload(f, svc.files().get_media(fileId=fid, supportsAllDrives=True), chunksize=16 * 1024 * 1024)
        done = False
        while not done:
            status, done = dl.next_chunk()
            print(f"  내려받는 중 {int(status.progress() * 100) if status else 100}% ({total / 1e6:.1f}MB)")
    return dest


def upload(path, folder=None, share=False):
    from googleapiclient.http import MediaFileUpload
    svc, path = service(), Path(path)
    body = {"name": path.name}
    if folder:
        body["parents"] = [file_id(folder)]
    import mimetypes
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"  # mp4, pptx, docx, pdf 등 확장자로 판단
    media = MediaFileUpload(str(path), mimetype=mime, resumable=True, chunksize=16 * 1024 * 1024)
    req = svc.files().create(body=body, media_body=media, fields="id,webViewLink", supportsAllDrives=True)
    resp = None
    try:
        while resp is None:
            status, resp = req.next_chunk()
            print(f"  올리는 중 {int(status.progress() * 100) if status else 100}%")
    except Exception as e:
        if "storageQuotaExceeded" in str(e):
            sys.exit("업로드 거부: 서비스 계정은 저장 용량이 없어서 개인 드라이브 폴더에 올리면 거부될 수 있습니다.\n"
                     "→ OAuth 방식으로 전환하세요 (docs/drive-setup.md '방식 B').")
        raise
    if share:
        svc.permissions().create(fileId=resp["id"], body={"type": "anyone", "role": "reader"}, supportsAllDrives=True).execute()
    return resp["id"], resp.get("webViewLink")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    lp = sub.add_parser("list")
    lp.add_argument("folder")
    lp.add_argument("--all", action="store_true", help="영상 외 파일(pptx, docx, pdf 등)도 표시")
    d = sub.add_parser("download")
    d.add_argument("file")
    d.add_argument("--out", default="samples")
    u = sub.add_parser("upload")
    u.add_argument("path")
    u.add_argument("--folder")
    u.add_argument("--share", action="store_true")
    a = ap.parse_args()
    if a.cmd == "list":
        for f in list_videos(a.folder, only_video=not a.all):
            print(f"{f['id']}  {int(f.get('size', 0)) / 1e6:7.1f}MB  {f['modifiedTime'][:10]}  {f['name']}")
    elif a.cmd == "download":
        print(f"저장: {download(a.file, a.out)}")
    else:
        fid, link = upload(a.path, a.folder, a.share)
        print(f"업로드 완료: {link}" + ("  (링크 공유 켜짐)" if a.share else "  (공유는 켜지 않음)"))


if __name__ == "__main__":
    main()
