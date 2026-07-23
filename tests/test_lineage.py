from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from master_runtime.core.lineage import LineageValidationError, append_entry


GEN5_FIXTURE = """# Master Lineage — 승계 계보 장부

> **OBSERVABILITY ONLY.** 이 장부는 역사 메타데이터다. Runtime memory가 되어서는 안 되고, 어떤 실행 의사결정에도 영향을 주어서는 안 된다. 회고·승계 품질 분석·운영 지표·포트폴리오 용도로만 쓴다. append-only — 기존 항목은 수정하지 않는다.

---

## Gen 5 — 2026-07-20 오후

- **Generation**: 5
- **Parent Session**: 39c1ec17 (claude PID 40309, Fable 5)
- **Successor Session**: 0464cb11 (claude PID 19909, Fable 5)
- **Timestamp**: 2026-07-20 오후 (승계 지시) / 15:02 successor 전임 종료 확인
- **Inherited Role**: Reference Implementation (Role Lock ENABLED — 승계는 역할을 바꾸지 않는다). Gen 4 대의 Role Switch(Release/Operations → Reference Implementation, R+0 Dorito 승인)를 그대로 상속
- **Succession reason**: Advisory 임계 (전임 컨텍스트 UI 실측 63%, Dorito 지시 "승계 진행해")
- **Recovery sources**: Charter (Git, specs/MASTER-ORCHESTRATOR-CHARTER.md) / thin handoff (docs/handoffs/2026-07-20-gen5-handoff.md) / 런 로그 (docs/drafts/2026-07-20-harness-impl-run-log.md — 임시 승계 문서, R+0~R+8) / bd (ready 15 + in_progress 6) / mogui-ADE-orchestrator 실측 (feat/u11 체크아웃·ddafcc7 확인) / 게이트 대장 ~/.mogui/dispatch-ledger.jsonl (세션 밖 SSOT, 그대로 사용) / U11 잡 companion status 실측 (running). Trace Archive 검색 0회 (miss 없음)
- **Inherited open tracks**: 7 (U11 트리아지 정련 착륙 검증 [활성, task-mrstc9ju-5pfj7d running·verifying 실측] / U1 Bootstrap + L1 루프 배선 [다음 순서, Dorito "추천대로 진행" 승인] / feat 브랜치 5개 main 머지 [Dorito 결정 대기, 인질 실증 3건으로 우선순위 높음] / 블로그 3건: 하네스 후속 포스트 파킹·118 티스토리 교체 게시 대기·2편 발행 파킹 / mogui-agent-harness PR #4 머지 [Dorito] / AHE 연구 Stage 2 FROZEN + rules/ 7문서 승인 대기 [파킹] / 7/17 배포 후속 bd [파킹])
- **Verification**: **PASS** — 기준선 재실측: product-a dev=4055ed9d clean / frontend-app dev=06db83dc clean (핸드오프 "이동했을 수 있음" 추정과 달리 불변). U11 잡 running 실측 (companion status, cwd=mogui-ADE-orchestrator). 게이트 대장 실존·최신 엔트리에 U11 잡 ALLOW 기록 확인. Gen 5 드리프트 모니터 재무장 후 첫 하트비트 확인 (15:01, 무드리프트)
- **Repeated-question count**: 0
- **Reopened-decision count**: 0
- **Context-loss summary**: 없음 확인 — U11 검증 계약 4항목·파견 규율·워크트리 지도·유닛 현황판(R+7)·U12 방향 확정(R+5) 전부 핸드오프·런 로그에서 무손실 인수
- **Predecessor retirement verified**: YES — PID 40309 커맨드라인("Gen 4 후임") 대조 후 해당 PID만 kill, ps 재확인으로 소멸 확증, 타 claude 프로세스(19909=본 세션·34357·7068) 무영향 확인 (15:02)
- **Notes**: 전임 orphan drift-monitor(PID 50179, 39c1ec17 scratchpad 경로 대조) 종료 후 Gen 5 소유로 재무장(이중실행 가드 내장, 자기 PID 실측 19909, 모니터 PID 33196). companion CLI가 셸 커맨드가 아니라 codex 플러그인 스크립트(codex-companion.mjs)임을 실측으로 확인 — 핸드오프에 호출 방법 미기재였으나 miss 아님(플러그인 경로 탐색으로 자체 해결).
"""


