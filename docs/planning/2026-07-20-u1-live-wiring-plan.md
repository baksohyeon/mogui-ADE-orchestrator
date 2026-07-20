# U1 Bootstrap 라이브 배선 v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polsia 마스터 세션 부팅에 U1 기반 `master-bootstrap-live`를 추가 훅으로 배선해 Role State 검증·이중 인스턴스 감지·bd 블록 예산 감사를 코드로 강제한다.

**Architecture:** 기존 `src/master_runtime/core/bootstrap.py`(U1)의 Role State 파서·이중 인스턴스 감지를 재사용하는 신규 모듈 `bootstrap_live.py` + CLI `scripts/master-bootstrap-live`. 플러그인 소유 bd prime은 건드리지 않고, 마스터 cwd에서만 도는 추가 SessionStart 훅이 동적 블록(~1KB)을 덧붙인다. 메모리 재발행 금지 — bd prime 블록의 감사만 한다.

**Tech Stack:** Python 3.9 호환(리포 기존 제약), stdlib only, pytest.

**스펙 정본:** ops-planning/docs/specs/2026-07-20-u1-bootstrap-live-wiring-design.md

## Global Constraints

- Python 3.9 호환 문법만 (기존 21모듈과 동일 — `X | None` 금지, `Optional[X]` 사용)
- stdlib 외 의존성 추가 금지
- 예산 상한 기본값 12000 chars, 초과·위반은 실패가 아니라 `[BUDGET-ALERT]`/`[AUDIT-ALERT]` 라인 (부팅은 절대 안 죽는다 — CLI는 내부 오류에도 폴백 라인 출력 후 exit 0)
- bd 호출은 subprocess, 실패 시 해당 섹션 생략 + 경보 라인 (bd 부재 환경에서도 동작)
- 메모리 본문 재출력 금지 — 감사 수치만
- 커밋 메시지: conventional, 한국어 제목 (리포 관례: `git log --oneline -5` 대조)

---

### Task 1: 최신 handoff 탐색 + Role State 재사용 노출

**Files:**
- Create: `src/master_runtime/core/bootstrap_live.py`
- Test: `tests/test_bootstrap_live.py`

**Interfaces:**
- Consumes: `master_runtime.core.bootstrap._parse_role_state`, `._role_state_block` (기존)
- Produces: `latest_handoff(handoff_dir: Path) -> Optional[Path]` (파일명 사전순 최대 = 최신, `*.md`만), `load_role_state(handoff_dir: Path) -> Tuple[Optional[str], List[str]]` — (role_state_block 텍스트, alerts). handoff 부재/파싱 실패 시 block=None + alert `"[AUDIT-ALERT] role-state: <사유>"`

- [ ] **Step 1: 실패 테스트 작성**

```python
from pathlib import Path
from master_runtime.core.bootstrap_live import latest_handoff, load_role_state

HANDOFF = """# handoff
## Role State
```
Current Role: Reference Implementation
Role Lock: ENABLED
Frozen: all other roles
Unlock: explicit user instruction only
```
"""

def test_latest_handoff_picks_lexicographic_max(tmp_path: Path) -> None:
    (tmp_path / "2026-07-19-a.md").write_text("x", encoding="utf-8")
    (tmp_path / "2026-07-20-gen6-handoff.md").write_text(HANDOFF, encoding="utf-8")
    assert latest_handoff(tmp_path).name == "2026-07-20-gen6-handoff.md"

def test_load_role_state_returns_block(tmp_path: Path) -> None:
    (tmp_path / "2026-07-20-gen6-handoff.md").write_text(HANDOFF, encoding="utf-8")
    block, alerts = load_role_state(tmp_path)
    assert "Current Role: Reference Implementation" in block
    assert alerts == []

def test_load_role_state_missing_dir_alerts(tmp_path: Path) -> None:
    block, alerts = load_role_state(tmp_path / "none")
    assert block is None
    assert any("role-state" in a for a in alerts)
```

- [ ] **Step 2: 실패 확인** — Run: `python3 -m pytest tests/test_bootstrap_live.py -v` / Expected: FAIL (ModuleNotFoundError)
- [ ] **Step 3: 최소 구현** — `bootstrap_live.py`에 위 두 함수 구현 (기존 bootstrap 모듈의 `_role_state_block` 재사용, 파싱 실패·부재는 alert 문자열 축적)
- [ ] **Step 4: 통과 확인** — 같은 커맨드, Expected: PASS (3 tests)
- [ ] **Step 5: Commit** — `git add src/master_runtime/core/bootstrap_live.py tests/test_bootstrap_live.py && git commit -m "feat(bootstrap-live): 최신 handoff 탐색과 Role State 적재"`

