이 quickstart는 로컬 clone에서 런타임을 살펴보고, 테스트를 실행하고, 마스터 온보딩 흐름으로 들어가는 최소 경로입니다.

# 시작하기

이 레포지터리는 라이브러리 의존성이 아니라 운영 하네스로 쓰입니다. 먼저 clone하고 로컬 확인을 실행한 뒤, 온보딩 가이드로 워크스페이스용 운영 레포지터리를 만들거나 설정합니다.

## Clone

```bash
git clone <repository-url> orchestrator
cd orchestrator
```

## 런타임 확인

레포지터리 루트에서 테스트를 실행합니다.

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

로컬 어댑터 도구가 보이는지 확인합니다.

```bash
scripts/adapter doctor
```

## 에이전트 세션 시작

최초 설정에서는 installer 대화 안에서 마스터를 부트하려 하지 않습니다. 온보딩 가이드는 워크스페이스 정보 수집, 운영 레포지터리 초기화, placeholder 채우기, 이슈 트래커 선택, Generation 1 마스터 세션 창설 절차를 설명합니다.

다음 문서로 이어갑니다.

- [master-ops/ONBOARDING.md](../../../master-ops/ONBOARDING.md)
- [한국어 미러](../master-ops/ONBOARDING.md)

호스트가 Orca 관리 터미널을 지원하면 온보딩에서 `scripts/master-succeed spawn`으로 창설 마스터를 만들 수 있습니다. 지원하지 않으면 워크스페이스 루트에서 깨끗한 에이전트 세션을 열고, 온보딩 중 만든 kickoff 텍스트를 첫 메시지로 붙여 넣습니다.

## 첫 부트 스모크

온보딩이 운영 파일을 만든 뒤 첫 마스터 부트는 세 가지 사실을 증명해야 합니다.

```text
Role State is declared.
The configured model and measured model are reported separately.
Placement evidence matches the intended workspace.
```

관련 스크립트 진입점:

```bash
scripts/master-bootstrap \
  --charter master-ops/docs/MASTER-OPERATIONS.md \
  --json

scripts/master-bootstrap-live \
  --handoff-dir ./handoffs \
  --role-state-file master-ops/docs/runbooks/role-state.md
```

> 팁: 이 문서는 짧게 유지합니다. 자세한 설치 흐름은 온보딩 가이드가, 부트와 승계 세부사항은 생애주기 문서가 맡습니다.

다음 문서: [개념](concepts.md), [마스터 생애주기](master-lifecycle.md).
