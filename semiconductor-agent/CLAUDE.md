# CLAUDE.md — semiconductor-agent

## Project Overview

LangGraph 기반 반도체 취준생 AI 학습 에이전트. 삼성DS/SK하이닉스 기술면접 특화.  
Clean Architecture (4-layer) + TDD (pytest) 로 구현됨.

## 하네스: 반도체 면접 교육 운영

**목표:** 이 교육 제품(문제은행·평가 품질·산업 동향·학습자 진도)을 최신·고품질 상태로 유지한다.

**트리거:** "운영 점검", "주간/일일 운영", "콘텐츠 갱신", "동향 반영", "평가 품질 점검",
"약점 보강", "운영 다시 실행" 등 여러 운영 작업을 묶어 돌릴 때 `semiconductor-ops` 스킬을
사용하라. 단일 작업(예: "골든셋만 돌려줘")은 해당 스킬(monitor-eval-quality 등)을 직접
써도 된다. 단순 질문은 직접 응답 가능.

**실행 모드:** 서브에이전트 (에이전트 팀 플래그 미설정). 모든 Agent 호출은 `model: "opus"`.

**변경 이력:**
| 날짜 | 변경 내용 | 대상 | 사유 |
|------|----------|------|------|
| 2026-06-03 | 초기 구성 (5 에이전트 + 6 스킬, 감독자+생성-검증) | 전체 | 운영 하네스 신규 구축 |
| 2026-06-03 | eval_judge 키 가드를 judge·critic 양 provider로 확장 | scripts/eval_judge.py, llm_service.py | 드라이런 발견: OPENAI만 설정 시 회색지대 런타임 실패 |
| 2026-06-03 | weekly_review 한글 폰트 fallback 추가 | scripts/weekly_review.py | 드라이런 발견: 폰트 경고가 stdout 요약을 묻음 |

## Commands

```bash
uv sync --dev                          # 의존성 + pytest 설치
uv run pytest tests/ -v                # 전체 테스트 실행 (232개, eval 자동 제외)
uv run pytest -m eval tests/eval/ -v   # judge 품질 골든셋 (실제 LLM, OPENAI_API_KEY 필요)
uv run python scripts/eval_judge.py    # judge 품질 리포트 (markdown 표 + PNG 차트)
uv run jupyter notebook main.ipynb     # 데모 노트북 실행
uv run chainlit run chainlit_app.py    # Chainlit 웹 UI
uv run python scripts/daily.py         # 일일 면접 루틴 (영속화·이어가기)
uv run python scripts/weekly_review.py # 주간 누적 진단 + 사용 통계 차트
```

## 본인용 일일 사용

매일 5분 면접 루틴:

```bash
# alias 등록 (zshrc / bashrc)
alias inv="cd ~/Desktop/project/movie-expert-agent/semiconductor-agent && uv run python scripts/daily.py"

# 그 후 매일
inv
```

영속화: `.agent_state.db` (SQLite). 재시작 후에도 thread_id="hans"로 진도 이어감.
사용 로그: `usage.jsonl` (자동). `weekly_review.py`로 주간 회고 차트.

env 변수:
- `THREAD_ID` (기본 "hans") — 사용자 식별자
- `AGENT_DB` (기본 ".agent_state.db") — SQLite 경로
- `USAGE_LOG_PATH` (기본 "usage.jsonl") — 호출 로그 경로
- `DAILY_COMPANY` (기본 "samsung_ds"), `DAILY_MAX_Q` (기본 3) — daily.py 설정

## Architecture (Clean Architecture)

```
semiconductor/
├── domain/              # 레이어 1: 순수 비즈니스 규칙
│   ├── entities.py      #   Question, EvaluationResult, DiagnosticResult
│   └── ports.py         #   IQuestionRepository, ILLMJudge, ILLMCritic, ICoachLLM, IDiagnosticLLM
│
├── application/         # 레이어 2: 유스케이스 (포트에만 의존)
│   └── use_cases/
│       ├── evaluate_answer.py        # judge 1차 평가
│       ├── critique_evaluation.py    # critic 2차 검증
│       ├── next_question.py          # 질문 풀에서 출제
│       ├── coach_concept.py          # 소크라테스 코칭
│       └── diagnose_session.py       # 도메인별 진단
│
├── infrastructure/      # 레이어 3: 포트 구현체 + 외부 도구
│   ├── llm/
│   │   └── llm_service.py            # OpenAI{Judge|Critic|Coach|Diagnostic}LLM
│   ├── tools/                        # 외부 capability
│   │   ├── calculator.py             # SemiconductorCalculator (Vth, Id, Cox)
│   │   └── web_search.py             # IndustrySearchService (DuckDuckGo + today inject)
│   └── question_bank/
│       ├── _samsung_ds.py
│       └── _sk_hynix.py
│
└── adapters/            # 레이어 4: LangGraph 어댑터
    ├── state.py                      # InterviewState TypedDict
    ├── graph.py                      # create_app(), create_app_with_memory()
    ├── tools.py                      # @tool wrappers + COACH_TOOLS list
    └── nodes/
        ├── orchestrator.py           # 명령어 파싱 + phase-aware 라우팅
        ├── mock_interviewer.py       # 3-node split: present / evaluate / critic
        ├── web_enrichment.py         # 트렌드 도메인 병렬 검색 (Send API)
        ├── qa_coach.py               # ReAct tool-calling + ToolNode
        └── diagnostic.py             # 도메인 점수 + matplotlib 차트
```

## Graph Topology