### Task 2: bd 블록 감사 (audit_memories)

**Files:**
- Modify: `src/master_runtime/core/bootstrap_live.py`
- Test: `tests/test_bootstrap_live.py` (추가)

**Interfaces:**
- Produces: `audit_memories(memories_text: str, cap: int = 15, budget_chars: int = 12000) -> Tuple[str, List[str]]` — (감사 요약 1줄, alerts). 입력은 `bd prime --memories-only` 출력. `### <key>` 블록 단위로 세고, 본문에 `[L0]` 포함=L0, `[L1]` 포함=L1, 둘 다 없으면 untagged

- [ ] **Step 1: 실패 테스트 작성**

```python
from master_runtime.core.bootstrap_live import audit_memories

MEMS = """### rule-a
내용 [L0] 규칙
### ptr-b
내용 [L1 포인터]
### naked-c
태그 없는 서사
"""

def test_audit_counts_tiers_and_flags_untagged() -> None:
    line, alerts = audit_memories(MEMS, cap=15, budget_chars=12000)
    assert "memories=3" in line and "L0=1" in line and "L1=1" in line and "untagged=1" in line
    assert any("untagged" in a for a in alerts)

def test_audit_alerts_over_cap_and_budget() -> None:
    many = "\n".join(f"### k{i}\n[L0] x" for i in range(16))
    line, alerts = audit_memories(many, cap=15, budget_chars=10)
    assert any("cap" in a for a in alerts)
    assert any("BUDGET-ALERT" in a for a in alerts)
```

- [ ] **Step 2: 실패 확인** — `python3 -m pytest tests/test_bootstrap_live.py -v` FAIL (ImportError)
- [ ] **Step 3: 최소 구현** — 블록 파싱은 `re.split(r"^### ", text, flags=re.M)`, 요약 라인 형식: `[BD-PRIME-AUDIT] memories=N (L0=a, L1=b, untagged=c), block=X.XKB — OK|ALERT (budget 12KB)`
- [ ] **Step 4: 통과 확인** — PASS (누적 5 tests)
- [ ] **Step 5: Commit** — `git commit -am "feat(bootstrap-live): bd 메모리 블록 감사 — 티어·상한·예산"`

### Task 3: 활성 트랙 수집 + compose

**Files:**
- Modify: `src/master_runtime/core/bootstrap_live.py`
- Test: `tests/test_bootstrap_live.py` (추가)

**Interfaces:**
- Produces: `collect_tracks(runner: Callable[[Sequence[str]], str]) -> Tuple[List[str], List[str]]` — runner는 argv를 받아 stdout을 돌려주는 주입 가능 함수(기본은 subprocess로 `bd list --status in_progress`), 제목 라인만 추출. 실패 시 빈 리스트 + alert.
  `compose(role_block, tracks, audit_line, alerts, dual_line, charter_pointer) -> str` — 섹션 순서: 헤더 `[MASTER-BOOTSTRAP v1]` / Role State / 활성 트랙 / Charter 포인터 1줄 / audit / dual / alerts. 자체 출력이 2000 chars 초과 시 트랙부터 절단 + `[BUDGET-ALERT] self-block`

- [ ] **Step 1: 실패 테스트 작성**

```python
from master_runtime.core.bootstrap_live import collect_tracks, compose

def test_collect_tracks_parses_titles() -> None:
    fake = lambda argv: "◐ AL-3be ● P1 OPS-02: batch 살리기\n◐ AL-mpr ● P1 QA-01: 마감\n"
    tracks, alerts = collect_tracks(fake)
    assert len(tracks) == 2 and alerts == []

def test_collect_tracks_runner_failure_alerts() -> None:
    def boom(argv):
        raise RuntimeError("bd missing")
    tracks, alerts = collect_tracks(boom)
    assert tracks == [] and any("tracks" in a for a in alerts)

def test_compose_orders_sections_and_caps_self_block() -> None:
    out = compose("Current Role: X", ["t"] * 500, "[BD-PRIME-AUDIT] ...", [], "[DUAL-INSTANCE] none", "Charter: Recovery Flow 0 정독")
    assert out.startswith("[MASTER-BOOTSTRAP v1]")
    assert len(out) <= 2200  # 절단 마커 여유 포함
    assert "[BUDGET-ALERT] self-block" in out
```

- [ ] **Step 2: 실패 확인** — FAIL / **Step 3: 최소 구현** / **Step 4: PASS (누적 8 tests)**
- [ ] **Step 5: Commit** — `git commit -am "feat(bootstrap-live): 활성 트랙 수집과 예산 내 compose"`

### Task 4: 이중 인스턴스 감지 통합 + CLI

