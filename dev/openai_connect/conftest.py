import pytest
from unittest.mock import create_autospec
from websockets.asyncio.client import ClientConnection

@pytest.fixture
def model():
    return "gpt-model"

@pytest.fixture
def api_key():
    return "test"

@pytest.fixture
def root_url():
    return "wss://api.openai-test.com/v1/realtime"

@pytest.fixture
def url(root_url, model):
    return f"{root_url}?model={model}"

@pytest.fixture
def headers(api_key):
    return {
        "Authorization": f"Bearer {api_key}",
    }

@pytest.fixture
def mock_client_connection():
    return create_autospec(ClientConnection)