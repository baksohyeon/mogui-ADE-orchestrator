# mogui-ADE-orchestrator 문서화 계획 (스펙)

> **Status as of 2026-07-31: partly superseded. Read [`docs/README.md`](../../README.md) for the document set that actually exists.**
>
> Writing happened, but not into the structure planned in §1 below. The public set landed under `docs/public/` (overview, getting-started, concepts, master-lifecycle, delegation-and-review, reference) instead of `docs/architecture/` + `docs/decisions/` + `docs/diagrams/`, and `README.md` was promoted from the `docs/README-public-draft.md` draft this plan called for. Internal material now lives under `docs/internal/`.
>
> What this plan still governs: the crosscutting principles in §0 (measured claims only, the exact meaning of vendor neutrality, publication safety, plain tone, and the rule that design intent must be separated from current behavior) and the acceptance criteria in §7. Those are still the standard.
>
> What has not been delivered: per-unit design documents (§3), ADRs (§4), and mermaid diagrams (§5). Symbol tables in §3 are a 2026-07-25 snapshot and must be re-measured before use — the module layout has changed since (`acceptance/` was added, `adapters/` never existed as a top-level package).

- 작성일: 2026-07-25
- 상태: 설계 확정, 집필 대기 (위 Status 참조 — 부분 대체됨)
- 목적 우선순위: 내부 설계 정본(SSOT) = 포폴 = 오픈소스 공개용 (셋 다)

이 문서는 "무슨 문서를, 어떤 내용으로, 어떤 순서로" 만들지의 지도다. 실제 집필은 이 스펙을 계약으로 삼아 후속 세션에서 파견한다.

## 0. 관통 원칙 (모든 문서 공통)

1. **실측만.** 존재하는 유닛·심볼·스크립트·플래그만 기술한다. 확인 안 된 것은 쓰지 않는다. 근거는 `src/master_runtime/core/**`, `scripts/**`, `tests/**`.
2. **벤더 중립의 정확한 의미.** 벤더 중립은 **AI 에이전트 호스트**(Claude Code / codex / grok / cursor 등)에 묶이지 않는다는 뜻이다. 도구를 감추거나 추상적으로 얼버무리라는 뜻이 **아니다**:
   - 실제로 쓰는 도구는 이름을 정확히 쓴다 — **orca**(터미널·워크트리·파견 오케스트레이션), **beads/bd**(실행 상태 추적), **ctx**(세션 아카이브 인덱스), **Git**(장기 문서 정본).
   - core는 tool-name-free로 유지되고, 이 도구들은 `adapter` 레이어를 통해 연결된다. 문서에는 "대체재가 있으면 adapter 교체로 바꿀 수 있다"고 명시한다 (예: orca 대신 다른 오케스트레이터).
   - 즉 "core는 도구 이름을 모른다 + 실제 배선은 orca/beads/ctx다 + 교체는 adapter에서"를 한 세트로 기술한다.
3. **공개 안전.** 회사명·클라이언트명·개인 실명·사내 절대경로·내부 티켓번호(HF-*)·내부 호스트/IP 금지. `scripts/redaction-scan.sh`가 신규 유입을 차단하며, 히스토리 세척은 공개 직전 `git filter-repo`로 별도 수행(author·커밋 메시지·과거 blob의 식별자 제거).
4. **형식.** 마크다운 + mermaid(GitHub 네이티브 렌더). 정적 사이트(mkdocs/docusaurus)는 지금 범위 밖 — 마크다운을 잘 써두면 후속에서 감싸기만 하면 된다.
5. **톤.** 담백한 기술 서술. 과장·웅장 표현 금지.
6. **설계 의도와 현 실동작을 구분한다.** 자동으로 설계됐으나 현 실행 환경(Claude Code 증분 압축)에서 수동 트리거에 의존하는 부분은, "설계는 X, 현 환경에선 Y, 격차는 Z"로 격차를 명시한다. 작동하지 않는 것을 작동하는 것처럼 쓰지 않는다 — SSOT 신뢰·포폴 정직·공개 정확성 모두에 직결.

## 1. 문서 세트 구조 (A안)

```
docs/
  architecture/
    DOCUMENTATION-PLAN.md   ← 이 문서 (지도)
    overview.md             ← 시스템 진입 (세 목적 공통)
    <unit>.md               ← 유닛별 설계 (SSOT)
  decisions/
    ADR-XXXX-*.md           ← 왜 이렇게 설계했나 (SSOT + 포폴)
  diagrams/
    *.md (mermaid)          ← 아키텍처·시퀀스 (포폴 + 공개)
README.md                   ← docs/README-public-draft.md 승격, 위 문서로 링크
```

