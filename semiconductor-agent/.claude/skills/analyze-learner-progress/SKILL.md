---
name: analyze-learner-progress
description: 학습자의 누적 평가에서 약점 도메인을 분석하고 맞춤 일일 루틴을 설계한다. 진도 분석, 주간 회고 해석, 다음 학습 추천, 운영비 점검. "진도 분석", "약점 진단", "다음 루틴 추천", "주간 회고 해석" 요청 시 사용. 학습자 진도 운영 작업이면 반드시 이 스킬을 쓴다.
---

# 학습자 진도 분석

learner-progress-analyst 에이전트가 누적 평가를 분석해 학습 경로를 설계하는 절차.

## 데이터 소스

- `.agent_state.db` — LangGraph SqliteSaver, thread_id별 누적 `evaluations`
- `usage.jsonl` — 노드별·모델별 호출·비용 로그
- env: `THREAD_ID`(기본 hans), `AGENT_DB`(기본 .agent_state.db), `USAGE_LOG_PATH`(기본 usage.jsonl)

## 워크플로우

### 1. 누적 평가 집계
```bash
uv run python scripts/weekly_review.py       # 도메인별 점수 추이 + 7일 사용 통계 차트(png)
```
직렬화된 `domain` 필드로 도메인별 점수를 집계한다(텍스트 추정 아님 —
`aggregate_eval_history` 기준). 도메인: 소자/공정/회로/트렌드.

### 2. 약점 진단
- 도메인별 평균 최저 = 다음 집중 대상.
- 평균뿐 아니라 추세(개선/정체/악화)도 본다.
- 표본이 적으면(<5건) "표본 적음" 경고를 붙인다.

### 3. 다음 루틴 설계 (행동으로)
"공정이 약함"에서 멈추지 말고 실행 가능한 스텝으로:
```
다음 루틴: 공정 3문제 (DAILY_COMPANY=samsung_ds, DAILY_MAX_Q=3)
복습 포인트: ALD self-limiting/conformality, CVD gas-phase 차이
근거: 공정 평균 52점(직전 49 → 개선 중), 트렌드 71점 대비 약함
```

### 4. 운영비 점검
`usage.jsonl`의 노드별·모델별 호출·비용으로 학습량 대비 비용을 본다. 비용이 과하면
tier 조정 제안: premium(gpt-4o+sonnet) / standard(mini+haiku, 1/5) / budget(mini, 1/10).

## 산출물

`_workspace/progress_<날짜>.md`:
- 도메인별 점수·추세 + 약점 도메인
- 다음 일일 루틴 설계
- 사용량/비용 요약 + tier 제안(있으면)

## 원칙

- DB·로그가 비었으면(첫 사용) "데이터 부족 — 기준선 수집" 보고, 추정 진단 금지.
- judge 변별이 깨졌으면(eval-quality-monitor 보고) 점수 해석을 보류한다 — 신뢰
  불가한 점수로 진도를 단정하지 않는다.
