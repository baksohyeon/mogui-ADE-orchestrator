# 유닛 캠페인 2026-07-20 — 하네스 완주: 승계를 코드로

> Status: Approved (Owner, 2026-07-20 브레인스토밍 경유). 계획 v1(FROZEN 아키텍처의 분해)의 잔여 유닛 구현 캠페인. 이 문서는 계획 v1에 아무것도 추가하지 않는다 — 순서와 계약 골자만 확정한다.
> 배경: 같은 날 이중 Master 인스턴스 사고(example-ops 런 로그 R+12) — U8·U9 미구현이 구조적 원인으로 실증됨.

## 결정 사항 (브레인스토밍 Q&A)

1. **머지 선행**: 캠페인 0단계에서 기존 feat 브랜치 5개(U2·U5·U6·U11·U12)를 main에 머지. 인질 실증 3건 해소, U8·U9 통합 검증의 전제.
2. **스코프**: 계획 v1 구현 순서 라인의 잔여 5개 — U1·U10·U3·U8·U9. U4(Repo Runtime Loader)·U7(Role Runtime)은 순서 라인에 없음(계획 갭) — 계약 중 필요 실증 시 편입, 아니면 후속.
3. **페이싱**: 3병렬+2순차. U1∥U10∥U3(상호 독립, 워크트리 격리) → 각 착륙 검증·머지 → U8(단독) → U9(단독).

## 단계 구조

```
0단계  feat 5개 → main 머지 (U5 먼저)
1단계  U1 Bootstrap ∥ U10 Lineage ∥ U3 Workspace  (워크트리 3개 병렬)
        → 각 착륙 검증 → main 머지
2단계  U8 Recovery Manager  (main 기반 단독) → 검증 → 머지
3단계  U9 Succession Manager (main 기반 단독)
        → 승계 시나리오 통합 테스트 = MVP 수락 (c)
```

각 유닛은 독립 수락 — 어느 단계에서 끊겨도 안전한 중단점.

## 유닛별 계약 골자

### U1 Bootstrap
- `bootstrap(config) -> BootstrapResult`: Charter 적재, Role State 블록 파싱·검증, 예산 상한(chars) 내 L0/L1 주입 텍스트 생성.
- **세션 lease 훅**: 같은 세션ID의 타 claude 인스턴스 실측 시 부트 경고/거부. lease 본체는 U9 소속 — U1은 체크만 (분리안 합의).
- 실데이터 검증: 실제 MASTER-ORCHESTRATOR-CHARTER.md + gen5 핸드오프 1회 실기동.

### U10 Lineage Recorder
- `append(entry) -> None`: 13필드 스키마 검증(누락 거부), append-only 강제.
- **read API 없음** — 계획 v1 명문 불변식: lineage는 런타임에 역류 금지.
- 실데이터 검증: 실제 MASTER-LINEAGE.md 사본에 Gen 5 형식 dry-run append.

### U3 Workspace Runtime
- 중립 `WorkLedger` 인터페이스 + JSONL 참조 구현(dispatch-ledger 전례 답습): 활성 트랙 등록·갱신·복구, 세션 내 L1 캐시.
- bd(beads) 백엔드 연동은 U12 프로파일 후속으로 명시 파킹 (YAGNI).

### U8 Recovery Manager
- `recover(handoff, config) -> RecoveryReport`: Recovery Flow 0-6의 **read-only 실행기** — 각 단계가 실측 프로브(차터 존재, 핸드오프 파싱, Git SSOT rev-parse, 모니터 생존)를 돌고 리포트 산출.
- 자동 조치 없음 — L1 사다리 준수. 재무장·킬은 수동 유지.
- 실데이터 검증: gen5 핸드오프 입력 → 2026-07-20 수동 복구 결과와 대조.

### U9 Succession Manager
- ① trigger 판정(Immediate/Advisory) ② thin handoff 생성 ③ successor 검증 체크리스트 ④ 전임 은퇴 검증(PID 커맨드라인 대조) ⑤ **세션 lease**(`~/.mogui/master-lease.json` — acquire/release/probe, 이중 Master 차단).
- 이중 인스턴스 사고(R+12)의 코드 처방.

## 파견·검증 규율

- 전 잡: 게이트 check → 파견 → register (probe 실측).
- 1단계 3잡: 병렬 쓰기 → 워크트리 격리 (조건부 규칙 ①).
- 계약 공통 제약: py3.9 import 호환 / 커밋 금지(커밋=마스터 수락 행위) / **테스트 픽스처는 실데이터 포맷 의무** — U11 1차 반려(fake 마커 창작)의 재발 방지 조항.
- 착륙 검증 4항목 패턴: pytest 직접 실행 / py3.9 import / 실데이터 실기동 / 변경 범위 대조.

## 종착: 승계 시나리오 통합 테스트

U9 착륙 후 시뮬레이션 모드로 전 유닛 관통: handoff 생성(U9) → 복구 실행(U8, U1·U3 소비) → successor 검증(U9) → lineage append(U10). 통과 시 MVP (a)(c) 충족 — (b) 위임 루프는 U5·U12로 기실증이므로 **계획 v1 MVP 전체 달성**.

## 리스크·아웃 오브 스코프

- 게이트 한계 2건(의미 중복 계약 미검출, register 교차 결합)은 스코프 밖 — U5 후속 bd 이슈로 등록만.
- U8 자동 조치(킬·재무장 실행)는 L2 영역 — 보류.
- 분량 리스크: 3단계 미도달 시 U9는 익일 — 독립 수락 구조라 중단 안전.