**Files:**
- Create: `scripts/master-bootstrap-live`
- Modify: `src/master_runtime/core/bootstrap_live.py`
- Test: `tests/test_bootstrap_live.py` (추가)

**Interfaces:**
- Consumes: `master_runtime.core.bootstrap._detect_dual_instances`, `._default_process_probe` (기존 — 시그니처는 구현 시 원본 확인 후 그대로 사용)
- Produces: `run_live(handoff_dir, bd_runner, probe) -> str` (전 조립, 어떤 내부 예외도 잡아 `[BOOTSTRAP-FALLBACK] <사유>` 1줄 반환), CLI `master-bootstrap-live --handoff-dir <path> [--budget 12000] [--bd bd]` — stdout으로 블록 출력, **exit code는 항상 0** (Global Constraints)

- [ ] **Step 1: 실패 테스트 작성**

```python
import subprocess, sys
from pathlib import Path
from master_runtime.core.bootstrap_live import run_live

def test_run_live_never_raises(tmp_path: Path) -> None:
    def boom(argv):
        raise RuntimeError("everything broken")
    out = run_live(tmp_path / "none", bd_runner=boom, probe=lambda: "")
    assert "[MASTER-BOOTSTRAP v1]" in out or "[BOOTSTRAP-FALLBACK]" in out

def test_cli_exits_zero_with_missing_dir(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parent.parent / "scripts" / "master-bootstrap-live"
    proc = subprocess.run([sys.executable, str(script), "--handoff-dir", str(tmp_path / "none")], capture_output=True, text=True)
    assert proc.returncode == 0
    assert proc.stdout.strip() != ""
```

- [ ] **Step 2: 실패 확인** — FAIL / **Step 3: 구현** — CLI는 기존 `scripts/master-bootstrap`의 sys.path 부트 패턴 복제 / **Step 4: PASS (누적 10 tests)** / 전체 스위트 회귀: `python3 -m pytest tests/ -q` 전건 green
- [ ] **Step 5: Commit** — `git commit -am "feat(bootstrap-live): 이중 인스턴스 감지 통합 + CLI (부팅 불사 보장)"`

### Task 5: 훅 배선 + 드라이런 검증 (마스터 검수 단계 — 워커는 5a 검증까지만)

**Files:**
- Modify: `/Users/polsia/dev/work/Polsia/.claude/settings.json` (git 밖 — 변경 전문을 스펙에 추기해 기록 보존)

**Steps:**
- [ ] 5a. 워커: 드라이런 3종 실측 결과를 보고에 첨부 — ① `scripts/master-bootstrap-live --handoff-dir /Users/polsia/dev/work/Polsia/ops-planning/docs/handoffs` 출력 전문+바이트 수 ② 출력에 Role State·AUDIT 라인 존재 ③ exit 0
- [ ] 5b. 마스터: Polsia/.claude/settings.json의 hooks.SessionStart 배열에 추가(수동, 워커 권한 밖):

```json
{"matcher": "", "hooks": [{"type": "command", "command": "sh -c 'if [ \"$PWD\" = \"/Users/polsia/dev/work/Polsia\" ]; then /Users/polsia/dev/personal/mogui-ADE-orchestrator/scripts/master-bootstrap-live --handoff-dir /Users/polsia/dev/work/Polsia/ops-planning/docs/handoffs || echo \"[BOOTSTRAP-FALLBACK] master-bootstrap-live 실패\"; fi'"}]}
```

- [ ] 5c. 마스터: 훅 커맨드를 셸에서 직접 실행해 마스터 cwd에서 블록 출력, 워커 cwd(예: ops-planning)에서 무출력 실측
- [ ] 5d. 마스터: 변경 전문을 스펙 문서에 추기 커밋 (Polsia/.claude가 git 밖이므로 기록 보존)

### Task 6: 실부팅 수락 (마스터, 다음 세션)

- [ ] 다음 마스터 세션 부팅에서 실측: `[MASTER-BOOTSTRAP v1]` 블록 존재 + Role State 일치 + AUDIT 라인(memories=15, untagged=0) + bd prime 블록과 중복 없음 + 총 주입 ≤14KB. 결과를 bd 이슈에 기록 후 트랙 종결.

## Self-Review 결과

- 스펙 커버리지: 재결정(추가 훅) 반영 ✓ / 예산·경보 ✓ / 폴백(불사 CLI) ✓ / 워커 무영향(5c 검증) ✓ / 메모리 재발행 금지(감사만) ✓
- 플레이스홀더 없음. 시그니처 일관성: `run_live(handoff_dir, bd_runner, probe)` — Task 1~4 함수들을 조립. `_detect_dual_instances` 원 시그니처는 구현 시 원본 파일에서 확인하도록 명시(추측 서명 기재 대신).
