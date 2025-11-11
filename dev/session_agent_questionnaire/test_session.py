import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from dataclasses import dataclass
from jinja2 import Template
from realtime_agent import Session
from realtime_agent import WebSocketPort
import realtime_agent.services.openai as openai
import uuid

from dev.websocket_port import MyTestWebSocketPort
from realtime_agent.scaffolding import QuestionnaireAgentScaffolding

@pytest.fixture
def tool_1():
    return {
        "type": "function",
        "name": "tool_1",
        "description": "Tool 1",
        "parameters": {
            "type": "object",
            "properties": {
                "property_1": {"type": "string"},
            }
        }
    }

@pytest.fixture
def tool_2():
    return {
        "type": "function",
        "name": "tool_2",
        "description": "Tool 2",
    }

@pytest.fixture
def tools():
    return [tool_1, tool_2]

@pytest.mark.asyncio
async def test_session_builds(
    monkeypatch: pytest.MonkeyPatch,
    init_state,
    config,
    user_websocket,
    questionnaire,
    ):
    questionnaire_mock = Mock(return_value=questionnaire)
    with monkeypatch.context() as m:
        m.setattr(QuestionnaireAgentScaffolding, "build_questionnaire", questionnaire_mock)
        session = Session(
            user_websocket=user_websocket,
            init_state=init_state,
            config=config,
        )
        questionnaire_mock.assert_called_once()
    return session

@pytest.mark.asyncio
async def test_session_initialize(
    monkeypatch: pytest.MonkeyPatch,
    built_session: Session,
    user_websocket: MyTestWebSocketPort,
    openai_websocket: MyTestWebSocketPort,
    initial_message_template: str,
    rendered_questionnaire: str,
    session_created_event: dict,
    init_state: dict,
    tools: list,
):

    initial_message_template_mock = Mock(
        return_value=initial_message_template
    )
    render_questionnaire_mock = Mock(return_value=rendered_questionnaire)
    accept_mock = AsyncMock(return_value=initial_message_template)
    openai_connect_mock = AsyncMock(return_value=openai_websocket)
    from_openai_queue = openai_websocket.to_receive
    agent_scaffolding = built_session.agent_scaffolding
    tools_mock = Mock(return_value=tools)

    with monkeypatch.context() as m:

        m.setattr(agent_scaffolding, "initial_message_template", initial_message_template_mock)
        m.setattr(user_websocket, "accept", accept_mock)
        m.setattr(openai, "connect", openai_connect_mock)
        m.setattr(agent_scaffolding, "render_questionnaire", render_questionnaire_mock)
        m.setattr(agent_scaffolding, "tools", tools_mock)
        task = asyncio.create_task(built_session.initialize())
        await asyncio.sleep(0.2)
        openai_connect_mock.assert_awaited_once_with()
        accept_mock.assert_not_awaited()
        assert not task.done()

        from_openai_queue.put_nowait(session_created_event)
        await asyncio.sleep(0.2)
        assert task.done()
        await task

    accept_mock.assert_awaited_once()
    initial_message_template_mock.assert_called_once()
    render_questionnaire_mock.assert_called_once()
    tools_mock.assert_called_once()

    session_created_user_event = user_websocket.sent.pop(0)
    session_created_user_event.event == session_created_event

    session_update_openai_event = openai_websocket.sent.pop(0)
    assert session_created_user_event.timestamp < session_update_openai_event.timestamp
    event = session_update_openai_event.event
    assert "type" in event and event["type"] == "session.update" , f"Expected session.update event, got {event}"
    assert "session" in event and isinstance(event["session"], dict) , f"Expected event to have a 'session' key which is a dict, but that is not the case for {event}"
    session = event["session"]
    assert "tools" in session and isinstance(session["tools"], list) and len(session["tools"]) > 0, f"Expected session to have a 'tools' key which is a non empty list, but that is not the case for {session}"
    for tool in tools:
        assert any(tool == session_tool for session_tool in session["tools"]), f"Expected session to have tool {tool}, but that is not the case for {session}"


    event = openai_websocket.sent.pop(0).event
    assert "type" in event and event["type"] == "conversation.item.create", f"Expected conversation.item.create event, got {event}"
    assert "item" in event and isinstance(event["item"], dict) , f"Expected event to have a 'item' key which is a dict, but that is not the case for {event}"
    item = event["item"]
    assert "type" in item and item["type"] == "message", f"Expected item to have a 'type' key which is 'message', but that is not the case for {item}"
    assert "role" in item and item["role"] == "user", f"Expected item to have a 'role' key which is 'user', but that is not the case for {item}"
    assert "content" in item and isinstance(item["content"], list) and len(item["content"]) > 0, f"Expected item to have a 'content' key which is a non empty list, but that is not the case for {item}"
    content = item["content"]
    content_0 = content[0]
    assert "type" in content_0 and content_0["type"] == "input_text", f"Expected content_0 to have a 'type' key which is 'input_text', but that is not the case for {content_0}"
    assert "text" in content_0 and isinstance(content_0["text"], str), f"Expected content_0 to have a 'text' key which is a non empty string, but that is not the case for {content_0}"
    text = content_0["text"]
    expected_text = "<system>" + Template(initial_message_template_mock.return_value).render(state=init_state) + "</system>"
    assert text == expected_text, f"Expected text to be {expected_text}, but got {text}"
    content_1 = content[1]
    assert "type" in content_1 and content_1["type"] == "input_text", f"Expected content_1 to have a 'type' key which is 'input_text', but that is not the case for {content_1}"
    assert "text" in content_1 and isinstance(content_1["text"], str), f"Expected content_1 to have a 'text' key which is a non empty string, but that is not the case for {content_1}"
    text = content_1["text"]
    expected_text = "<questionnaire>" + rendered_questionnaire + "</questionnaire>"
    assert text == expected_text, f"Expected text to be {expected_text}, but got {text}"

    event = openai_websocket.sent.pop(0).event
    assert "type" in event and event["type"] == "response.create", f"Expected response.create event, got {event}"
    
    from_openai_queue.put_nowait(
        {
            "type": "session.updated",
            "session": {}
        }
    )
    await asyncio.sleep(0.2)
    user_websocket.sent.pop(0).event == session_created_event

