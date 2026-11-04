# 클라우드 세션 설정

로컬 PC가 아닌 곳(Claude Code 클라우드 세션, 다른 PC)에서 이 저장소를 이어서 작업할 때의 설정이다.

## 1. 먼저 읽을 것
1. `CLAUDE.md` — 프로젝트 목적, 구성, 규칙
2. `docs/ai-context/` — 이전 세션에서 정리한 맥락(강의 목표, 작업 방식, 환경 제약)
3. `agent.md` — 다른 AI 도구용 작업 지침

## 2. 환경 준비
```bash
pip install -r requirements.txt
cp .env.example .env    # 키는 직접 입력, 커밋 금지
```
- 필요: Python 3.13, ffmpeg(ffprobe 포함)
- GPU가 있으면 `WHISPER_MODEL=large-v3` 로 올려도 된다. 없으면 `small` 이 기본이다.

## 3. 비밀 값
- 클라우드 세션에는 `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` 를 환경변수 또는 세션의 비밀 값 설정으로 넣는다.
- 저장소(공개)에는 절대 키를 쓰지 않는다. 채팅에도 붙여 넣지 않는다.

## 4. 영상은 저장소에 없다
`uploads/`, `samples/`, `output/`, `work/` 는 커밋하지 않는다. 테스트 영상은 세션에서 직접 올리거나 ffmpeg 로 합성한다.

```bash
ffmpeg -f lavfi -i testsrc=size=640x360:rate=30:duration=10 -f lavfi -i sine=frequency=440:duration=10 -shortest samples/test.mp4
```

## 5. 실행 확인
```bash
python autoedit.py samples/test.mp4 --dry-run   # 전사·컷 계산 (API 비용 없음)
python app.py                                   # 웹 화면 http://127.0.0.1:8766
```
