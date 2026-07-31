이 문서는 Deep Agents의 개념을 mogui-ADE-orchestrator가 구현했거나 운영 규율로 둔 워크스페이스 레벨 개념에 대응시킵니다.

# 개념

Deep Agents는 에이전트 하네스를 실행, 컨텍스트, 위임, 스티어링, virtual filesystem 접근으로 설명합니다. mogui-ADE-orchestrator도 비슷한 관점을 쓰지만, 프로세스 내부 런타임이 아니라 실제 세션과 레포지터리에 적용합니다.

| Deep Agents 컴포넌트 | mogui-ADE-orchestrator 대응 개념 | 현재 상태 |
| --- | --- | --- |
| Execution Environment | Orca 터미널 세션, 스크립트 진입점, 어댑터 파견, git worktree | 진입점과 코어 헬퍼 구현 |
| Context Management | L0/L1 부트스트랩 컨텍스트, Role State, 이슈 트래커 메모리 감사, 컴팩션 회상 프로브, 운영 문서 | 부트스트랩과 digest 일부 구현; 이슈 트래커는 온보딩에서 선택 |
| Delegation | 파견 게이트, 작업자 계약, 어댑터 파견, 등록 프로브, 수락 게이트 | 게이트와 어댑터 흐름 구현 |
| Steering | `Proposal -> Approval -> Execution`, Role State, 역할 잠금, 분리된 리뷰 렌즈 | 승인 registry 구현; 역할과 리뷰 규칙은 운영 정책 |
| Virtual Filesystem | 레포지터리 worktree, 컨텍스트 resolver, 경로 관측, 민감 레인 분리 | worktree와 경로 헬퍼 구현; 민감 레인 분리는 정책 및 설계 |

## 실행 환경

Deep Agents에서 실행 환경은 에이전트가 도구, 파일, 코드 실행을 사용하는 자리입니다. 이 레포지터리에서 실행 환경은 실제 워크스페이스입니다.

마스터는 `scripts/master-bootstrap`, `scripts/master-succeed`, `scripts/dispatch-gate`, `scripts/adapter`, `scripts/l1-digest` 같은 스크립트 진입점으로 동작할 수 있습니다. 작업자 실행은 어댑터 레이어를 통해 라우팅됩니다. 병렬 쓰기, 브랜치 기준점, 트리 경합, 브랜치 전환 때문에 공유 체크아웃 작업이 위험하면 어댑터는 격리용 git worktree를 계획할 수 있습니다.

예시:

```bash
scripts/adapter dispatch \
  --contract ./contracts/job.md \
  --repo ./product-api \
  --isolation auto \
  --runtime codex \
  --agents 1 \
  --est-chars 2000 \
  --dry-run
```

> 팁: 작업자를 실제로 시작하지 않고 파견 계획만 보려면 `--dry-run`을 사용합니다.

## 컨텍스트 관리

마스터는 채팅 기록만이 아니라 지속 컨텍스트에서 시작합니다.

L0는 안정적인 운영 프레임입니다. charter, 역할 규칙, 상시 조율 규칙이 여기에 속합니다. L1은 현재 작업 컨텍스트입니다. 활성 트랙, 핸드오프 상태, digest 관측, 최근 운영 증빙이 여기에 속합니다. `scripts/master-bootstrap`은 제한된 L0/L1 블록을 적재하고, 핸드오프가 있으면 Role State를 파싱합니다.

`scripts/master-bootstrap-live`는 세션 시작 진입점입니다. Role State를 적재하고, 가능한 경우 이슈 트래커 명령으로 활성 트랙 라인을 수집하며, 메모리 요약을 감사하고, 작은 부트스트랩 블록을 출력합니다. 컴팩션 때는 역할과 트랙 세부 정보를 먼저 숨겨, 이어지는 세션이 스스로 회상한 뒤 지속 상태와 대조하게 합니다.

예시:

```bash
scripts/master-bootstrap-live \
  --handoff-dir ./handoffs \
  --role-state-file master-ops/docs/runbooks/role-state.md
```

> 참고: 컴팩션 동작은 회상 프로브입니다. 데이터 손실 복구 시스템이 아닙니다. 승인된 상태는 여전히 이슈 트래커나 git 문서로 승격해야 합니다.

## 위임

위임은 계약 기반입니다. 마스터는 열린 지시를 보내고 작업자 보고를 그대로 믿지 않습니다.

파견 게이트는 작업자가 시작되기 전에 읽을 수 있는 계약을 평가합니다. 그다음 어댑터가 작업자 명령을 시작할 수 있습니다. 작업자가 job id를 보고한 뒤에는, 독립 프로브가 예상 산출물에서 job id를 확인해야 register 단계가 수락됩니다.

공개 개념은 단순합니다.

```text
check -> dispatch -> register -> independent verification -> acceptance
```

이 흐름을 따르면 마스터는 네 가지 질문에 답할 수 있습니다. 무엇이 파견됐는지, 어떤 계약이 승인했는지, 어디서 실행됐는지, 어떤 증빙으로 수락했는지입니다.

## 스티어링

스티어링은 마스터가 무엇을 해도 되는지 정하는 사람 및 정책 레이어입니다.

운영 규칙은 다음과 같습니다.

```text
Proposal -> Approval -> Execution
```

코어 approval registry는 게이트 대상 행동이 실행 전에 승인된 proposal과 일치해야 함을 강제합니다. role-state 파일은 정확히 하나의 활성 역할을 유지하고, 명시적 역할 전환 전까지 다른 역할을 동결합니다.

중요한 머지나 공유 상태 변경에는 운영 가이드가 분리된 리뷰 렌즈를 권장합니다.

```text
general correctness
regression disproof
contract and scope
```

이 렌즈는 현재 코드 안의 별도 합의 엔진이 아니라 리뷰 규율입니다.

## 레포지터리 파일시스템 모델

Deep Agents는 pluggable storage가 뒷받침하는 virtual filesystem을 노출합니다. mogui-ADE-orchestrator는 그 추상화를 제공하지 않습니다.

대신 실제 레포지터리 파일시스템을 경계로 다룹니다. 컨텍스트 resolver는 레포지터리 경로와 git worktree를 관측합니다. 어댑터는 격리가 필요할 때 대상 레포지터리 아래에 작업자 worktree를 계획할 수 있습니다. 민감 레인은 공개 virtual filesystem 구현이 아니라 운영 정책과 전용 세션 라우팅으로 분리합니다.

다음 문서: [위임과 리뷰](delegation-and-review.md), [마스터 생애주기](master-lifecycle.md).
