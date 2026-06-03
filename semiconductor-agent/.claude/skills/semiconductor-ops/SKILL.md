---
name: semiconductor-ops
description: 반도체 면접 교육 에이전트의 운영을 조율하는 오케스트레이터. 문제은행 큐레이션·평가 품질 모니터링·산업 동향 갱신·학습자 진도 분석·정확성 검수를 서브에이전트로 분배한다. "운영 점검", "주간 운영", "일일 운영", "콘텐츠 갱신", "운영 하네스 실행", "다시 실행", "운영 업데이트", "약점 보강", "동향 반영", "평가 품질 점검" 요청 시 반드시 이 스킬을 사용. 개별 운영 작업이 아니라 여러 운영을 묶어 돌릴 때 이 오케스트레이터를 쓴다.
---

# 반도체 면접 교육 에이전트 운영 오케스트레이터

semiconductor-agent 제품을 최신·고품질 상태로 유지하는 운영 팀을 조율한다.
**실행 모드: 서브에이전트** (Agent 도구 직접 호출, 팀 통신 불필요).
**아키텍처: 감독자(Supervisor) + 생성-검증(Generate-Verify).**

## 운영 팀 (5 에이전트, 모두 `model: "opus"`)

| 에이전트 | subagent_type | 역할 | 스킬 |
|---------|---------------|------|------|
| question-bank-curator | general-purpose | 문제은행 큐레이션 | curate-question-bank |
| trend-curator | general-purpose | 산업 동향 갱신 | curate-trends |
| eval-quality-monitor | general-purpose | 평가 품질 모니터링 | monitor-eval-quality |
| learner-progress-analyst | general-purpose | 학습자 진도 분석 | analyze-learner-progress |
| accuracy-reviewer | general-purpose | 정확성 검수(QA 게이트) | review-accuracy |

> 각 Agent 호출 시 반드시 `model: "opus"`를 명시하고, 해당 에이전트 정의(`.claude/agents/`)와
> 스킬을 읽게 한다. 검증 스크립트 실행이 필요하므로 모두 `general-purpose` 타입을 쓴다
> (읽기 전용 Explore 금지).

## Phase 0: 컨텍스트 확인

먼저 `_workspace/` 존재로 실행 모드를 판별한다:
- `_workspace/` 없음 → **초기 실행**
- `_workspace/` 있음 + 사용자가 부분 수정 요청(예: "동향만 다시") → **부분 재실행**(해당 에이전트만)
- `_workspace/` 있음 + 새 운영 요청 → **새 실행**(기존을 `_workspace_prev/`로 이동)

`_workspace/`가 없으면 만든다. 산출물 규칙: `{phase}_{agent}_{artifact}.md`,
중간 파일은 `_workspace/`에 보존(감사 추적), 최종 운영 리포트만 사용자에게 보고.

## Phase 1: 운영 범위 결정

요청에서 케이던스/범위를 파악한다:

| 범위 | 트리거 예 | 호출 에이전트 |
|------|----------|--------------|
| **일일 운영** | "일일 운영", "오늘 점검" | learner-progress-analyst (+ eval 빠른 확인) |
| **주간 운영** | "주간 운영", "운영 점검" | 5개 전부 |
| **콘텐츠 갱신** | "동향 반영", "문제 보강" | trend-curator → question-bank-curator → accuracy-reviewer |
| **품질 점검** | "평가 품질 점검" | eval-quality-monitor (+ accuracy-reviewer 라벨 확인) |

불확실하면 주간 운영(전체)로 본다.

## Phase 2: 분배 + 생성-검증 게이트

**실행 모드: 서브에이전트.** Agent 도구로 호출하고, 독립 작업은 `run_in_background: true`로
병렬 실행한다. 데이터는 `_workspace/` 파일 기반 + 반환값으로 주고받는다.

### 2-1. 독립 수집 (병렬)
서로 의존이 없는 수집/분석은 동시에 띄운다:
```
Agent(eval-quality-monitor,   model="opus", run_in_background=true)
Agent(learner-progress-analyst, model="opus", run_in_background=true)
Agent(trend-curator,          model="opus", run_in_background=true)
```
각 에이전트는 자기 스킬을 읽고 `_workspace/`에 산출물을 쓰고 경로를 반환한다.

