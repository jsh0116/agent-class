"""Chainlit UI for the semiconductor interview agent."""
import chainlit as cl
from langchain_core.messages import HumanMessage

from semiconductor.adapters.graph import create_app


@cl.set_chat_profiles
async def chat_profile():
    return [
        cl.ChatProfile(
            name="삼성DS",
            markdown_description="**삼성전자 DS부문** — 공정·소자·회로·트렌드 심화 (FinFET/GAA, EUV, CVD/ALD)",
        ),
        cl.ChatProfile(
            name="SK하이닉스",
            markdown_description="**SK하이닉스** — HBM·메모리·패키징 특화 (TSV, 하이브리드 본딩, LPDDR5, CXL)",
        ),
    ]


@cl.on_chat_start
async def start():
    profile = cl.user_session.get("chat_profile")
    company = "samsung_ds" if profile == "삼성DS" else "sk_hynix"

    app, state = create_app(company=company, max_questions=5)
    cl.user_session.set("app", app)
    cl.user_session.set("state", state)

    await cl.Message(content=state["display_output"]).send()


@cl.on_message
async def on_message(message: cl.Message):
    app = cl.user_session.get("app")
    state = cl.user_session.get("state")

    # 누적: 이전 턴 대화(질문·평가·코칭 맥락)를 보존하고 새 입력만 추가한다.
    # 덮어쓰면 멀티턴 QA 코칭이 직전 맥락을 잃는다. orchestrator는 마지막
    # HumanMessage에서 명령을 읽으므로 누적해도 라우팅은 안전하다.
    state["messages"] = list(state.get("messages") or []) + [
        HumanMessage(content=message.content)
    ]
    state = app.invoke(state)
    cl.user_session.set("state", state)

    output = state.get("display_output", "")
    chart_png: bytes | None = state.get("chart_png")

    if chart_png:
        await cl.Message(
            content=output,
            elements=[cl.Image(content=chart_png, name="이해도 진단 차트", display="inline")],
        ).send()
    elif output:
        await cl.Message(content=output).send()
