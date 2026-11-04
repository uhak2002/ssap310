---
name: environment-no-gpu
description: "개발 PC는 GPU 없이 CPU만 있고, 강의 환경(RTX 4070 Ti)과 달라 OCR·Whisper가 느림"
metadata:
  node_type: memory
  type: project
  originSessionId: 986f0bf7-3e36-4b4a-9c55-5cc73646b99d
  modified: 2026-11-04T11:20:29.462Z
---

이 PC(Windows 11)에는 GPU가 없다(`nvidia-smi` 없음, `torch.cuda.is_available()` False). Python 3.13, ffmpeg 9 설치됨.
측정값: Whisper small(CPU/int8) 26초 영상 전사 약 26초. EasyOCR 28회 검사 약 7분(모델 다운로드 포함).

**Why:** 강의는 RTX 4070 Ti 에서 large-v3 와 OCR 을 빠르게 돌리지만 이 PC는 그럴 수 없다.
**How to apply:** Whisper 기본은 small, OCR 은 검사 간격을 늘리거나 변화 없는 구간을 건너뛰게 한다. 오래 걸리는 작업은 백그라운드로 돌린다. 기술 메모: opencv-python 은 5.x 에 얼굴 검출기가 없어 `<5` 고정, ffmpeg 9 필터 스크립트는 `-/filter_complex`.