```
START → orchestrator
          ├──▶ mock_present  ──▶ END                            (질문 출제 turn)
          ├──▶ eval_dispatch ─┬─▶ mock_evaluate ─┐
          │  (Send API fanout) └─▶ web_enrichment ┼──▶ mock_critic ──▶ END
          │                                       (트렌드만, 병렬 + 자동 join)
          ├──▶ qa_coach ─tool_calls?─▶ coach_tools ──▶ qa_coach (ReAct loop)
          │              └─no──▶ END
          ├──▶ diagnostic    ──▶ END
          └──▶ END (idle)
```

**평가 파이프라인 ("교수 초과")**: Specialty Judge → (선택적 ∥ web_search) → Critic → 출력 6개 섹션
**ReAct 도구 7개** (qa_coach가 LLM-driven 호출):
- `industry_trend_search` (DuckDuckGo, today 날짜 자동 주입)
- `calculate_threshold_voltage` / `calculate_drain_current` / `calculate_oxide_capacitance` (반도체 수식 계산)
- `analyze_circuit_diagram` / `analyze_band_diagram` / `analyze_engineering_image` (Gemini 멀티모달)
  - `LLM_MODEL_VISION` env (기본 `google_genai:gemini-2.5-pro`)
  - 회로도, 밴드 다이어그램, SEM/레이아웃 이미지 입력 → 텍스트 분석
**Memory**: `create_app_with_memory()` → MemorySaver. `config={"configurable":{"thread_id":"user_xxx"}}` 로 invoke 시 자동 영속화
**Parallel Send**: 트렌드 도메인 평가 시 judge LLM과 DuckDuckGo 검색이 동시 실행 (today 날짜 자동 주입으로 stale article 방지)

## Key Configuration

- `.env`에 `OPENAI_API_KEY` 필수
- `AI_BASE_URL` 설정 시 커스텀 엔드포인트 사용
- Multi-provider routing (`init_chat_model` 기반):
  - `LLM_TIER` env var (premium / standard / budget) → 역할별 model mapping
  - **premium**: `openai:gpt-4o` (Judge) + `anthropic:claude-sonnet-4-6` (Critic·Coach·Essay·Behavioral) + `openai:gpt-4o-mini` (Diagnostic)
  - **standard**: `openai:gpt-4o-mini` + `anthropic:claude-haiku-4-5` (Pro 진입 가성비, 비용 1/5)
  - **budget**: `openai:gpt-4o-mini` 단일 모델 통일 (Free 사용자, 비용 1/10)
  - 명시 env var (`LLM_MODEL_{ROLE}`)이 tier보다 우선
  - provider prefix 없으면 `openai:` 자동 보완 (예: `gpt-5` → `openai:gpt-5`)
  - `AI_BASE_URL`은 OpenAI provider일 때만 적용
  - 필요한 API 키: `OPENAI_API_KEY` + `ANTHROPIC_API_KEY` + `GOOGLE_API_KEY` (vision 사용 시)
- Adaptive critic skip — 평가 비용 절감
  - mock_critic은 1차 평가 점수가 회색지대(31~84)일 때만 호출
  - 확신 영역(>=85 우수, <=30 미흡)은 LLM critic 생략 → 평균 -50% 비용
  - `CRITIC_SKIP_HIGH` / `CRITIC_SKIP_LOW` env로 임계값 조정 가능
  - `LLM_DISABLE_CRITIC_SKIP=1` 설정 시 강제 호출 (디버깅용)
- LLM judge 루브릭: 정확성 40 + 깊이 30 + 전문용어 30 = 100점

## 평가 파이프라인 ("교수 초과" 메커니즘)

```
질문 + 답변
   ↓
[Specialty Judge]  ← 도메인별 전문가 페르소나 (소자/공정/회로/트렌드)
   ↓ initial_evaluation
[Critic]           ← Self-Critique: 평가의 평가, 과대/과소 식별
   ↓ final_evaluation
출력:
  - 점수 (40/30/30 = 100)
  - feedback
  - strong_points / weak_points
  - 🔬 specialist_commentary  (도메인 전문가 코멘트)
  - 📚 model_answer           (만점 모범답안, LaTeX 수식 포함 가능)
  - 💡 follow_up_question     (약점 파고드는 후속 질문)
```

도메인 페르소나:
- **소자**: 삼성종합기술원 출신 MOSFET/FinFET/GAA 박사 — 1차 원리 중시
- **공정**: SK하이닉스 청주 fab CVD/ALD 박사 — step coverage, conformality 중시
- **회로**: 메모리 컨트롤러 회로 설계자 — 센스앰프/차지펌프 마진 중시
- **트렌드**: TSMC/Samsung Foundry 산업 분석가 — EUV/HBM/GAA 로드맵 중시

## User Commands

| 입력 | 동작 |
|------|------|
| `/인터뷰` | 모의 기술면접 (4도메인 × 5문제, judge → critic 2-pass) |
| `/qa [주제]` | 소크라테스 코칭 + ReAct tool (검색·계산기) |
| `/자소서 [회사] [항목]` | 자소서 첨삭 (4축 rubric, 회사 인재상 매칭) |
| `/인성 [회사]` | 인성면접 STAR 평가 (5축 rubric) |
| `/적성 [GSAT\|SKCT]` | 적성검사 객관식 (수리/추리/언어/공간) — LLM 미사용, 정적 채점 |
| `/진단` | 도메인별 이해도 진단 + matplotlib 차트 |
| `quit` | 세션 종료 |

회사: `samsung_ds` / `sk_hynix`. 자소서 항목: `지원동기` / `직무역량` / `성장과정` / `갈등극복`.