### 2-2. 콘텐츠 생성 (의존)
trend-curator 산출물(트렌드 질문 후보)이 나오면 question-bank-curator가 이를 입력으로
문제은행 제안을 만든다:
```
Agent(question-bank-curator, model="opus")   # trends_*.md를 입력으로
```

### 2-3. 검증 게이트 (필수)
**큐레이터가 만든 콘텐츠는 accuracy-reviewer 검수를 통과해야 코드에 반영된다.**
```
Agent(accuracy-reviewer, model="opus")        # qbank_*.md / trends_*.md 검수
```
- ✅통과 → 큐레이터가 코드 Edit (또는 검수자가 직접) → `uv run pytest tests/ -q` 회귀 확인
- ✏️수정요청 → 해당 큐레이터 1회 재호출(지적 사항만 수정) → 재검수
- ❌반려 / 확인 필요 → 코드 미반영, 운영 리포트에 사유 명시

학습자 진도(learner-progress-analyst)는 eval-quality-monitor의 순서 통과를 전제로
해석한다 — 변별이 깨졌으면 진도 해석을 보류하고 평가 품질 복구를 우선 보고한다.

## Phase 3: 종합 리포트

모든 산출물(`_workspace/*.md`)을 모아 운영 리포트를 종합한다:
```
## 운영 리포트 ({날짜}, {범위})
- 평가 품질: 순서 {통과/실패}, 변별폭 {N}점, 추세 {↑/→/↓}
- 학습자 진도: 약점 {도메인}, 다음 루틴 {요약}
- 문제은행: 추가 {N}개(검수 {통과/대기}), 커버리지 {빈 영역}
- 산업 동향: 신규 {N}건, 교체 제안 {M}건
- 검수 게이트: 통과 {N} / 수정 {M} / 반려 {K}
- 코드 반영: {파일 목록} (회귀 테스트 {통과/실패})
- 후속 권고: {다음 운영에서 할 일}
```

## 데이터 전달 프로토콜

| 전략 | 방식 | 적용 |
|------|------|------|
| 반환값 기반 | Agent 반환 메시지로 경로+한줄요약 수집 | 모든 에이전트 |
| 파일 기반 | `_workspace/{phase}_{agent}_{artifact}.md` | 큐레이터 산출물, 검수, 리포트 |

## 에러 핸들링

- 에이전트 1회 재시도 후 재실패 → 해당 결과 없이 진행, 리포트에 **누락 명시**.
- API 키 미설정(eval) → "미실행"으로 보고, 점수 추정 금지.
- 검수 반려 콘텐츠 → 삭제하지 말고 `_workspace/`에 사유와 함께 보존.
- 코드 반영 후 `pytest` 실패 → 즉시 롤백 권고 + 회귀 지점 보고(자동 반영 강행 금지).
- 상충 동향 정보 → 출처 병기, 단일값 단정 금지.

## 테스트 시나리오

**정상 흐름 (주간 운영):**
"주간 운영 점검해줘" → Phase 0 초기 실행 → eval/진도/동향 병렬 수집 →
question-bank-curator가 동향 기반 질문 제안 → accuracy-reviewer 검수(통과분만 반영) →
`pytest` 회귀 확인 → 종합 리포트.

**에러 흐름 (평가 품질 실패):**
eval-quality-monitor가 트렌드 도메인 순서 실패(P1) 보고 → 진도 분석가는 점수 해석 보류 →
리포트 최상단에 "judge 트렌드 변별 결함 — 골든셋/프롬프트 점검 필요" 경보 →
question-bank/trend 큐레이션은 계속 진행하되, 평가 품질 복구를 최우선 후속으로 권고.

## 후속 작업

- 부분 재실행: "동향만 다시" → trend-curator + accuracy-reviewer만 재호출.
- 같은 피드백 2회 반복 / 에이전트 반복 실패 → 하네스 진화 제안(에이전트·스킬·CLAUDE.md 갱신).
- 모든 변경은 CLAUDE.md 변경 이력에 기록한다.