@pytest.mark.asyncio
async def test_session_forwards_user_message_to_openai(
    monkeypatch: pytest.MonkeyPatch,
    initialized_session: Session,
    user_websocket: MyTestWebSocketPort,
    openai_websocket: MyTestWebSocketPort,
):
    from_user_queue = user_websocket.to_receive
    
    # All messages will be forwarded to openai so check a variety of random messages
    random_messages = [
        {
            "type": "foo",
            "content": "bar"
        },
        {
            "foo": "bar",
        },
        {
            f"uuid-{uuid.uuid4().hex}": f"uuid-{uuid.uuid4().hex}",
            "item": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Hello, how are you?"
                    }
                ]
            }
        },
        {}
    ]

    for message in random_messages:
        from_user_queue.put_nowait(message)
    await asyncio.sleep(0.2)
    assert len(openai_websocket.sent) == len(random_messages)
    for i in range(len(random_messages)):
        assert openai_websocket.sent[i].event == random_messages[i]

@pytest.mark.asyncio
async def test_session_forwards_openai_response_to_user(
    monkeypatch: pytest.MonkeyPatch,
    initialized_session: Session,
    user_websocket: MyTestWebSocketPort,
    openai_websocket: MyTestWebSocketPort,
):
    from_openai_queue = openai_websocket.to_receive
    from_user_queue = user_websocket.to_receive

    # All responses will be forwarded to user so check a variety of random responses
    random_responses = [
        {
            "type": "foo",
            "content": "bar"
        },
        {
            "foo": "bar",
        },
        {
            f"uuid-{uuid.uuid4().hex}": f"uuid-{uuid.uuid4().hex}",
            "item": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Hello, how are you?"
                    }
                ]
            }
        },
    ]

    for response in random_responses:
        from_openai_queue.put_nowait(response)
    await asyncio.sleep(0.2)
    assert len(user_websocket.sent) == len(random_responses)
    for i in range(len(random_responses)):
        assert user_websocket.sent[i].event == random_responses[i]