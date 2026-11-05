# 구글 드라이브 연결 (Drive API)

강의 13강 방식. 프로그램이 영상을 드라이브에서 내려받고, 편집 결과를 올린다.
인증 방식은 둘 중 하나다. **먼저 방식 A(강의)** 를 쓰고, 업로드가 용량 문제로 거부되면 방식 B 로 바꾼다.

## 방식 A. 서비스 계정 (강의 방식)

### 1. 구글 클라우드 콘솔
1. https://console.cloud.google.com 로그인, 프로젝트 선택(없으면 새로 만들기)
2. **API 및 서비스 → 라이브러리 → Google Drive API → 사용** (서비스 계정을 만들 프로젝트와 같은 프로젝트에서)
3. **IAM 및 관리자 → 서비스 계정 → 서비스 계정 만들기**
   - 서비스 계정 이름: `video_test` (아무거나), ID는 자동 입력
   - **만들고 계속하기** → 권한·액세스 권한은 선택사항이라 건너뛰고 **완료**
4. 만든 서비스 계정 클릭 → **키** 탭 → **키 추가 → 새 키 만들기 → JSON → 만들기**
   - JSON 파일이 PC 에 내려받아진다. **저장소 폴더 밖**에 두고 절대 공유하지 않는다.

### 2. 키 등록 (직접)
```bash
python drive_sa_setup.py "C:\경로\내려받은-키.json"
```
`.env` 의 `GDRIVE_SERVICE_ACCOUNT_JSON` 에 저장되고, **서비스 계정 이메일**(`...@...iam.gserviceaccount.com`)이 출력된다.
키는 출력되지 않는다. 등록이 끝나면 내려받은 JSON 파일은 삭제하거나 안전한 곳에 보관한다.

### 3. 드라이브 폴더 공유
드라이브에 `input`, `output` 폴더를 만들고, 각각 **공유 → 서비스 계정 이메일 → 편집자** 로 추가한다.

### 4. 확인
```bash
python drive_io.py list <input 폴더 링크>
python drive_io.py download <영상 링크> --out samples
python drive_io.py upload output/영상_edited.mp4 --folder <output 폴더 링크>
```

### 제한 (강의에서도 안내)
서비스 계정은 **자체 저장 용량이 없다.** 개인 계정 폴더에 공유하면 업로드한 파일의 소유자가 서비스 계정이 되어
용량이 서비스 계정 쪽에서 계산되고, **업로드가 `storageQuotaExceeded` 로 거부될 수 있다.**
(내려받기는 문제없다. 공유 드라이브(Workspace)를 쓰면 해결된다.) 거부되면 방식 B 로 바꾼다.

## 방식 B. OAuth 사용자 인증 (내 용량으로 올림)

1. 콘솔 → **Google 인증 플랫폼 → 클라이언트 → 클라이언트 만들기 → 데스크톱 앱** → 클라이언트 ID·보안 비밀번호 확인
2. **대상(Audience)** 에서 테스트 사용자에 본인 Gmail 추가. 게시 상태가 "테스트"면 refresh token 이 7일 뒤 만료된다고
   알려져 있으니 오래 쓰려면 **앱 게시**
3. `.env` 에 `GDRIVE_CLIENT_ID`, `GDRIVE_CLIENT_SECRET` 입력 (채팅에 붙여 넣지 않는다)
4. `python drive_auth.py` → 브라우저 로그인·허용 → `.env` 에 `GDRIVE_REFRESH_TOKEN` 자동 저장

방식 B 는 서비스 계정 변수(`GDRIVE_SERVICE_ACCOUNT_JSON`)가 **비어 있을 때** 쓰인다. 전환하려면 그 줄을 비운다.

## 자동 실행 (미션: 편집 → 드라이브 업로드 → 공유 링크)
```bash
python drive_run.py --in <input 폴더 링크> --out <output 폴더 링크> --workflow --share
```
input 폴더의 새 영상을 내려받아 편집(컷 + 말투 + 자막)하고 output 폴더에 올린 뒤 링크를 출력한다.
`--share` 를 빼면 공유하지 않는다. 처리한 영상은 `work/drive_done.json` 에 기록되어 다시 처리하지 않는다.
클라우드 세션에서는 이 명령을 Claude 에게 시키면 된다 (`docs/workflow.md` 5장의 요청문 참고).

## 공유 링크
`python drive_io.py upload ... --share` 를 붙일 때만 "링크가 있는 모든 사용자: 보기"로 공유한다. 붙이지 않으면 공유하지 않는다.

## 클라우드 VM 에서 쓰려면
클라우드 환경(`video 0312`)의 **환경변수**에 방식 A 는 `GDRIVE_SERVICE_ACCOUNT_JSON`(JSON 한 줄), 방식 B 는 OAuth 세 값을 넣는다.
`ANTHROPIC_API_KEY` 는 넣지 않는다(클로드 코드 세션 인증과 충돌).

## 정리
과제가 끝나면 서비스 계정 키를 삭제(콘솔 → 서비스 계정 → 키)하고, 드라이브 폴더 공유에서 서비스 계정을 제거한다.
OAuth 를 썼다면 구글 계정의 **보안 → 타사 앱 액세스**에서 연결을 해제한다.
