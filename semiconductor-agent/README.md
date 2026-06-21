# 반도체 면접 준비 AI 에이전트

삼성DS · SK하이닉스 기술면접부터 자소서·인성·적성검사까지 커버하는 LangGraph 기반 멀티 에이전트.
"교수 수준 초과"를 목표로 도메인 전문가 페르소나 + Self-Critique + 멀티모달 비전 + ReAct 도구 결합.

> **본인 도구로 시작 → 상용화 옵션 보존** 경로. 매일 사용 인프라(영속화·일일 루틴·사용 로그) 갖춰져 있음.

---

## 주요 기능

| 명령어 | 모듈 | 설명 |
|--------|-----|------|
| `/인터뷰` | 기술면접 | 회사·도메인별 질문 + Specialty Judge → Self-Critique 2-pass 평가 |
| `/qa [주제]` | 개념 코치 | 소크라테스 방식 + ReAct 도구(검색·계산기·비전) |
| `/자소서 [회사] [항목]` | 자소서 첨삭 | 회사 인재상 매칭 4축 평가 (부합도 30 / 구조 25 / 구체성 25 / 작문 20) |
| `/인성 [회사]` | 인성면접 | STAR 5축 평가 (Situation 20 / Task 20 / Action 30 / Result 20 / 인재상 10) |
| `/적성 [GSAT\|SKCT]` | 적성검사 | 객관식 (수리·추리·언어·공간) — **LLM 미사용, 운영비 0원** |
| `/진단` | 이해도 진단 | 도메인별 점수 + matplotlib 차트 |

### "교수 수준 초과" 메커니즘

1. **도메인 전문가 페르소나** — 4도메인별 박사급 평가관 (삼성종기원 출신 소자 박사 / SK하이닉스 청주 fab 공정 박사 등)
2. **Self-Critique 2-pass** — 평가의 평가, 회색지대(31~84점)만 critic 호출 (확신 영역 skip = 비용 50%↓)
3. **모범답안 + LaTeX 수식** — 만점 기준 답변 + Vth·Id 수식 정확 표기
4. **Follow-up 질문** — 약점 파고드는 후속 질문 자동 생성
5. **산업 동향 검색** — DuckDuckGo + today 날짜 자동 주입 (LLM cutoff 보완)
6. **멀티모달 비전** — Gemini 2.5 Flash로 회로도·밴드 다이어그램·SEM 이미지 분석

---

## 빠른 시작

### 1. 의존성 설치

```bash
cd semiconductor-agent
uv sync --dev
```

### 2. 환경 변수

```bash
# 필수
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...

# 선택 (vision 사용 시)
export GOOGLE_API_KEY=...

# 선택 (tier 변경)
export LLM_TIER=premium   # premium / standard / budget (기본 premium)
```

### 3. 실행 (원하는 인터페이스 선택)

```bash
# Jupyter 노트북 (LaTeX 수식·차트 인라인)
uv run jupyter notebook main.ipynb

# Chainlit 웹 UI
uv run chainlit run chainlit_app.py

# 일일 면접 루틴 (영속화·이어가기) ← 추천
uv run python scripts/daily.py

# 주간 회고 (도메인별 추이 + 비용 통계)
uv run python scripts/weekly_review.py
```

---

## 본인용 일일 사용

매일 5분 면접 루틴이 핵심. 진도는 SQLite로 자동 저장 → 어제 끊어진 지점부터 자동 재개.

```bash
# alias 등록 (~/.zshrc 또는 ~/.bashrc)
alias inv="cd ~/Desktop/project/movie-expert-agent/semiconductor-agent && uv run python scripts/daily.py"
```

```bash
# 매일 한 줄
inv
```

세션 예시:

```
🎯 [일일 면접 루틴] 시작
📚 이전 진도 발견: 누적 8개 평가. 이어서 진행.

📝 [공정] 문제 9/3

CVD와 ALD의 메커니즘 차이를 설명하고, ALD가 고종횡비 구조에 유리한 이유를 말씀해 주세요.

>>> CVD는 가스가 동시에 반응하고, ALD는 전구체를 순서대로 흘려 한 층씩 쌓습니다.

🎓 [공정 전문가 평가] 📊 평가 결과 [보통] 58/100점

  정확성 28/40 | 깊이 16/30 | 전문용어 14/30

💬 self-limiting 반응 메커니즘과 컨포말성 우위에 대한 설명이 더 필요합니다.
✅ 잘한 점: ALD의 순차적 증착 방식
📌 보완점:  자기제한 반응 원리, 고종횡비 균일성

🔬 전문가 코멘트:
공정 전문가 관점에서 ALD의 self-limiting은 surface saturation에서 비롯되며,
이로 인해 sub-monolayer 정확도와 100% conformality가 가능합니다.

📚 모범답안:
CVD는 두 전구체가 동시 공급돼 gas-phase 반응이 일어나는 반면, ALD는 전구체 A → 퍼지 →
전구체 B → 퍼지 식의 self-limiting 반응으로 atomic-layer 정밀도를 보장합니다.
고종횡비(>50:1) trench/via에서 sticking probability가 낮은 ALD precursor가 표면 흡착으로
saturation에 도달하므로, 측벽까지 균일한 두께를 얻을 수 있습니다.

💡 심화 질문 (선택): 그럼 ALD throughput을 올리기 위한 spatial ALD 방식은 어떻게 동작하나요?
```

매주 토요일 회고:

```bash
uv run python scripts/weekly_review.py
# → weekly_report_YYYYMMDD.png + 콘솔 요약
```

---

## 아키텍처

Clean Architecture 4-layer + LangGraph StateGraph + Multi-provider LLM routing.

```
semiconductor/
├── domain/              # Layer 1: 순수 비즈니스 규칙
│   ├── entities.py          # 8 entity (Question/EvaluationResult/Essay/Behavioral/Aptitude...)
│   └── ports.py             # ILLMJudge / ICritic / ICoach / IEssayCoach / IBehavioralCoach...
│
├── application/         # Layer 2: 유스케이스
│   └── use_cases/           # 6 use case (evaluate / critique / next_question / coach / essay / behavioral)
│
├── infrastructure/      # Layer 3: 포트 구현체 + 외부 도구
│   ├── llm/                 # init_chat_model 기반 multi-provider + tier 시스템 + safety
│   ├── essay/               # Claude Essay Coach + 8개 prompt
│   ├── behavioral/          # Claude Behavioral Coach + 6개 STAR 질문
│   ├── aptitude/            # 정적 GSAT/SKCT 10문제 (LLM 미사용)
│   ├── tools/               # DuckDuckGo + 반도체 계산기 + Gemini Vision
│   ├── question_bank/       # 삼성DS / SK하이닉스 기술면접 질문
│   └── observability/       # usage_log (JSON Lines)
│
└── adapters/            # Layer 4: LangGraph 어댑터
    ├── state.py
    ├── graph.py             # create_app(), create_app_with_memory(), create_app_with_sqlite()
    ├── tools.py             # 7개 @tool wrapper (검색·계산기·비전)
    └── nodes/
        ├── orchestrator.py
        ├── mock_interviewer/    # 4-file split (present / evaluate / critic / serialization)
        ├── essay_coach.py
        ├── behavioral_coach.py
        ├── aptitude_test.py
        ├── qa_coach.py          # ReAct loop with 7 tools, recursion guard
        ├── web_enrichment.py    # Send API 병렬 실행
        └── diagnostic.py
```

### 그래프 토폴로지

```
START → orchestrator
          ├──▶ mock_present  ──▶ END                                     (질문 출제 turn)
          ├──▶ eval_dispatch ─┬──▶ mock_evaluate ─┐
          │                   └──▶ web_enrichment ┴──▶ mock_critic ──▶ END  (답변 평가 + 트렌드 병렬)
          ├──▶ qa_coach ──tool_calls?──▶ coach_tools ──▶ qa_coach (ReAct loop)
          │                  └──no──▶ END
          ├──▶ essay_present / essay_evaluate ──▶ END
          ├──▶ behavioral_present / behavioral_evaluate ──▶ END
          ├──▶ aptitude_present / aptitude_evaluate ──▶ END
          ├──▶ diagnostic ──▶ END
          └──▶ END (idle)
```

---

## Multi-provider LLM Routing

`init_chat_model` 기반. 작업 성격에 따라 다른 provider 사용. env로 자유 교체.

