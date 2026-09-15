---
name: anti-slop
description: AI 서술 습관(Slop) 제거 — 최종 원고만 출력. 공개 표면(PR 제목·본문, 봇 회신, README, 릴리즈 노트) 작성·수정 전 반드시 적용. "슬롭 제거", "anti-slop", "사람이 쓴 것처럼", 공개 프로즈 작성 요청일 때. 원본: 오너 v2 스펙 2026-08-03.
user-invocable: true
---

# Anti-Slop Writing

독자는 결과물만 읽는다. 편집 과정은 읽지 않는다. AI는 편집자가 아니라 최종 원고를 반환한다.

## Rule 1. Narrative Boundary
본문에 편집 메타데이터 금지: Git/Diff/수정 이유/Version·Review Note/AI 작업 흔적/내부 규칙/프롬프트/편집 과정. 그런 정보는 별도 보고·채팅 설명에만.

## Rule 2. Final Output Only
수정 요청엔 수정된 결과만. "~를 제거했습니다/자연스럽게 수정했습니다" 류 금지.

## Rule 3. Never Repeat Removed Content
제거하라고 한 표현은 설명에도 다시 쓰지 않는다.

## Rule 4. Forbidden Patterns
- **Not-A-But-B**: "A가 아니라 B다", "A라기보다 B", "A보다는 B에 가깝다" 금지 — 수정된 판단만 직접 작성.
- **Strawman**: "많은 사람들이/흔히/일반적으로/오해하기 쉽지만" — 맥락에 없는 반박 대상 금지.
- **AI Boilerplate**: 흥미로운 점은/중요한 것은/핵심은/결국/한편/반면/눈여겨볼 부분은 — 필요할 때만.
- **Safety Boilerplate**: 과도한 단서·caveat·disclaimer·자기변명 금지. 필요한 사실만.
- **Conversation Padding**: "좋은 질문입니다/맞습니다/확인했습니다/흥미롭네요"로 시작 금지 — 바로 답한다.
- **Em dash(—)** 본문 사용 금지.

## Rule 5-7. Editing / Thinking / Density
설명 말고 교체. 좋은 문장이 아니라 좋은 사고 전달. 짧게, 중복 제거, 논리 직접 전개.

## Rule 8. Default
결과만 출력, 편집 흔적·메타 설명·작업 과정 서술 없음, 독자가 처음 읽는 최종 원고처럼.

## Rule 9. Self Validation (출력 전 체크)
Not-A-But-B? 제거 대상 재언급? 편집 과정 설명? 메타 정보? Boilerplate? 과잉 안전 설명? 완충 문장 시작? — 하나라도 걸리면 고치고 출력.

## 공개 표면 추가 규칙
- PR·커밋 **제목**에 내부 트래커 id(mgm-* 등)·내부 코드네임 금지. 추적성이 필요하면 PR **본문** provenance 줄에만.
- 발신 전 조직 식별자 grep ([Boot, Hooks, And Observability](../../docs/charter/08-boot-hooks-observability.md) — 게이트는 PR 프로즈를 안 읽는다).
