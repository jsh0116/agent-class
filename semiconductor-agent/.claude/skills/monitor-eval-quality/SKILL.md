---
name: monitor-eval-quality
description: judge 평가 품질을 골든셋으로 측정·추적한다. 골든셋 스위트 실행, 순서일관성·변별폭 점검, 드리프트 감지, 골든셋 케이스 추가 제안. "평가 품질 점검", "골든셋 실행", "judge 변별 확인", "eval 모니터링" 요청 시 사용. 평가 품질 운영 작업이면 반드시 이 스킬을 쓴다.
---

# 평가 품질 모니터링

eval-quality-monitor 에이전트가 judge→critic 파이프라인의 변별력을 측정·추적하는 절차.

## 무엇을 검증하나

사용자가 실제로 보는 점수 = judge → adaptive critic skip(31~84점만 critic) → 최종.
골든셋은 이 **전체 파이프라인**을 검증한다(judge 단독 아님). 핵심 지표는 **순서 일관성**:
같은 질문에서 우수 > 보통 > 미흡 점수가 유지되는가.

## 대상

- `tests/eval/golden_set.py` — 라벨링된 케이스(4도메인 × 우수/보통/미흡)
- `tests/eval/test_judge_quality.py` — band + ordering + 변별폭 검증
- `scripts/eval_judge.py` — 리포트(md+png) + 순서 실패 시 exit 2

## 워크플로우

### 1. 골든셋 실행
```bash
uv run pytest -m eval tests/eval/ -v        # OPENAI_API_KEY + ANTHROPIC_API_KEY 필요
uv run python scripts/eval_judge.py          # 리포트 생성 + 순서 실패 시 exit 2
```
키가 없으면 자동 skip된다 → **"키 미설정으로 미실행"으로 보고하고 점수를 지어내지 않는다.**

### 2. 지표 해석
- **순서 일관성(주지표):** 도메인별 우수>보통>미흡 통과 여부. 깨지면 P1.
- **변별폭(보조):** 우수 평균 − 미흡 평균. 25점 미만이면 변별 약화 경보.
- band(점수대)는 sanity일 뿐, 경계 겹침은 정상.

### 3. 드리프트 추적
매 실행 요약을 `_workspace/eval_history.jsonl`에 한 줄로 누적:
```json
{"date":"2026-06-03","ordering_pass":true,"strong_avg":88.5,"weak_avg":22.0,"gap":66.5}
```
직전 대비 변별폭 감소·순서 실패 전환을 경보한다.

### 4. 골든셋 보강 제안
특정 도메인·토픽에서 변별이 흔들리면 그 question_family를 golden_set.py에 추가 제안
(우수/보통/미흡 3종 + 기대 등급 + 근거). 라벨 타당성은 accuracy-reviewer와 교차 확인.

## 산출물

`_workspace/eval_monitor_<날짜>.md`:
- 도메인별 점수 + 순서 통과 여부
- 변별폭 + 직전 대비 추세
- 드리프트 경보 / 골든셋 추가 제안

## 원칙

- 비결정성: 절대 점수는 흔들린다 → 순위·변별폭으로 판단, 절대 임계값 단정 금지.
- 키 미설정·LLM 오류는 미실행/누락으로 정직하게 보고(추정 금지).
