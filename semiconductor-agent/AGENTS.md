# AGENTS.md — semiconductor-agent

코딩 에이전트가 이 레포에서 작업할 때의 운영 지침. LangGraph 기반 반도체 취준 AI 학습
에이전트(삼성DS·SK하이닉스 기술면접 특화), Clean Architecture 4계층 + TDD(pytest)로 구현됨.

> 도메인·그래프 토폴로지·평가 파이프라인의 상세 설명은 `README.md`와 `CLAUDE.md` 참조.
> 이 문서는 **무엇을 어떻게 변경하는가**(명령어·계층 규칙·관례·금지사항)에 집중한다.

## 셋업 & 명령어

```bash
uv sync --dev                          # 의존성 + pytest (Python 3.13+ 필요)
uv run pytest tests/ -v                # 전체 테스트 (현재 232 passed)
uv run pytest tests/adapters/test_orchestrator.py -v   # 단일 파일
uv run python scripts/daily.py         # 일일 면접 루틴 (영속화·이어가기)
uv run chainlit run chainlit_app.py    # 웹 UI
```

- 패키지 매니저는 **uv** 고정. `pip` 직접 호출 금지.
- 코드 변경 후에는 **반드시 `uv run pytest tests/ -v`로 그린 확인** 후 마무리한다.

## 아키텍처 — 계층 의존 규칙 (가장 중요)

```
adapters ───────▶ application ───────▶ domain
   │                                      ▲
   └──────────▶ infrastructure ──────────┘

domain: 순수 비즈니스 규칙
application: 유스케이스, domain 포트에만 의존
infrastructure: domain 포트 구현체·외부 도구
adapters: LangGraph 조립 계층, use case와 구현체를 DI로 연결
```

```
semiconductor/
├── domain/          # Layer 1: entities.py, ports.py — 순수 비즈니스 규칙
├── application/     # Layer 2: use_cases/ — 포트(인터페이스)에만 의존
├── infrastructure/  # Layer 3: 포트 구현체 (llm/ tools/ question_bank/ essay/ behavioral/ aptitude/ observability/)
└── adapters/        # Layer 4: LangGraph (state.py graph.py tools.py nodes/)
```

**불변 규칙 (위반 시 아키텍처 깨짐):**
- `domain/`·`application/`은 **langchain·langgraph·외부 SDK를 import하지 않는다.** 프레임워크
  의존은 `adapters/`·`infrastructure/`에만 존재한다.
- `application/`의 유스케이스는 구체 클래스가 아니라 `domain/ports.py`의 **인터페이스(I...)에만**
  의존한다. 의존성 주입으로 구현체를 받는다.
- 의존 방향은 항상 안쪽(domain)을 향한다. `adapters/`는 바깥 조립 계층으로서
  `application/` 유스케이스와 `infrastructure/` 구현체를 연결할 수 있지만,
  `domain/`·`application/`이 `adapters/`·`infrastructure/`를 import하는 것은 금지한다.

## 새 기능 추가 워크플로우 (계층 횡단)

기능 하나가 보통 4계층을 모두 건드린다. **순서대로, TDD로** 진행한다:

1. **domain** — `entities.py`에 데이터 구조(Pydantic/dataclass) 추가, `ports.py`에 인터페이스
   (`I...`, `@abstractmethod`) 추가. 먼저 `tests/domain/`에 테스트 작성.
2. **application** — `use_cases/`에 유스케이스 추가 (포트만 받음). `tests/application/` 테스트.
3. **infrastructure** — 포트 구현체 추가 (LLM 서비스·도구·질문은행 등). `tests/infrastructure/` 테스트.
   LLM은 **mock으로 격리**해 외부 키 없이 테스트 가능해야 한다.
4. **adapters** — LangGraph 노드(`nodes/`) 추가, `graph.py`에 노드·엣지 배선, 필요시 `state.py`
   확장, `tools.py`에 `@tool` 래퍼. `tests/adapters/`에 노드·그래프 통합 테스트.

테스트 디렉토리는 소스 계층을 미러링한다 (`tests/{domain,application,infrastructure,adapters}/`).

## LLM 라우팅 & 환경변수

- 모델은 `init_chat_model` 기반 multi-provider. 역할별로 다른 provider 사용. **하드코딩 금지** —
  `infrastructure/llm/`의 tier/매핑을 통한다.
- `LLM_TIER` (premium/standard/budget) → 역할별 모델 매핑. 명시 env(`LLM_MODEL_{ROLE}`)가 tier보다 우선.
- 필수 키: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`. 선택: `GOOGLE_API_KEY`(vision).
- **API 키는 env에서만 읽는다. 코드·git에 하드코딩하지 않는다.**
- 영속화/식별: `THREAD_ID`, `AGENT_DB`, `USAGE_LOG_PATH`, daily는 `DAILY_COMPANY`/`DAILY_MAX_Q`.

## 보안 불변식 (상용화 안전성 — 유지할 것)

- **Prompt injection 가드:** 사용자 답변은 `<user_answer>` 태그로 격리, 알려진 패턴 sanitize.
  새 LLM 입력 경로를 추가하면 동일 가드를 적용한다 (`infrastructure/llm/safety.py` 참조).
- **Vision 파일 검증:** path traversal·symlink 차단, 크기 상한, magic byte 검증.
- **ReAct loop 가드:** qa_coach의 tool 호출은 상한에서 강제 종료한다.
- **비용:** Adaptive critic skip(회색지대만 critic 호출) 등 비용 최적화를 임의로 제거하지 않는다.

## 코드 관례

- 주석·문서·도메인 용어는 **한국어**(기존 코드 톤 유지). 반도체 전문용어는 정확히.
- 포트는 `I` 접두사 + `ABC`/`@abstractmethod`. 엔티티는 불변 데이터 중심.
- 기존 파일의 네이밍·구조·import 스타일을 따른다. 새 패턴을 임의 도입하지 않는다.

## 커밋 관례

Conventional Commits(한국어 본문) 사용:
```
feat(semiconductor): <요약>
refactor(semiconductor): <요약>
docs(semiconductor): <요약>
```
커밋·푸시는 **사용자가 요청할 때만** 한다. 변경 후 pytest 그린을 확인하고 보고한다.

## 하지 말 것

- domain/application에서 langchain/langgraph import
- 유스케이스에서 구체 구현체 직접 import (포트 우회)
- LLM 모델명·API 키 하드코딩
- 테스트 없이 기능 추가 (TDD 위반)
- 보안 가드(injection·vision·loop) 우회·삭제
- pip 직접 호출 (uv 사용)
