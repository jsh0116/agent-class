"""TDD: qa_coach ReAct loop — LLM이 tool_calls 발행 시 ToolNode로 라우팅."""
from unittest.mock import MagicMock, patch

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from semiconductor.adapters.nodes.qa_coach import (
    _recent_window,
    qa_coach_node,
    route_after_coach,
)
from semiconductor.adapters.state import create_initial_state


class TestRouteAfterCoach:
    def test_AIMessage에_tool_calls_있으면_coach_tools로(self):
        s = dict(create_initial_state())
        s["messages"] = [
            HumanMessage(content="HBM3E 동향?"),
            AIMessage(content="", tool_calls=[
                {"id": "call_1", "name": "industry_trend_search", "args": {"query": "HBM3E"}}
            ]),
        ]
        assert route_after_coach(s) == "coach_tools"

    def test_AIMessage에_tool_calls_없으면_END(self):
        from langgraph.graph import END
        s = dict(create_initial_state())
        s["messages"] = [
            HumanMessage(content="hello"),
            AIMessage(content="answer"),
        ]
        assert route_after_coach(s) == END

    def test_messages_없으면_END(self):
        from langgraph.graph import END
        s = dict(create_initial_state())
        s["messages"] = []
        assert route_after_coach(s) == END


class TestQaCoachNode:
    def test_topic_없으면_안내_메시지(self):
        s = dict(create_initial_state())
        s["current_qa_topic"] = ""
        result = qa_coach_node(s)
        assert "주제를 알려주세요" in result["display_output"]

    @patch("semiconductor.adapters.nodes.qa_coach.init_chat_model")
    def test_LLM이_tool_calls_없는_응답_반환_시_hint_count_증가(self, mock_init):
        # 일반 응답 → END 경로, hint_count 증가
        ai_msg = AIMessage(content="ALD에 대해 어디까지 아세요?", tool_calls=[])
        bound = MagicMock()
        bound.invoke.return_value = ai_msg
        chat = MagicMock()
        chat.bind_tools.return_value = bound
        mock_init.return_value = chat

        s = dict(create_initial_state())
        s["current_qa_topic"] = "ALD"
        s["hint_count"] = 0
        s["messages"] = [HumanMessage(content="ALD가 뭔가요?")]

        result = qa_coach_node(s)

        assert result["hint_count"] == 1  # 0 → 1
        assert result["display_output"] == "ALD에 대해 어디까지 아세요?"
        assert result["messages"][0] == ai_msg

    @patch("semiconductor.adapters.nodes.qa_coach.init_chat_model")
    def test_LLM이_tool_calls_반환시_hint_count_증가_안함_display도_안함(self, mock_init):
        # tool_calls 응답 → 루프 (아직 최종 답변 아님). hint_count 보존.
        ai_msg = AIMessage(content="", tool_calls=[
            {"id": "call_1", "name": "industry_trend_search", "args": {"query": "HBM"}}
        ])
        bound = MagicMock()
        bound.invoke.return_value = ai_msg
        chat = MagicMock()
        chat.bind_tools.return_value = bound
        mock_init.return_value = chat

        s = dict(create_initial_state())
        s["current_qa_topic"] = "HBM"
        s["hint_count"] = 1
        s["messages"] = [HumanMessage(content="요즘 HBM3E 어떻게 됐어?")]

        result = qa_coach_node(s)

        assert "hint_count" not in result  # 보존
        assert "display_output" not in result  # 아직 출력 안 함
        assert result["messages"][0] == ai_msg

    @patch("semiconductor.adapters.nodes.qa_coach.init_chat_model")
    def test_qa_coach는_Anthropic_Claude_Sonnet_provider_spec으로_호출(self, mock_init):
        # 권장 매핑 확인 — coach는 Claude
        ai_msg = AIMessage(content="x", tool_calls=[])
        bound = MagicMock()
        bound.invoke.return_value = ai_msg
        chat = MagicMock()
        chat.bind_tools.return_value = bound
        mock_init.return_value = chat

        s = dict(create_initial_state())
        s["current_qa_topic"] = "FinFET"
        s["messages"] = [HumanMessage(content="설명해줘")]
        qa_coach_node(s)

        spec = mock_init.call_args.args[0]
        assert spec == "anthropic:claude-sonnet-4-6"

    @patch("semiconductor.adapters.nodes.qa_coach.init_chat_model")
    def test_tool_call_counter_증가_tool_calls_있을때(self, mock_init):
        # tool_calls 응답 → coach_tool_calls 증가 (무한 루프 방지)
        ai_msg = AIMessage(content="", tool_calls=[
            {"id": "c1", "name": "industry_trend_search", "args": {"query": "x"}}
        ])
        bound = MagicMock()
        bound.invoke.return_value = ai_msg
        chat = MagicMock()
        chat.bind_tools.return_value = bound
        mock_init.return_value = chat

        s = dict(create_initial_state())
        s["current_qa_topic"] = "ALD"
        s["coach_tool_calls"] = 2
        s["messages"] = [HumanMessage(content="x")]

        result = qa_coach_node(s)

        assert result["coach_tool_calls"] == 3

    @patch("semiconductor.adapters.nodes.qa_coach.init_chat_model")
    def test_tool_call_counter_리셋_최종답변시(self, mock_init):
        # 일반 응답 → counter 0으로 리셋
        ai_msg = AIMessage(content="answer", tool_calls=[])
        bound = MagicMock()
        bound.invoke.return_value = ai_msg
        chat = MagicMock()
        chat.bind_tools.return_value = bound
        mock_init.return_value = chat

        s = dict(create_initial_state())
        s["current_qa_topic"] = "ALD"
        s["coach_tool_calls"] = 3
        s["messages"] = [HumanMessage(content="x")]

        result = qa_coach_node(s)

        assert result["coach_tool_calls"] == 0

    @patch("semiconductor.adapters.nodes.qa_coach.init_chat_model")
    def test_invoke에_provider중립_BaseMessage만_전달한다(self, mock_init):
        # 2차 호출(도구 실행 후) transcript가 OpenAI dict로 내려 변환되면
        # Anthropic coach가 못 파싱한다. BaseMessage 원형 그대로 전달되어야 한다.
        ai_final = AIMessage(content="정리된 답변", tool_calls=[])
        bound = MagicMock()
        bound.invoke.return_value = ai_final
        chat = MagicMock()
        chat.bind_tools.return_value = bound
        mock_init.return_value = chat

        ai_tc = AIMessage(content="", tool_calls=[
            {"id": "c1", "name": "industry_trend_search", "args": {"query": "HBM"}}
        ])
        tool_msg = ToolMessage(content="검색 결과 텍스트", tool_call_id="c1")
        s = dict(create_initial_state())
        s["current_qa_topic"] = "HBM"
        s["coach_tool_calls"] = 1
        s["messages"] = [HumanMessage(content="요즘 HBM?"), ai_tc, tool_msg]

        qa_coach_node(s)

        passed = bound.invoke.call_args.args[0]
        # 전부 BaseMessage (dict로 내려 변환 안 함)
        assert all(isinstance(m, BaseMessage) for m in passed)
        # system은 SystemMessage이고 맨 앞
        assert isinstance(passed[0], SystemMessage)
        # tool_call AIMessage와 ToolMessage가 재구성/문자열화 없이 원형 그대로 전달
        assert ai_tc in passed
        assert tool_msg in passed

    @patch("semiconductor.adapters.nodes.qa_coach.init_chat_model")
    def test_tool_call_상한_도달시_강제_종료(self, mock_init):
        # 5회 도달하면 LLM 호출 없이 안내 메시지 반환
        chat = MagicMock()
        bound = MagicMock()
        chat.bind_tools.return_value = bound
        mock_init.return_value = chat

        s = dict(create_initial_state())
        s["current_qa_topic"] = "ALD"
        s["coach_tool_calls"] = 5  # _MAX_TOOL_CALLS_PER_TURN
        s["messages"] = [HumanMessage(content="x")]

        result = qa_coach_node(s)

        # LLM 호출 없이 종료
        bound.invoke.assert_not_called()
        assert "도구 호출" in result["display_output"]
        assert "초과" in result["display_output"]
        assert result["coach_tool_calls"] == 0  # 다음 턴 위해 리셋


class TestRecentWindow:
    def test_orphan_ToolMessage로_시작하면_앞을_제거한다(self):
        # 윈도우가 짝 AIMessage 없는 ToolMessage로 시작하면 Anthropic 짝 요구를 깬다
        msgs = [
            ToolMessage(content="orphan", tool_call_id="x"),
            HumanMessage(content="질문"),
            AIMessage(content="답변"),
        ]
        w = _recent_window(msgs, limit=15)
        assert not isinstance(w[0], ToolMessage)
        assert len(w) == 2

    def test_정상_순서는_그대로_유지한다(self):
        msgs = [HumanMessage(content="q"), AIMessage(content="a")]
        w = _recent_window(msgs, limit=15)
        assert w == msgs

    def test_limit으로_최근만_남긴다(self):
        msgs = [HumanMessage(content=str(i)) for i in range(20)]
        w = _recent_window(msgs, limit=5)
        assert len(w) == 5
        assert w[-1].content == "19"
