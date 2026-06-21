# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

AI 에이전트 예제 모음 레포지토리. 각 서브디렉토리가 독립적인 에이전트 프로젝트이며,
프로젝트별 `pyproject.toml`, `.venv`, `uv.lock` 또는 각 프로젝트의 언어/런타임 설정을 갖는다.

## Structure

```
ai-agent-repos/
├── semiconductor-agent/          # LangGraph + Clean Architecture 반도체 면접 학습 에이전트
├── movie-expert-agent/           # OpenAI Agents SDK + Clean Architecture 영화 추천 에이전트
├── movie-agent/
├── movie-recommendation-chatbot/
├── restaurant-bot/
├── storybook-agent/
└── life-coach-agent/
```

각 서브프로젝트는 자체 AGENTS.md를 가지고 있으므로, 해당 프로젝트 작업 시 서브프로젝트의 AGENTS.md를 참고할 것.

## Commands

서브프로젝트 단위로 실행:

```bash
cd <project-dir>
uv sync                        # Python/uv 프로젝트 의존성 설치
uv run pytest tests/ -v        # 테스트 실행 (프로젝트에 따라 다름)
uv run python <entrypoint>.py   # CLI 실행 (프로젝트에 따라 다름)
```

## Key Configuration

- 각 서브프로젝트의 `.env`에 API 키 설정 (루트 `.env`는 공통 설정용)
- Python 버전은 서브프로젝트별 `.python-version` 또는 `pyproject.toml`의 `requires-python`을 따른다.
