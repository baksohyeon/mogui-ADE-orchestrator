# 마스터 운영 온보딩

이 문서는 Stage 1 골격을 실제 워크스페이스/오케스트레이터 운영 레포로 바꾸는 Stage 2 실행 가이드입니다.

Stage 1은 아무것도 묻지 않습니다. 골격을 깔고 남은 placeholder를 출력합니다. Stage 2는 대화형입니다. AI host에 구조화 질문 도구가 있으면 그것을 쓰고, 없으면 일반 대화로 묻습니다. 각 단계에서 왜 필요한지 먼저 설명한 뒤 질문합니다.

마스터 운영 템플릿에서 허용되는 placeholder는 아래 7개뿐입니다.

- `{{WORKSPACE_NAME}}`
- `{{WORKSPACE_ROOT}}`
- `{{OPS_REPO}}`
- `{{MONITOR_NS}}`
- `{{MODEL_ID}}`
- `{{REPO_LIST}}`
- `{{RUNTIME_ROOT}}` — 이 오케스트레이터 레포 클론의 절대경로. 온보딩 에이전트가 자기 레포 루트로 스스로 채운다(3단계, 사용자 질문 불필요)

## 1단계. 워크스페이스 정보 수집

(a) 왜: 마스터 레이어는 개별 repo 위에서 움직이므로, 작업 라우팅과 배치 검증을 하려면 안정적인 이름, 경로, repo 목록이 먼저 필요합니다.

(b) 사용자에게 물을 것:

- 워크스페이스 이름
- 절대 경로의 워크스페이스 루트
- 마스터가 조율할 repo 목록
- 선호하는 operations repo 경로
- 모니터 namespace
- 부팅 때 실측할 기본 모델 식별자

(c) 에이전트 행동:

- 변경 전에 현재 파일을 읽습니다
- 경로를 정규화하되 없는 repo를 발명하지 않습니다
- 불확실한 값은 placeholder로 남기고 다시 묻습니다

(d) 검증:

- `{{WORKSPACE_ROOT}}`가 절대 경로입니다
- `{{OPS_REPO}}`가 절대 경로이거나 사용자가 승인한 repo 이름입니다
- `{{REPO_LIST}}`가 사용자가 준 repo 목록과 맞습니다

## 2단계. ops repo 생성

(a) 왜: 제품 코드와 거버넌스 운영은 소유 경계가 달라야 합니다. 권장 이름은 `<workspace>-ops`입니다. 제품 스코프와 거버넌스 스코프를 분리하면 파견, 메모리, lineage 기록 위치가 명확해집니다.

(b) 사용자에게 물을 것:

- 새 `<workspace>-ops` repo를 만들지, 기존 operations repo를 쓸지
- 로컬 git 초기화를 허용하는지

(c) 에이전트 행동:

- repo가 없고 생성 승인이 있으면 만듭니다
- 하네스 원본에서 Stage 1을 실행합니다:
  `bash scripts/setup-master-ops.sh <ops-repo-path>`
- 사용자가 명시하지 않으면 push하지 않습니다

(d) 검증:

- ops repo가 존재합니다
- ops repo에 `CLAUDE.md`와 `AGENTS.md`가 있습니다
- `docs/MASTER-OPERATIONS.md`가 있습니다
- Stage 1이 질문 없이 남은 placeholder를 출력했습니다

## 3단계. 템플릿 placeholder 치환

(a) 왜: 골격은 안정적으로 부팅될 만큼 로컬화되어야 하지만, 제품 repo에 속한 규칙을 마스터 레이어로 끌어오면 안 됩니다.

(b) 사용자에게 물을 것:

- 남은 placeholder 각각의 확정 값
- 마스터 조율에서 제외할 repo가 있는지

(c) 에이전트 행동:

- placeholder를 ops repo 전체에서 일관되게 치환합니다
- `{{RUNTIME_ROOT}}`는 이 오케스트레이터 레포 클론의 절대경로(현재 레포 루트)로 직접 채웁니다 — 사용자 질문 불필요
- 사용자가 host별 분기를 승인하지 않는 한 `CLAUDE.md`와 `AGENTS.md`를 byte-identical로 유지합니다
- 새 `{{...}}` placeholder를 만들지 않습니다

(d) 검증:

- 사용자가 값을 준 뒤 `{{...}}` placeholder가 남지 않습니다
- `CLAUDE.md`와 `AGENTS.md`가 같습니다
- 원본 워크스페이스의 비공개 고유명이 잘못 복사되지 않았습니다

## 4단계. 이슈 트래커 초기화

(a) 왜: 실행 상태는 문서보다 자주 바뀝니다. 이슈 트래커가 작업 상태 SSOT이고, Git은 승인된 계획·설계·결정·런북용입니다.

(b) 사용자에게 물을 것:

- Beads(`bd`) 등 어떤 이슈 트래커를 쓸지
- 지금 트래커 DB를 초기화할지

(c) 에이전트 행동:

- 선택한 트래커를 ops repo 안에서만 초기화합니다
- 작업 상태를 markdown TODO 파일이 아니라 트래커에 기록합니다
- 메모리에는 load-bearing 규칙과 포인터만 시드합니다

(d) 검증:

- 트래커 명령이 `{{OPS_REPO}}`에서 실행됩니다
- 워크스페이스 트래커 DB가 각 제품 repo의 트래커 DB와 분리되어 있습니다
- `bd where` 또는 대응 명령이 제품 repo가 아니라 ops repo를 가리킵니다

경고: Beads 같은 로컬 트래커는 repo별 DB를 가질 수 있습니다. 제품 repo의 DB를 워크스페이스 오케스트레이션에 재사용하지 마십시오.

