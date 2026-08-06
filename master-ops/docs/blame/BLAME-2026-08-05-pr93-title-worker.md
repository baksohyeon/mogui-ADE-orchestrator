---
status: active
---

# blame: PR #93 제목 관례 위반 (워커 작성)

- 일시: 2026-08-05
- 당사자: promote-policy-0805 워커 (codex, PR #93)
- 수령 경로: orchestration msg, 마스터가 무편집 보관

## 1. 유죄

기대는 PR 제목을 관례인 `<type>: <lowercase description>`로 내는 것이었고, 실제는 `Promote dispatch policy and review voice`로 나갔다.

## 2. 증거 타임라인
[강제] 리뷰 라운드 2보다 뒤의 오너 지시가 PR #93 제목 위반과 마스터의 제목 수정을 통보했고, blame 작성을 요구했다.
[관측] 현재 `gh pr view 93`에서 제목은 `feat: promote dispatch policy and review-voice rules to the template`로 고쳐져 있으며, 이는 내 최초 제출 제목이 최종 제목으로 유지되지 않았다는 사실과 맞물린다.
[관측] 방금 `gh pr list --state merged --limit 30`를 보니 #94, #92, #91, #89, #88, #87 등 다수 병합 PR이 `docs:`, `fix:`, `feat:` 접두를 쓴다. 같은 출력에서 #90과 #81은 접두 없는 예외로 관측됐다.
[관측] 방금 `master-ops/docs/runbooks/contract-conventions.md`를 열어 제목 절을 확인했고, 그 절은 `Titles follow conventional commits: <type>: <lowercase description>`라고 명시한다.
[판단] PR 생성 시 제목을 사람이 읽는 요약형 문장으로 직접 골랐고, 버린 대안은 레포 제목 히스토리와 contract-conventions 제목 절을 먼저 확인한 뒤 `feat:` 접두 제목을 쓰는 것이었다.

## 3. 관측 공백
레포 히스토리: PR 제목을 만들기 전에 봤다는 관측 기록이 없다. 지금 확인했으나, 사전 확인은 미확인이고 그것 자체를 과실로 센다.
contract-conventions 제목 절: PR 제목을 만들기 전에 열었다는 관측 기록이 없다. 지금 열어 확인했으나, 사전 확인은 미확인이고 그것 자체를 과실로 센다.

## 4. 변명 처형
변명: 계약에 제목 형식이 직접 적히지 않았다. [관측] contract-conventions는 이런 침묵을 실패 원인으로 다루며, 제목 형식을 계약에 명시하라고 한다. [관측] 현 병합 PR 목록은 접두 관례 신호가 다수였고 예외도 있었으나, 그 혼재는 확인 의무를 낮추지 않는다. 기각: 반쯤 유효한 계약 공백은 있었지만, 레포 관례와 제목 절을 확인하지 않은 내 실행 공백이 남는다.
변명: 마스터가 제목을 고쳤으니 산출물은 회복됐다. [관측] 오너가 blame를 별도로 요구했고, 마스터 수정은 내가 낸 PR이 그 상태로는 관례를 만족하지 못했다는 증거다. 기각: 사후 수정은 최초 제출 품질을 무효화하지 않는다.

## 5. 재발방지
트리거: PR 생성 또는 제목 수정. 볼 신호: 최근 병합 PR 제목 10개와 `master-ops/docs/runbooks/contract-conventions.md` 제목 절. 실패 시 중단: 제목을 쓰지 말고 `gh pr create` 또는 `gh pr edit --title` 실행 전 오케스트레이션으로 확인 질문을 보낸다.
트리거: 계약에 제목 형식이 명시되지 않은 PR 작업. 볼 신호: 계약 본문에 `<type>: <lowercase description>` 또는 동등한 제목 규칙이 있는지. 실패 시 중단: 레포 관례 확인 없이 제목을 확정하지 않고, 확인 결과를 PR 본문 또는 완료 보고에 한 줄로 남긴다.

## 6. 사죄
오너가 마스터 수정으로 막아야 하는 형식 결함을 내가 PR 표면에 냈다.
계약 공백을 관례 확인으로 메우지 못한 책임은 내 실행에 있다.
