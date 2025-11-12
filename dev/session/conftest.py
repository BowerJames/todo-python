import pytest
from unittest.mock import create_autospec, Mock

import uuid
from typing import Any

from realtime_agent import WebSocketPort
from realtime_agent import Session

@pytest.fixture
def init_state() -> dict[str, Any]:
    return {
        "agent_name": "test_agent",
        "branch_name": "test_branch",
        "branch_ids": ["8134", "8135"],
        "office_id": 17801,   
    }

@pytest.fixture
def llm_config() -> dict[str, Any]:
    return {
        "model": "gpt-realtime",
    }

@pytest.fixture
def agent_scaffolding_config() -> dict[str, Any]:
    return {
        "type": "questionnaire",
        "scaffolding_kwargs": {
            "foo": "bar",
        }
    }

@pytest.fixture
def user_websocket() -> WebSocketPort:
    return create_autospec(WebSocketPort)

@pytest.fixture
def session_id() -> uuid.UUID:
    return uuid.uuid4()

@pytest.fixture
def session(
    monkeypatch: pytest.MonkeyPatch,
    session_id,
    init_state,
    llm_config,
    agent_scaffolding_config,
    user_websocket,
) -> Session:
    with monkeypatch.context() as m:
        m.setattr(uuid, "uuid4", Mock(return_value=session_id))
        session = Session(
            init_state=init_state,
            llm_config=llm_config,
            agent_scaffolding_config=agent_scaffolding_config,
            user_websocket=user_websocket,
        )
    return session
