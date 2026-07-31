이 레퍼런스는 이 레포지터리의 실행형 스크립트를 요약합니다. 생성 구간은 로컬 `scripts/` help 출력에서 가져온 정보에 근거합니다.

# 레퍼런스

명령을 찾을 때 이 문서를 사용합니다. 각 진입점을 언제 사용할지는 생애주기 문서와 위임 문서가 설명합니다.

<!-- AUTO-GENERATED from scripts/ --help -->
| 스크립트 | 명령 | 용도 | 핵심 옵션 |
| --- | --- | --- | --- |
| `scripts/adapter` | `adapter doctor` | 보이는 adapter 도구와 필수 로컬 의존성 존재 여부를 보고합니다. | `-h` 또는 `--help` 외 없음. |
| `scripts/adapter` | `adapter dispatch` | adapter layer를 통해 작업자를 계획하거나 시작합니다. | `--contract`, `--repo`, `--isolation {auto,shared,worktree}`, `--runtime {codex}`, `--agents`, `--est-chars`, `--ledger`, `--dry-run`. |
| `scripts/dispatch-gate` | `dispatch-gate check` | 작업자 계약을 평가하고 allow 또는 deny 결정을 파견 원장에 기록합니다. | 전역 `--ledger`; 명령 옵션 `--runtime`, `--contract`, `--agents`, `--est-chars`. |
| `scripts/dispatch-gate` | `dispatch-gate register` | 프로브가 예상 산출물에서 job id를 확인한 뒤에만 작업자 job을 등록합니다. | 전역 `--ledger`; 명령 옵션 `--job-id`, `--probe-cmd`, `--contract-sha`, `--runtime`. |
| `scripts/dispatch-gate` | `dispatch-gate watch` | 작업자 로그의 stall 상태를 확인합니다. | 전역 `--ledger`; 명령 옵션 `--log`, `--max-idle`. |
| `scripts/l1-digest` | `l1-digest tick` | config 파일 기준으로 읽기 전용 L1 digest 관측 tick을 한 번 실행합니다. | `--config`. |
| `scripts/master-bootstrap` | `master-bootstrap` | charter, 선택적 handoff, 예산, session id, 역할 상태 확인에서 제한된 bootstrap 블록을 만듭니다. | `--charter`, `--handoff`, `--budget`, `--session-id`, `--strict-lease`, `--json`. |
| `scripts/master-bootstrap-live` | `master-bootstrap-live` | handoff directory와 선택적 role-state file에서 live session-start bootstrap 블록을 출력합니다. | `--handoff-dir`, `--role-state-file`, `--budget`, `--bd`. |
| `scripts/master-recover` | `master-recover` | recovery 입력을 검사하고 master session recovery report를 만듭니다. | `--charter`, `--handoff`, `--ledger`, `--repo`, `--monitor-pattern`, `--session-id`, `--json`. |
| `scripts/master-succeed` | `master-succeed detect` | 승계 trigger 문장과 선택적 context pressure를 분류합니다. | `text`, `--context-ratio`, `--json`. |
| `scripts/master-succeed` | `master-succeed handoff` | JSON spec에서 얇은 handoff를 만듭니다. | `--spec`, `--json`. |
| `scripts/master-succeed` | `master-succeed verify-successor` | successor recovery report를 검증합니다. | `--report`, `--json`. |
| `scripts/master-succeed` | `master-succeed check-duplicates` | 현재 handle을 제외하고 marker 기준 중복 master instance를 탐지합니다. | `--self-handle`, `--marker`, `--json`. |
| `scripts/master-succeed` | `master-succeed retire` | predecessor terminal 또는 session 후보를 정확히 하나로 해석하고 선택적으로 닫습니다. | `--self-handle`, `--expected`, `--target-handle`, `--target-pty-id`, `--target-session-id`, `--execute`, `--json`. |
| `scripts/master-succeed` | `master-succeed spawn` | 선택한 workspace에 깨끗한 successor terminal을 spawn하거나 dry run합니다. | `--workspace-selector`, `--kickoff-text` 또는 `--kickoff-file`, `--root`, `--model`, `--title`, `--dry-run`, `--json`. |
| `scripts/model-identity-probe` | `model-identity-probe` | transcript의 최근 assistant event에서 측정 모델을 읽고, 기대 모델이 있으면 비교합니다. | `--transcript`, `--expect`, `--limit`. |
| `scripts/redaction-scan.sh` | `redaction-scan.sh` | 공개 전 tracked, staged, range 파일에서 secret과 내부 식별자를 스캔합니다. | `--staged`, `--range A..B`, `--help`; allowlist 기본값은 `scripts/redaction-allowlist.txt` 또는 `REDACTION_ALLOWLIST`. |
<!-- END AUTO-GENERATED from scripts/ --help -->

생성 표는 공개 명령 표면만 나열합니다. 로컬 호스트 라우팅, 개인 경로, 민감 레인 세부사항은 이 레퍼런스 밖에 둡니다.