## 2. overview.md 명세

세 목적 공통 진입 문서. 구성:

- **시스템 정의 + 문제의식**: 장수(long-running) 마스터 AI 세션이 컨텍스트 한계·세션 교체·검증 부담을 겪을 때, 승계·계보·게이트·컴팩션 계측으로 이를 다루는 오케스트레이션 런타임. (기존 repo description 실측 확장)
- **유닛 지도** — 11개 core 유닛을 4묶음 + 경계로 제시:
  - **수명주기(lifecycle)**: `bootstrap` / `succession` / `recovery` / `lineage`
  - **제어(control)**: `approval` / `dispatch_gate` / `work_ledger`
  - **컨텍스트 품질(context quality)**: `context` / `digest_loop` (E12 회상 프로브)
  - **관측(observability)**: `watchdog`
  - **경계(boundary)**: `adapter` — core(tool-name-free)와 실제 도구(orca/beads/ctx/Git)를 잇는 레이어
- **데이터 흐름 한 장**: charter/문서(Git) → bootstrap → 마스터 세션 → dispatch_gate(파견 승인) → 워커 → work_ledger/lineage(기록) → 컴팩션 시 context/digest_loop 계측(현 환경에선 수동 `/compact` 트리거 의존 — §3.1) → 임계 시 succession(operator 지시 트리거, 자동 승계 금지).
- **벤더 중립 원칙** (0.2 방침대로 정확히).

## 3. 유닛별 문서 명세 (SSOT)

각 유닛 문서 공통 템플릿:

1. **무엇을 하나** (한 문단)
2. **공개 인터페이스** — 실측 심볼(아래 표)의 입출력·역할
3. **의존성** — 무엇에 기대나 (다른 유닛·adapter·외부 도구)
4. **핵심 불변식** — 반드시 지켜지는 규칙
5. **실패 모드** — 어떤 예외/거부가 언제 나나

실측 심볼 참조(집필 시 이 이름으로 정확히 기술, 집필 전 재실측 필수):

| 유닛 | 우선순위 | 실측 공개 심볼 (2026-07-25) |
|---|---|---|
| `succession` | **1차** | `SuccessionError`, `TriggerDecision`, `FrozenState`, `VerificationReport`, `SessionInfo`, `RetirementReport`, `detect_trigger`/`build_handoff`/`verify_successor`/`detect_duplicate_instances`/`retire_predecessor` (scripts/master-succeed 서브커맨드와 대응) |
| `lineage` | **1차** | `LineageValidationError`, `LineageAppendError`, `append_entry` (append-only 계보 장부) |
| `dispatch_gate` | **1차** | `ReasonCode`, `DispatchRequest`, `GateDecision`, 티켓 억제(TTL·1회 소비·suppress 기록), fail-closed |
| `context` + `digest_loop` | **1차** (E12) | `TriageClassification`, `JobStatus`, `ProcessStatus`, `JobLogClassification`, `RepoConfig`, `DigestConfig` — 컴팩션 직후 회상 계측. **현 상태 절 의무**(아래 §3.1) |
| `approval` | 2차 | 승인 게이트 (Proposal→Approval→Execution) |
| `recovery` | 2차 | `RecoveryConfig`, `RecoveryStep`, `RepositoryObservation`, `MonitorObservation`, `RecoveryReport`, `recover` |
| `work_ledger` | 2차 | `TrackState`, `WorkLedger`(ABC), `JsonlWorkLedger`, `WorkspaceRuntime` |
| `watchdog` | 2차 | `StallStatus`, `StallDecision`, `check_stall` (stall 판정 — died/timeout/empty 어휘 분리 유의) |
| `bootstrap` | 2차 | `BootstrapError`, `BootstrapConfig`, `RoleState`, `BootstrapResult`, `bootstrap` |
| `adapter` | 2차 | 벤더 중립 경계 — orca/beads/ctx/Git 배선, 교체 지점 |

### 3.1 E12(context/digest_loop) 현 상태 절 — 필수

E12 유닛 문서와 E12 ADR에 아래 "현 상태·한계"를 반드시 담는다. 이 격차를 숨기면 스펙 원칙 0.6 위반이다.

