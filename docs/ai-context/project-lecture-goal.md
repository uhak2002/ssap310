---
name: project-lecture-goal
description: 강의 실습으로 만드는 유튜브 자동 편집 프로그램과 최종 목표(유학컨설팅 자료 자동화·수익화)
metadata:
  node_type: memory
  type: project
  originSessionId: 986f0bf7-3e36-4b4a-9c55-5cc73646b99d
  modified: 2026-11-04T11:20:22.841Z
---

사용자는 "업무 자동화 → 자료화 → 무료/유료 제공으로 수익화"를 가르치는 강의를 듣는 중이다.
강의 실습이 유튜브 영상 자동 편집 프로그램(전사 → 컷 편집 → 기획(Claude) → 이미지 생성 → 개인정보 탐지(OCR) → 최종 렌더, 로컬 웹 화면, 단계별 캐시)이다.
이 과정을 익힌 뒤 사용자의 전문 분야인 유학컨설팅 자료를 API 키로 받아 같은 방식으로 자동화할 계획이다.

**Why:** 강의가 보여주는 프로그램이 학습의 기준이다. 최소 버전을 임의로 만들면 두 번 이상 재작업이 생겼다.
**How to apply:** 강의 화면이 기준이다. 구조를 줄이거나 바꾸기 전에 강의 캡처와 대조하고, 다르면 먼저 확인한다. 코드는 이후 유학컨설팅 자동화에 재사용할 수 있게 단계(stage) 구조로 유지한다. 관련: [[feedback-follow-reference-fix-directly]], [[reference-github-repo]]
