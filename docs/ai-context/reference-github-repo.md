---
name: reference-github-repo
description: "프로젝트 GitHub 저장소(uhak2002/ssap310, Public)와 키·파일 취급 규칙"
metadata:
  node_type: memory
  type: reference
  originSessionId: 986f0bf7-3e36-4b4a-9c55-5cc73646b99d
  modified: 2026-11-04T11:20:32.737Z
---

저장소: https://github.com/uhak2002/ssap310 (Public, main). 로컬 폴더는 `C:\Users\a\OneDrive\Desktop\ssap310(20261104)`. `gh` 는 uhak2002 로 로그인되어 있다.
`.env`, 영상(`uploads/ samples/ output/ work/`)은 .gitignore 로 제외한다. 저장소가 공개이므로 개인 정보와 키는 절대 커밋하지 않는다.

**Why:** 공개 저장소라 한 번 올라간 값은 되돌릴 수 없다.
**How to apply:** 커밋 전 `git status` 와 키 패턴 검사(`sk-ant-`, `sk-proj-`)를 한다. 푸시는 사용자가 요청한 범위에서만 한다. 관련: [[project-lecture-goal]]
