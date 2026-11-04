---
name: feedback-follow-reference-fix-directly
description: "기준 자료를 먼저 확인하고, 바로 고칠 수 있는 문제는 묻지 말고 고칠 것"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 986f0bf7-3e36-4b4a-9c55-5cc73646b99d
  modified: 2026-11-04T11:20:26.264Z
---

사용자는 (1) 기준 자료 없이 추측으로 최소 구현을 만든 것, (2) 바로 고칠 수 있는 문제(느린 OCR 등)를 "고칠까요?"라고 되물은 것에 강하게 불만을 표했다.

**Why:** 강의 프로그램이 기준인데 제가 범위를 줄여 만들어서 API 키 구조, 웹 화면, 단계별 캐시를 뒤늦게 추가해야 했다. 되묻는 것이 진행을 늦췄다.
**How to apply:** 새 기능은 기준 자료(강의 캡처, .env 예시)부터 요청한다. 사용자가 결정할 일(공개 범위, 계정, 비용)만 묻고, 나머지는 바로 실행·검증한다. 못 해 본 부분은 숨기지 말고 "검증 안 됨"으로 쓴다. 관련: [[project-lecture-goal]]