def valid_entry(generation: int = 6) -> dict[str, object]:
    return {
        "generation": generation,
        "parent_session": "0464cb11 (claude PID 19909, Fable 5)",
        "successor_session": "u10-test-successor (Fable 5)",
        "timestamp": "2026-07-20 오후 (U10 dry-run)",
        "inherited_role": "Reference Implementation (Role Lock ENABLED — 승계는 역할을 바꾸지 않는다)",
        "succession_reason": "U10 Lineage Recorder dry-run append verification",
        "recovery_sources": "Charter (Git) / thin handoff / bd prime / pytest fixture",
        "inherited_open_tracks": "1 (U10 Lineage Recorder 착륙 검증)",
        "verification": "PASS",
        "repeated_question_count": 0,
        "reopened_decision_count": 0,
        "context_loss_summary": "없음 확인 — dry-run fixture preserves existing bytes",
        "predecessor_retirement_verified": "YES — dry-run only, no real predecessor touched",
        "notes": "실데이터 Gen 5 형식 기반 테스트 항목",
    }


class LineageRecorderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "MASTER-LINEAGE.md"
        self.path.write_text(GEN5_FIXTURE, encoding="utf-8")

    def test_append_entry_adds_gen_section(self) -> None:
        append_entry(self.path, valid_entry())

        content = self.path.read_text(encoding="utf-8")
        self.assertIn("## Gen 6 — 2026-07-20 오후 (U10 dry-run)", content)
        self.assertIn("- **Generation**: 6", content)
        self.assertIn("- **Verification**: **PASS**", content)
        self.assertIn("- **Notes**: 실데이터 Gen 5 형식 기반 테스트 항목", content)

    def test_missing_required_field_is_rejected(self) -> None:
        entry = valid_entry()
        del entry["parent_session"]

        with self.assertRaises(LineageValidationError):
            append_entry(self.path, entry)

    def test_unknown_verification_is_rejected(self) -> None:
        entry = valid_entry()
        entry["verification"] = "UNKNOWN"

        with self.assertRaises(LineageValidationError):
            append_entry(self.path, entry)

    def test_duplicate_generation_is_rejected(self) -> None:
        with self.assertRaises(LineageValidationError):
            append_entry(self.path, valid_entry(generation=5))

    def test_existing_content_bytes_are_unchanged(self) -> None:
        original = self.path.read_bytes()

        append_entry(self.path, valid_entry())

        updated = self.path.read_bytes()
        self.assertEqual(original, updated[: len(original)])

    def test_validation_failure_leaves_file_unchanged(self) -> None:
        original = self.path.read_bytes()
        entry = valid_entry()
        entry["repeated_question_count"] = -1

        with self.assertRaises(LineageValidationError):
            append_entry(self.path, entry)

        self.assertEqual(original, self.path.read_bytes())

    def test_real_lineage_copy_dry_run_preserves_original_prefix(self) -> None:
        source = Path("/Users/polsia/dev/work/Polsia/ops-planning/docs/lineage/MASTER-LINEAGE.md")
        if not source.exists():
            self.skipTest("real MASTER-LINEAGE.md source is unavailable")

        dry_run_path = Path(self.tempdir.name) / "MASTER-LINEAGE-copy.md"
        shutil.copyfile(source, dry_run_path)
        original = dry_run_path.read_bytes()

        append_entry(
            dry_run_path,
            valid_entry(generation=_next_generation(dry_run_path)),
        )

        self.assertEqual(original, dry_run_path.read_bytes()[: len(original)])
        self.assertEqual(original, source.read_bytes())


def _next_generation(path: Path) -> int:
    generations: list[int] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("- **Generation**: "):
            continue
        value = line.rsplit(":", maxsplit=1)[1].strip()
        if value.isdigit():
            generations.append(int(value))
    return max(generations, default=0) + 1


if __name__ == "__main__":
    unittest.main()