| 역할 | 기본 (premium) | 이유 |
|------|--------------|------|
| Judge | `openai:gpt-4o` | structured output 6필드 안정성 |
| Critic | `anthropic:claude-sonnet-4-6` | 비판적 사고 + 한국어 자연스러움 |
| Coach | `anthropic:claude-sonnet-4-6` | 한국어 + ReAct tool use |
| Diagnostic | `openai:gpt-4o-mini` | analytical, mini로 충분 |
| Essay | `anthropic:claude-sonnet-4-6` | 한국어 작문 강점 |
| Behavioral | `anthropic:claude-sonnet-4-6` | STAR 한국어 평가 일관성 |
| Vision | `google_genai:gemini-2.5-flash` | 회로도·밴드·멀티모달 분석 (저비용) |

### Tier 시스템 (비용 최적화)

```bash
LLM_TIER=premium   # gpt-4o + claude-sonnet (기본)
LLM_TIER=standard  # gpt-4o-mini + claude-haiku (Pro 진입 가성비, 비용 1/5)
LLM_TIER=budget    # gpt-4o-mini × 4 통일 (Free, 비용 1/10)
```

명시 env (`LLM_MODEL_JUDGE`, `LLM_MODEL_COACH` 등)이 tier보다 우선.

### Adaptive Critic Skip (비용 50%↓)

1차 평가 점수가 회색지대(31~84)일 때만 critic LLM 호출. 확신 영역(>=85 우수, <=30 미흡) skip.
`CRITIC_SKIP_HIGH` / `CRITIC_SKIP_LOW` env로 임계값 조정.

---

## 영속화 + 사용 추적

| 인프라 | 본인 사용 | 상용 전환 시 |
|--------|---------|-------------|
| `thread_id="hans"` (env) | 본인 1명 | `user.id`로 한 줄 변경 |
| `.agent_state.db` (SqliteSaver) | 매일 진도 자동 저장 | PostgresSaver로 swap |
| `usage.jsonl` | 본인 비용 추적 | per-user usage tracking |

```bash
# env 조정
export THREAD_ID=hans
export AGENT_DB=.agent_state.db
export USAGE_LOG_PATH=usage.jsonl
```

`weekly_review.py`가 도메인별 점수 추이 + 7일 호출·모델·비용 통계 차트 자동 생성.

---

## 보안 (상용화 안전성)

- **Prompt injection 가드**: 사용자 답변을 `<user_answer>` 태그로 격리, 11개 알려진 패턴 sanitize, system prompt에 주의 지시
- **Vision file 검증**: path traversal (`../`, symlink) 차단, 파일 크기 상한, magic byte 검증
- **ReAct loop 가드**: tool 호출 5회 도달 시 강제 종료
- **API 키**: env 변수만 사용, 코드·git에 하드코딩 없음

---

## 테스트

```bash
uv run pytest tests/ -v
# 232 passed
```

도메인·application·infrastructure·adapter 4 layer 모두 단위 테스트 커버.
LLM은 mock으로 격리, 외부 API 키 없이도 실행 가능.

테스트 분포:
- 도메인 entities: 28
- Application use cases: 17
- Infrastructure (LLM service / safety / tools / question pool / vision / usage_log): 70+
- Adapter nodes (orchestrator / mock_interviewer / essay / behavioral / aptitude / qa_coach / memory / parallel): 110+

---

## 기술 스택

| 분류 | 라이브러리 |
|------|-----------|
| 에이전트 오케스트레이션 | LangGraph (StateGraph + Send API + checkpointer) |
| LLM | `langchain.chat_models.init_chat_model` (OpenAI + Anthropic + Google) |
| 도구 | langchain-community (DuckDuckGo) + 자체 반도체 계산기 + Gemini Vision |
| 시각화 | matplotlib |
| 영속화 | langgraph-checkpoint-sqlite |
| 테스트 | pytest |
| 패키지 관리 | uv |

---

## 요구사항

- Python 3.13+
- OpenAI API 키 (필수)
- Anthropic API 키 (필수, Critic·Coach·Essay·Behavioral)
- Google API 키 (선택, Vision tool 사용 시)
- uv

---

## 라이선스 / 사용

본인 학습용으로 시작한 프로젝트. 상용화 옵션은 보존됐지만 현재는 **자체 dogfooding** 단계.

문제·제안: GitHub Issues
