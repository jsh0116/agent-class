---
name: curate-question-bank
description: 반도체 면접 문제은행(question_bank/_samsung_ds.py, _sk_hynix.py)을 큐레이션한다. 신규 토픽 질문 추가, 도메인·난이도 커버리지 점검, 중복 제거를 수행. "문제 추가", "문제은행 점검", "질문 보강", "커버리지 확인" 요청 시 사용. 문제은행 운영 작업이면 반드시 이 스킬을 쓴다.
---

# 문제은행 큐레이션

question-bank-curator 에이전트가 반도체 면접 질문 풀을 유지보수하는 절차.

## 대상 파일

- `semiconductor/infrastructure/question_bank/_samsung_ds.py` — 삼성DS(공정·소자 심화)
- `semiconductor/infrastructure/question_bank/_sk_hynix.py` — SK하이닉스(HBM·메모리·패키징)
- 형식: `QUESTIONS: dict[str, list[Question]]`, 키는 도메인(`소자`/`공정`/`회로`/`트렌드`)
- 엔티티: `Question(domain=, question=, key_points=[...])` — domain은 `VALID_DOMAINS` 강제

## 워크플로우

### 1. 현황 파악
대상 회사 파일을 읽고 도메인별 질문 수·토픽을 집계한다. 빈/얇은 도메인을 찾는다.

### 2. 신규 질문 설계
- 실제 기술면접에서 "원리를 설명하고 왜 그런지 파고드는" 질문으로 만든다.
- key_points는 채점 루브릭(정확성 40 / 깊이 30 / 전문용어 30)의 기준 — 핵심 개념·원리·정량
  포인트를 3개 내외로.
- 회사 특성 반영: samsung_ds=공정/소자, sk_hynix=HBM/메모리/패키징.

좋은 예 (소자):
```python
Question(
    domain="소자",
    question="GAA(MBCFET)가 FinFET 대비 단채널 효과 억제에 유리한 이유를 "
             "정전 제어 관점에서 설명하세요.",
    key_points=[
        "게이트가 채널을 4면 전체로 감싸 정전 제어 우위",
        "유효 채널 폭/구동전류를 나노시트 적층으로 확보",
        "SCE·DIBL 억제 → 더 낮은 노드로 스케일링",
    ],
)
```

### 3. 중복 검사
추가 전 기존 질문과 의미 중복 확인(같은 개념 다른 표현 금지).

### 4. 검수 게이트 (필수)
신규 질문은 먼저 `_workspace/qbank_curator_<작업>.md`에 **제안**으로 쓴다.
accuracy-reviewer 검수를 통과한 뒤에만 `_*.py`에 Edit한다. **검수 전 코드 반영 금지.**

### 5. 반영 후 검증
코드 Edit 후 회귀 확인:
```bash
uv run pytest tests/infrastructure/test_question_bank.py -q
```

## 산출물

`_workspace/qbank_curator_<작업>.md`:
- 제안 질문(도메인·질문·key_points·근거)
- 커버리지 진단(도메인별 수, 빈 영역)
- 검수/반영 상태

## 원칙

- 도메인이 모호하면 임의 배정하지 말고 두 후보 병기 → 검수자 판단.
- 파일 구조가 예상과 다르면 덮어쓰지 말고 보고 후 확인 요청.
