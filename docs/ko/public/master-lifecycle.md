마스터 생애주기는 깨끗한 세션 창설, 지속 컨텍스트 부트, 평시 승격 규율, 검증된 승계로 이어지는 실측 루프입니다.

# 마스터 생애주기

마스터 세션은 장수명으로 운영되지만 불멸의 세션은 아닙니다. 이 런타임은 마스터를 운영 계보의 한 세대로 다룹니다. 각 세대는 부트하고, 작업을 조율하고, 승인된 상태를 승격하고, 결국 깨끗한 후속 세션으로 제어를 넘깁니다.

## 전체 흐름

```text
founding spawn -> boot measurement -> steady state -> clean succession -> lineage record
```

## 창설 스폰

온보딩 가이드는 전체 최초 실행 절차의 정본입니다. 이 절차는 설치 대화와 Generation 1 마스터 세션을 분리해, 마스터가 깨끗한 컨텍스트와 감사 가능한 배치 기록으로 시작하게 합니다.

정본으로 사용할 온보딩 가이드:

- [master-ops/ONBOARDING.md](../../../master-ops/ONBOARDING.md)
- [한국어 미러](../master-ops/ONBOARDING.md)

실제 스폰 진입점은 `scripts/master-succeed spawn`입니다. 터미널을 만들기 전에 호스트 명령을 확인하려면 dry run을 사용합니다.

```bash
scripts/master-succeed spawn \
  --workspace-selector workspace-a \
  --kickoff-text "Generation 1 founding boot" \
  --root . \
  --model example-model \
  --title "Gen-1 founding boot" \
  --json \
  --dry-run
```

호스트가 관리형 터미널 생성을 지원하면, dry run이 아닌 스폰은 반환된 worktree 식별자가 요청한 workspace selector와 일치하는지 검증합니다. 일치하지 않으면 코드는 fail closed로 동작하고, 가능하면 새로 생성된 터미널을 닫습니다.

## 부트 실측

부트는 추정이 아니라 실측 단계입니다. 부트스트랩 명령은 charter, 선택적 handoff, 역할 상태, 예산 사용량, 중복 세션 경고를 읽습니다.

```bash
scripts/master-bootstrap \
  --charter master-ops/docs/MASTER-OPERATIONS.md \
  --handoff ./handoffs/latest.md \
  --session-id example-session \
  --json
```

세션 transcript가 있으면 최근 assistant 이벤트에서 모델 정체성을 확인할 수 있습니다.

```bash
scripts/model-identity-probe \
  --transcript ./sessions/example-session.jsonl \
  --expect example-model
```

호스트가 측정된 모델 필드를 제공하지 못하면 unavailable로 보고합니다. 실행 플래그만 보고 실제 모델을 추론하지 않습니다.

## 평시 운영

기본 운영은 continue-and-compact입니다. 마스터는 컨텍스트 압력이 커지기 전에 승인된 지식, 활성 트랙, 열린 결정을 지속 저장소로 승격해야 합니다.

live bootstrap 진입점은 세션 시작 배선에 쓰입니다. 제한된 블록을 출력하고, 부트 실패 대신 fallback 한 줄로 degrade되도록 설계되어 있습니다.

```bash
scripts/master-bootstrap-live \
  --handoff-dir ./handoffs \
  --role-state-file master-ops/docs/runbooks/role-state.md
```

읽기 전용 L1 digest loop는 설정된 레포지터리, 원장 tail, 작업 로그, 프로세스 패턴을 관측하고 config에 따라 digest를 씁니다.

```bash
scripts/l1-digest tick --config ./ops/l1-digest.json
```

> 참고: digest loop는 관측하고 기록합니다. 실제 작업과 수락은 digest 모듈 밖에 있습니다.

## 깨끗한 승계

승계는 명시적입니다. 컨텍스트 압력이 높거나 자연스러운 마일스톤에 도달하면 현재 마스터가 승계를 제안할 수 있지만, 권고 신호가 자동으로 후속 세션을 스폰하지는 않습니다.

트리거 분류:

```bash
scripts/master-succeed detect \
  "succession now" \
  --context-ratio 0.65 \
  --json
```

현재 마스터는 구조화된 상태에서 얇은 handoff를 만듭니다.

```bash
scripts/master-succeed handoff \
  --spec ./ops/handoff-spec.json \
  --json
```

후속 세션은 다음 명령이 소비하는 report shape로 복구를 증명합니다.

```bash
scripts/master-succeed verify-successor \
  --report ./ops/recovery-report.json \
  --json
```

후속 세션 검증 뒤에만 이전 세션을 은퇴시켜야 합니다. retire 명령은 정확히 하나의 predecessor 후보만 해석하며, 후보가 모호하면 거부합니다.

```bash
scripts/master-succeed retire \
  --self-handle successor-handle \
  --target-handle predecessor-handle \
  --json
```

운영자가 이전 터미널을 닫으려는 의도가 분명할 때만 `--execute`를 추가합니다.

## 계보

Lineage는 append-only 관측 메타데이터입니다. 세대, parent와 successor 세션, 상속 역할, 복구 소스, 상속된 열린 트랙, 검증 결과, 컨텍스트 손실 노트를 기록합니다. 부트스트랩 소스가 아니며 런타임 판단에도 사용하지 않습니다.

공개 규칙은 단순합니다. 검증 뒤에 lineage를 append하고, 마스터가 다음에 무엇을 해야 하는지 판단하는 권위로 lineage를 쓰지 않습니다.

다음 문서: [위임과 리뷰](delegation-and-review.md).