## 5단계. 사용자 보편 규칙 메모리 시드

(a) 왜: 마스터는 여러 repo와 여러 세션을 조율합니다. 호칭, 언어, 승인 규율, 스코프 경계 같은 선호는 컴팩션과 인수인계 뒤에도 유지되어야 합니다.

(b) 사용자에게 물을 것:

- 선호하는 호칭
- 기본 답변 언어
- 실행, 파견, 브랜치 생성, 커밋, push, 배포 전 승인 규칙
- 상시 금지 규칙

(c) 에이전트 행동:

- 보편 운영 규칙을 선택한 메모리 시스템에 기록합니다
- 비공개 또는 민감 정보는 공개 문서에 넣지 않습니다
- 제품별 관례는 마스터 레이어가 아니라 각 제품 repo에 둡니다

(d) 검증:

- 메모리 검색으로 시드한 규칙이 조회됩니다
- 규칙이 짧고 실행 가능하며 Git 문서에 서사로 중복되지 않습니다

## 6단계. 설정 계층 안내

(a) 왜: hook과 도구 설정은 유용한 보장을 만들 수 있지만 민감 레인을 건드립니다. 마스터 템플릿은 동작 스펙만 제시하고 숨은 거부 목록이나 환경별 보안 구현을 싣지 않습니다.

(b) 사용자에게 물을 것:

- 마스터를 실행할 AI host
- hook 설치와 보안 민감 설정의 소유자
- dispatch 경고, role-state 주입, compaction probe hook을 켤지

(c) 에이전트 행동:

- `docs/MASTER-OPERATIONS.md`의 hook wiring spec을 제시합니다
- 구현은 사람 또는 전담 보안/운영 세션에 맡깁니다
- 인증, 권한, 시크릿, prod 데이터, credential 작업은 별도 민감 레인에 둡니다

(d) 검증:

- hook 스펙이 문서화되어 있습니다
- 온보딩 에이전트가 hook 구현체, 거부 목록, credential, secret path를 추가하지 않았습니다
- 민감 레인 소유자가 명시되었거나 미해결로 표시되었습니다

## 7단계. 창설 스폰

(a) 왜: 마스터는 온보딩 대화의 연장이 아니라, 배치가 검증된 깨끗한 새 세션으로 태어나야 합니다. 창설 스폰이 설치자(당신)와 운영자(새 마스터)를 분리해, 마스터가 클린 컨텍스트와 감사 가능한 배치 기록으로 시작하게 합니다.

(b) 사용자에게 물을 것:

- 지금 Generation 1 마스터를 스폰할지, 유예할지
- 마스터를 어느 터미널 환경에 띄울지 (호스트가 관리형 터미널을 제공하면 그것을 제안, 아니면 일반 새 세션)

(c) 에이전트 행동:

- 킥오프 파일 작성: 세대 번호 1, 창설 출처(이 온보딩 세션), 부팅 순서(운영 정본 재수화 → Role State 선언 → 모델·배치 실측), 초기 큐
- 관리형 스폰이 가능하면 실행:
  `{{RUNTIME_ROOT}}/scripts/master-succeed spawn --workspace-selector <워크스페이스 셀렉터> --kickoff-file <킥오프 파일> --root {{WORKSPACE_ROOT}} --model {{MODEL_ID}} --title "Gen-1 founding boot" --json`
  응답의 배치 검증이 MATCH일 때만 유효한 스폰으로 간주
- 관리형 스폰이 없는 호스트면: cwd를 `{{WORKSPACE_ROOT}}`로 한 새 에이전트 세션을 열고 킥오프 파일 내용을 첫 메시지로 붙여넣기 — 배치 검증은 8단계에서 수동 수행
- 이 온보딩 세션 안에서 마스터를 부팅하지 않는다 (절대)
- 주의: 설정 계층은 세션 시작 시점에 로드되므로, 설정 배치 후 반드시 새 세션으로 스폰한다

(d) 검증:

- 새 마스터 프로세스/세션이 정확히 1개 (이중 기동 금지)
- 관리형 스폰 경로: 배치 검증 MATCH 보고됨
- 마스터가 받은 킥오프 내용이 킥오프 파일과 일치

## 8단계. 첫 마스터 부팅 스모크

(a) 왜: 첫 부팅은 마스터가 role state를 선언하고, 실제 모델을 실측하며, 의도한 워크스페이스에 배치되었음을 증명하는 절차입니다.

(b) 사용자에게 물을 것:

- 초기 역할, 또는 구체 트랙 선택 전 Maintenance로 시작해도 되는지
- 모델과 배치 증거를 위한 로컬 read-only probe 실행 허용 여부

(c) 에이전트 행동:

- `docs/runbooks/role-state.md`를 Generation 1로 갱신합니다
- 대화에 Role State를 선언합니다
- host가 데이터를 제공하면 설정 모델과 실제 세션 모델을 실측합니다
- 배치 실측 3종 세트를 캡처합니다
- `docs/lineage/MASTER-LINEAGE.md`에 Generation 1을 append합니다

(d) 검증:

- Role State에 활성 역할이 하나만 있고 Role Lock이 켜져 있습니다
- 모델 측정 결과를 measured, unavailable, unsupported 중 하나로 보고합니다. 추측하지 않습니다
- 배치 실측 3종 세트가 있습니다:
  host pane 또는 worktree selector, `{{WORKSPACE_ROOT}}` 아래의 process cwd, session artifact 또는 log namespace
- 사용자가 의도적으로 미룬 값이 아니라면 unresolved placeholder가 남지 않습니다
