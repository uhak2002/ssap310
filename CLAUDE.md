# CLAUDE.md

> 작업 전에 `docs/ai-context/` 를 먼저 읽는다 (강의 목표, 작업 방식, 환경 제약).
> 클라우드·다른 PC 설정은 `docs/cloud-setup.md`. 웹 화면 미리보기 설정은 `.claude/launch.json`.

## 프로젝트
유튜브 영상 자동 편집 프로그램. 강의(업무 자동화 → 자료화·수익화)의 실습 프로젝트이며,
이 구조를 익혀 이후 유학컨설팅 자료 자동화(API 키로 자료를 받아 처리)에 재사용하는 것이 최종 목표다.
강의에서 만드는 프로그램을 기준으로 삼는다. 임의로 범위를 줄이거나 구조를 바꾸지 말고, 다르면 먼저 확인한다.

## 구성
- `stages.py` — 8단계 파이프라인과 캐시: 전사 → 컷 편집 → 말투 다듬기(Claude) → 자막 → 기획(Claude) → 이미지 생성 → 개인정보 탐지(OCR) → 최종 렌더
- `docs/workflow.md` — 내 영상 편집 워크플로우(유학 상담 클립: 컷·말투·자막)와 자동화 설계
- `scenes.py` — Claude로 설명 일러스트·로고 구간 기획, 이미지 생성(OpenAI gpt-image-1, 없으면 플레이스홀더)
- `pii.py` — 개인정보 정규식, 화면 글자 OCR(EasyOCR)
- `app.py` + `web/index.html` — 로컬 웹 화면 (127.0.0.1:8766)
- `autoedit.py` — 명령줄 실행
- `.env.example` — 설정 항목 (실제 값은 `.env`, 커밋 금지)

## 실행
```bash
pip install -r requirements.txt
cp .env.example .env      # 키 입력
python app.py             # 웹 화면
python autoedit.py 영상.mp4 --dry-run   # 전사·컷 계산만 (API 비용 없음)
```

## 규칙
- API 키·토큰을 코드, 로그, 커밋, 채팅에 절대 남기지 않는다. 키는 `.env` 에만 둔다.
- 영상(`uploads/`, `samples/`, `output/`, `work/`)은 커밋하지 않는다.
- 단계 결과는 `work/<영상>-<해시>/<단계>.json` 에 캐시한다. 옵션 또는 앞 단계 결과가 바뀌면 자동 무효화된다.
- 이미지 생성은 비용이 드므로 같은 프롬프트는 캐시 이미지를 재사용한다.
- 개인정보(전화번호·주민번호·이메일·계좌) 모자이크는 보조 수단이다. 업로드 전 결과를 사람이 확인한다.

## 환경 메모
- 개발 PC는 GPU가 없다(CPU만). Whisper 기본은 `small`, OCR 은 느리다. 강의 환경(RTX 4070 Ti)과 다르다.
- OpenCV 는 5.x 에 얼굴 검출기가 없어 `opencv-python<5` 로 고정.
- ffmpeg 9: 필터 스크립트는 `-/filter_complex 파일` 형식.

## 아직 검증하지 않은 것
- Claude 기획과 OpenAI 이미지 생성 (API 키 필요)
- 로고·아이콘 오버레이 (`로고/` 에 이미지 필요)
- 화면 속 개인정보가 실제로 있는 영상에서의 모자이크