- **설계**: `SessionStart source=compact` 훅이 컴팩션 직후 회상 프로브를 자동 주입 → 기억으로 먼저 답하고 정본과 대조 → 임계 미달 반복 시 승계 제안.
- **현 실동작**: Claude Code가 증분 압축(대화를 조금씩 요약)으로 바뀌어 **큰 단일 compact 이벤트가 안 생기고, 그 결과 `source=compact` 자동 트리거가 걸리지 않는다.** (config로 증분 압축을 끄거나 단일 압축으로 되돌리는 공식 옵션은 없음 — 2026-07-25 조사.)
- **유효한 트리거**: 수동 `/compact` 실행은 `source=compact` 훅을 확실히 트리거한다(문서 확인). 따라서 E12 계측은 "수동 `/compact`를 계측점으로 강제하는 워크플로우"로 성립한다 — 억지 config가 아니라 이 방식이 정답.
- **열린 과제**: 수동 `/compact`를 안 하면 증분 압축의 누적 손실은 아무 계측 없이 지나간다(회상 사각지대). 자동 상시 계측·누적 손실 포착은 미해결 — 문서에 "열린 과제"로 명시.

## 4. ADR 명세 (SSOT + 포폴 서사)

각 ADR: 맥락 / 결정 / 근거 / 대안 / 결과. 초기 목록:

- **ADR: 승계 v3** — 새 판 클린 스폰 단일 절차, fork 승계 폐기(컨텍스트 유지할 거면 승계할 이유 없음), 모델 플래그+실측 불변식.
- **ADR: 게이트 fail-closed + 티켓 억제** — 규율만으로 파견 누락을 못 막아서 check→ticket→warn/suppress를 구조화. 미검증 잡은 UNVERIFIED로 거부.
- **ADR: E12 회상 프로브** — 컴팩션 손실을 "가정"하지 않고 회상 자가시험으로 "계측". 임계 미달 시 승계 제안(자동 승계 금지). **현 상태 절(§3.1) 필수**: 증분 압축으로 자동 트리거 미작동, 수동 `/compact`가 유효 트리거, 누적 손실 포착은 열린 과제.
- **ADR: tool-name-free core + adapter** — 벤더 중립(호스트 한정)의 구현. core는 도구 이름을 모르고 adapter가 orca/beads/ctx/Git을 배선, 교체는 adapter에서.
- **ADR: lineage append-only** — 계보는 관측 메타데이터, 부트·우선순위·모델 평가 입력으로 쓰지 않음.

## 5. 다이어그램 명세 (mermaid — 포폴 + 공개)

- **아키텍처 컴포넌트도**: 4묶음 유닛 + adapter 경계 + 외부 도구(orca/beads/ctx/Git).
- **승계 시퀀스**: 현직 승격 감사 → 클린 스폰 → 후임 생존 실측 → 은퇴·동결 → 후임 부팅·페인 철거·lineage append.
- **파견 게이트 흐름**: DispatchRequest → gate check(ALLOW/거부) → 티켓 발권 → 파견 → worker_done → 수락 검증.
- **E12 컴팩션 루프**: compact 이벤트 → 회상 프로브 주입 → 기억 우선 작성 → 정본 대조 → 임계 판정 → (승계 제안).

## 6. 집필 순서·규모

**1차 (다음 세션 첫 파견 — 포폴·공개에 바로 쓸 뼈대):**
overview.md + 유닛 4개(succession·lineage·dispatch_gate·context/digest_loop) + ADR 5개 + 다이어그램 4개 + README 승격.

**2차 (후속):**
나머지 유닛 6개(approval·recovery·work_ledger·watchdog·bootstrap·adapter).

라우팅: 문서 집필은 grok/claude 레인(codex 크레딧 상태와 무관하게 문서는 이 레인이 적합). 각 문서 집필 후 실측 대조(심볼·스크립트가 실제와 일치하는지) 게이트를 둔다.

## 7. 수용 기준

- 모든 유닛 문서의 심볼·인터페이스가 집필 시점 코드와 일치(실측 대조 통과).
- overview의 유닛 지도가 실제 core 파일 구성과 1:1.
- 벤더 중립 서술이 0.2 방침대로(도구 이름 명시 + adapter 교체 가능).
- redaction-scan 통과(회사·개인·내부 식별자 0).
- mermaid 다이어그램이 GitHub에서 렌더됨.
