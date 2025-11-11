import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from realtime_agent import Session
import realtime_agent.services.openai as openai
import uuid

from dev.websocket_port import MyTestWebSocketPort
from realtime_agent.scaffolding import QuestionnaireAgentScaffolding

@pytest.fixture
def initial_message_template():
    return "Say 'Hello, this is {{state.agent_name}} from {{state.branch_name}}, how can I help you today?'"

@pytest.fixture
def system_prompt_template():
    return (
        "You are a helpful assistant called {{state.agent_name}} from {{state.branch_name}}.\n\n"
    )

@pytest.fixture
def model():
    return "gpt-realtime"

@pytest.fixture
def questionnaire():
    return Mock()

@pytest.fixture
def rendered_questionnaire():
    return "RENDERED_QUESTIONNAIRE"

@pytest.fixture
def llm_config(model) -> dict:
    return {
        "model": model
    }

@pytest.fixture
def agent_kwargs():
    return {}

@pytest.fixture
def agent_config() -> dict:
    return {
        "type": "questionnaire"
    }

@pytest.fixture
def config(llm_config, agent_config) -> dict:
    return {
        "llm": llm_config,
        "agent": agent_config,
    }

@pytest.fixture
def user_websocket():
    return MyTestWebSocketPort()

@pytest.fixture
def openai_websocket():
    return MyTestWebSocketPort()

@pytest.fixture
def init_state():
    return {
        "agent_name": "test_agent",
        "branch_name": "test_branch",
        "branch_ids": ["8134", "8135"],
        "office_id": 17801,   
    }

@pytest.fixture
def session_created_event():
    return {
        "type": "session.created",
    }

@pytest_asyncio.fixture
async def built_session(
    monkeypatch: pytest.MonkeyPatch,
    init_state,
    config,
    questionnaire,
    user_websocket,
    openai_websocket,
):

    questionnaire_mock = Mock(return_value=questionnaire)
    with monkeypatch.context() as m:
        m.setattr(QuestionnaireAgentScaffolding, "build_questionnaire", questionnaire_mock)
        session = Session(
            user_websocket=user_websocket,
            init_state=init_state,
            config=config,
        )
    user_websocket.sent.clear()
    openai_websocket.sent.clear()
    return session

@pytest_asyncio.fixture
async def initialized_session(
    monkeypatch: pytest.MonkeyPatch,
    built_session: Session,
    initial_message_template: str,
    rendered_questionnaire: str,
    user_websocket: MyTestWebSocketPort,
    openai_websocket: MyTestWebSocketPort,
    session_created_event: dict,
):

    initial_message_template_mock = Mock(
        return_value=initial_message_template
    )
    accept_mock = AsyncMock(return_value=None)
    render_questionnaire_mock = Mock(return_value=rendered_questionnaire)
    openai_connect_mock = AsyncMock(return_value=openai_websocket)
    from_openai_queue = openai_websocket.to_receive
    with monkeypatch.context() as m:
        m.setattr(built_session.agent_scaffolding, "initial_message_template", initial_message_template_mock)
        m.setattr(user_websocket, "accept", accept_mock)
        m.setattr(openai, "connect", openai_connect_mock)
        m.setattr(built_session.agent_scaffolding, "render_questionnaire", render_questionnaire_mock)
        task = asyncio.create_task(built_session.initialize())
        await asyncio.sleep(0.2)
        from_openai_queue.put_nowait(session_created_event)
        await asyncio.sleep(0.2)
        assert task.done()
        await task
    user_websocket.sent.clear()
    openai_websocket.sent.clear()
    return built_session