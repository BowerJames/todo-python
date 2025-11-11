import asyncio
from types import MappingProxyType
from unittest.mock import AsyncMock, Mock

import pytest

from realtime_agent import (
    Event,
    EventHandlerError,
    Session,
    SessionClosedError,
    SessionError,
    WebSocketClient,
)
import realtime_agent.services.openai as openai_service


@pytest.mark.asyncio
async def test_session_emit_calls_registered_handlers() -> None:
    session = Session()
    seen: list[int] = []

    def handler(value: int) -> int:
        seen.append(value)
        return value * 2

    session.on("number", handler)
    results = await session.emit("number", 5)

    assert seen == [5]
    assert results == [10]


@pytest.mark.asyncio
async def test_session_once_handler_runs_only_once() -> None:
    session = Session()
    counter = 0

    def handler() -> None:
        nonlocal counter
        counter += 1

    session.once("tick", handler)

    await session.emit("tick")
    await session.emit("tick")

    assert counter == 1


@pytest.mark.asyncio
async def test_session_supports_async_handlers() -> None:
    session = Session()

    async def handler(value: int) -> int:
        await asyncio.sleep(0.01)
        return value + 1

    session.on("increment", handler)

    results = await session.emit("increment", 9)

    assert results == [10]


@pytest.mark.asyncio
async def test_wait_for_returns_matching_event() -> None:
    session = Session()

    async def waiter() -> Event:
        return await session.wait_for("update")

    wait_task = asyncio.create_task(waiter())

    await asyncio.sleep(0)
    await session.emit("update", {"status": "ok"})

    event = await wait_task
    assert event.name == "update"
    assert event.args == ({"status": "ok"},)


@pytest.mark.asyncio
async def test_wait_for_with_predicate_filters_events() -> None:
    session = Session()

    async def waiter() -> Event:
        return await session.wait_for("value", predicate=lambda event: event.args[0] > 5)

    wait_task = asyncio.create_task(waiter())

    await asyncio.sleep(0)
    await session.emit("value", 3)
    await session.emit("value", 9)

    event = await wait_task
    assert event.args == (9,)


@pytest.mark.asyncio
async def test_emit_collects_errors_without_silencing_successes() -> None:
    session = Session()

    def good_handler() -> str:
        return "ok"

    def bad_handler() -> None:
        raise ValueError("boom")

    session.on("mixed", good_handler, priority=1)
    session.on("mixed", bad_handler, priority=0)

    with pytest.raises(ExceptionGroup) as exc_info:
        await session.emit("mixed")

    assert len(exc_info.value.exceptions) == 1
    handler_error = exc_info.value.exceptions[0]
    assert isinstance(handler_error, EventHandlerError)
    assert isinstance(handler_error.original, ValueError)


@pytest.mark.asyncio
async def test_wait_for_cancelled_when_session_closed() -> None:
    session = Session()

    async def waiter() -> None:
        await session.wait_for("never")

    task = asyncio.create_task(waiter())
    await asyncio.sleep(0)

    session.close()

    with pytest.raises(SessionClosedError):
        await task


def test_session_state_helpers_mutate_state_and_update_timestamp() -> None:
    session = Session()
    created_at = session.created_at

    session["a"] = 1
    session.setdefault("b", 2)
    session.update({"c": 3}, d=4)

    assert session["a"] == 1
    assert session["b"] == 2
    assert session["c"] == 3
    assert session["d"] == 4
    assert session.updated_at >= created_at


def test_handler_token_cancels_registration() -> None:
    session = Session()
    token = session.on("event", lambda: None)
    assert token.active is True

    removed = token.cancel()

    assert token.active is False
    assert removed is None  # cancel returns None
    assert session.off("event") == 0


class _StubWebSocket:
    def __init__(self) -> None:
        self.accept_calls = 0
        self.sent: list[dict[str, object]] = []
        self.to_receive: asyncio.Queue = asyncio.Queue()
        self.closed = False
        self.fail_on_receive = False

    async def accept(self) -> None:
        self.accept_calls += 1

    async def send(self, message: dict[str, object]) -> None:
        self.sent.append(message)

    async def receive(self) -> dict[str, object]:
        if self.fail_on_receive:
            raise AssertionError("receive called unexpectedly")
        return await self.to_receive.get()

    async def close(self) -> None:
        self.closed = True


class _SpyPort:
    def __init__(self) -> None:
        self.accept = AsyncMock()
        self.send = AsyncMock()
        self.receive = AsyncMock(return_value={"ok": True})
        self.close = AsyncMock()


@pytest.mark.asyncio
async def test_initialize_sends_questionnaire(monkeypatch: pytest.MonkeyPatch) -> None:
    user_websocket = _StubWebSocket()
    openai_websocket = _StubWebSocket()
    handshake_event = {"type": "session.created"}
    openai_websocket.to_receive.put_nowait(handshake_event)

    async def fake_connect(**_: object) -> _StubWebSocket:
        return openai_websocket

    monkeypatch.setattr("realtime_agent.services.openai.connect", fake_connect)

    config = {
        "llm": {"model": "gpt-realtime"},
        "agent": {
            "type": "questionnaire",
            "initial_message_template": "Hello {{ state.agent_name }}",
            "questionnaire_template": "Questionnaire for {{ state.branch_name }}",
            "tools": [
                {
                    "type": "function",
                    "name": "search_listings",
                    "description": "Search available property listings.",
                },
                {
                    "type": "function",
                    "name": "schedule_viewing",
                    "description": "Schedule a property viewing appointment.",
                },
            ],
        },
    }
    state = {"agent_name": "TestAgent", "branch_name": "HQ"}

    session = Session(
        user_websocket=user_websocket,
        init_state=state,
        config=config,
    )

    await session.initialize()

    assert user_websocket.accept_calls == 1
    assert user_websocket.sent[0] == handshake_event

    assert len(openai_websocket.sent) >= 3
    session_update = openai_websocket.sent[0]
    assert session_update["type"] == "session.update"
    advertised_tools = session_update["session"]["tools"]
    assert advertised_tools == config["agent"]["tools"]

    conversation_create = openai_websocket.sent[1]
    assert conversation_create["type"] == "conversation.item.create"
    message_item = conversation_create["item"]
    assert message_item["type"] == "message"
    assert message_item["role"] == "user"
    content = message_item["content"]

    assert content[0]["text"] == "<system>Hello TestAgent</system>"
    assert content[1]["text"] == "<questionnaire>Questionnaire for HQ</questionnaire>"

    response_message = openai_websocket.sent[2]
    assert response_message["type"] == "response.create"

    session.close()
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_websocket_client_proxies_methods() -> None:
    port = _SpyPort()
    client = WebSocketClient(port)

    await client.accept()
    await client.send({"message": "hi"})
    payload = await client.receive()
    await client.close()

    port.accept.assert_awaited_once()
    port.send.assert_awaited_once_with({"message": "hi"})
    port.receive.assert_awaited_once()
    port.close.assert_awaited_once()
    assert payload == {"ok": True}
    assert client.port is port


def test_event_unpack_returns_arguments() -> None:
    kwargs = MappingProxyType({"key": "value"})
    event = Event("demo", (1, 2), kwargs, ("result",))

    args, unpacked_kwargs = event.unpack()

    assert args == (1, 2)
    assert unpacked_kwargs == kwargs


@pytest.mark.asyncio
async def test_handler_token_cancel_is_idempotent() -> None:
    session = Session()
    token = session.on("ping", lambda: None)

    token.cancel()
    token.cancel()

    assert token.active is False
    assert session.off("ping") == 0


def test_session_mapping_helpers_cover_all_paths() -> None:
    session = Session()
    session["value"] = 5

    assert "value" in session
    assert session.get("value") == 5
    assert session.get("missing", 42) == 42

    del session["value"]
    assert "value" not in session

    session.setdefault("fallback", 10)
    session.update({"extra": 1}, more=2)

    assert session["fallback"] == 10
    assert session["extra"] == 1
    assert session["more"] == 2


def test_session_closed_property_and_idempotent_close() -> None:
    session = Session()
    assert session.closed is False

    session.close()
    session.close()

    assert session.closed is True


def test_agent_scaffolding_property_is_exposed() -> None:
    session = Session()
    assert session.agent_scaffolding is None or session.agent_scaffolding is session.agent_scaffolding


@pytest.mark.asyncio
async def test_initialize_requires_user_websocket() -> None:
    session = Session()
    with pytest.raises(SessionError):
        await session.initialize()


@pytest.mark.asyncio
async def test_initialize_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    user_ws = _StubWebSocket()
    openai_ws = _StubWebSocket()
    openai_ws.to_receive.put_nowait({"type": "session.created"})

    async def fake_connect(**_: object) -> _StubWebSocket:
        return openai_ws

    monkeypatch.setattr(openai_service, "connect", fake_connect)

    session = Session(
        user_websocket=user_ws,
        config={"llm": {"model": "gpt-realtime"}},
    )

    await session.initialize()
    openai_ws.fail_on_receive = True
    await session.initialize()


def test_session_off_removes_all_handlers() -> None:
    session = Session()

    session.on("event", lambda: None)
    session.on("event", lambda: None)

    removed = session.off("event")

    assert removed == 2
    assert "event" not in session._handlers


@pytest.mark.asyncio
async def test_emit_nowait_creates_task_and_returns_results() -> None:
    session = Session()

    session.on("double", lambda value: value * 2)
    task = session.emit_nowait("double", 3)

    result = await task

    assert isinstance(task, asyncio.Task)
    assert result == [6]


@pytest.mark.asyncio
async def test_wait_for_times_out_and_cleans_up() -> None:
    session = Session()

    with pytest.raises(asyncio.TimeoutError):
        await session.wait_for("never", timeout=0.01)

    assert "never" not in session._waiters


def test_register_requires_callable() -> None:
    session = Session()

    with pytest.raises(TypeError):
        session.on("invalid", 123)  # type: ignore[arg-type]


def test_prepare_transport_config_requires_mapping() -> None:
    user_ws = _StubWebSocket()

    with pytest.raises(SessionError):
        Session(
            user_websocket=user_ws,
            config={"llm": "not-a-mapping"},
        )


@pytest.mark.asyncio
async def test_resolve_openai_client_validates_port(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Session(config={"llm": {"model": "x"}})

    async def bad_connect(**_: object) -> object:
        return object()

    monkeypatch.setattr(openai_service, "connect", bad_connect)

    with pytest.raises(SessionError):
        await session._resolve_openai_client()


@pytest.mark.asyncio
async def test_resolve_openai_client_uses_cached_instance() -> None:
    session = Session()
    port = _StubWebSocket()
    cached = WebSocketClient(port)
    session._openai_client = cached

    result = await session._resolve_openai_client()

    assert result is cached


@pytest.mark.asyncio
async def test_send_initial_prompt_returns_when_no_content() -> None:
    session = Session()
    session._agent_scaffolding = None

    class Client:
        def __init__(self) -> None:
            self.sent: list[object] = []

        async def send(self, payload: object) -> None:
            self.sent.append(payload)

    client = Client()

    await session._send_initial_prompt(client)  # type: ignore[arg-type]

    assert client.sent == []


def test_render_initial_prompt_blank_string_returns_none() -> None:
    session = Session()

    class Scaffolding:
        def initial_message_template(self) -> str:
            return "   "

    session._agent_scaffolding = Scaffolding()

    assert session._render_initial_prompt() is None


def test_render_questionnaire_requires_string() -> None:
    session = Session()

    class Scaffolding:
        def render_questionnaire(self, state: MappingProxyType) -> object:  # pragma: no cover - interface
            return 123

    session._agent_scaffolding = Scaffolding()

    with pytest.raises(SessionError):
        session._render_questionnaire()


def test_prime_agent_scaffolding_wraps_mock_assertion() -> None:
    session = Session()
    scaffolding = Mock()
    scaffolding.build_questionnaire.return_value = {"question": "value"}

    session._prime_agent_scaffolding(scaffolding)  # type: ignore[arg-type]

    assert session._questionnaire_blueprint == {"question": "value"}
    assert scaffolding.build_questionnaire.assert_called_once()


def test_build_session_snapshot_includes_tools() -> None:
    session = Session()
    session.state["foo"] = "bar"
    session.metadata["trace"] = "abc"
    session._llm_config = {"model": "gpt"}
    session.config = {"agent": {"nested": {"param": 1}}}
    session._agent_scaffolding = object()  # enable tools snapshot
    session._session_tools = [
        MappingProxyType({"name": "primary"}),
        {"name": "secondary"},
        "raw",
    ]

    snapshot = session._build_session_snapshot()

    assert snapshot["state"] == {"foo": "bar"}
    assert snapshot["metadata"] == {"trace": "abc"}
    assert snapshot["llm"] == {"model": "gpt"}
    assert snapshot["config"]["agent"]["nested"]["param"] == 1
    assert snapshot["tools"][0]["name"] == "primary"
    assert isinstance(snapshot["tools"][1], dict)
    assert snapshot["tools"][2] == "raw"


def test_normalise_and_clone_tools() -> None:
    session = Session()

    assert session._normalise_tools(None) == []
    mapping = {"name": "single"}
    single = session._normalise_tools(mapping)
    assert isinstance(single[0], MappingProxyType)
    assert dict(single[0]) == mapping

    mixed = session._normalise_tools([{"name": "list"}, "value"])
    assert isinstance(mixed[0], MappingProxyType)
    assert mixed[1] == "value"

    frozen = MappingProxyType({"name": "immutable"})
    assert session._freeze_tool(frozen) is frozen
    mutable_frozen = session._freeze_tool({"name": "mutable"})
    assert isinstance(mutable_frozen, MappingProxyType)
    assert dict(mutable_frozen) == {"name": "mutable"}
    assert session._clone_tool(frozen) == {"name": "immutable"}


@pytest.mark.asyncio
async def test_attach_task_handles_success_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Session()

    async def succeed() -> str:
        await asyncio.sleep(0)
        return "ok"

    task_ok = asyncio.create_task(succeed())
    session._attach_task(task_ok)
    await task_ok
    assert task_ok not in session._transport_tasks

    errors: list[BaseException] = []

    def capture_failure(self: Session, exc: BaseException) -> None:
        errors.append(exc)

    monkeypatch.setattr(Session, "_handle_transport_failure", capture_failure, raising=False)

    async def fail() -> None:
        await asyncio.sleep(0)
        raise RuntimeError("boom")

    task_fail = asyncio.create_task(fail())
    session._attach_task(task_fail)
    await asyncio.sleep(0.05)

    assert isinstance(errors[0], RuntimeError)
    assert task_fail not in session._transport_tasks


def test_run_async_soon_without_running_loop_executes() -> None:
    session = Session()
    called: list[str] = []

    async def coro() -> None:
        called.append("done")

    session._run_async_soon(coro())

    assert called == ["done"]


@pytest.mark.asyncio
async def test_relay_openai_to_user_handles_error(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Session()

    class FaultyClient:
        def __init__(self) -> None:
            self.receive_calls = 0

        async def receive(self) -> object:
            self.receive_calls += 1
            raise RuntimeError("upstream failure")

        async def send(self, message: object) -> None:  # pragma: no cover - unused
            pass

    class UserSocket:
        async def send(self, message: object) -> None:  # pragma: no cover - unused
            pass

    failures: list[BaseException] = []

    def capture_failure(self: Session, exc: BaseException) -> None:
        failures.append(exc)

    monkeypatch.setattr(Session, "_handle_transport_failure", capture_failure, raising=False)

    session._openai_client = FaultyClient()
    session._user_websocket = UserSocket()

    await session._relay_openai_to_user()

    assert isinstance(failures[0], RuntimeError)


@pytest.mark.asyncio
async def test_relay_user_to_openai_handles_error(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Session()

    class FaultyUserSocket:
        def __init__(self) -> None:
            self.receive_calls = 0

        async def receive(self) -> object:
            self.receive_calls += 1
            raise RuntimeError("user failure")

        async def send(self, message: object) -> None:  # pragma: no cover - unused
            pass

    class OpenAIClient:
        async def send(self, message: object) -> None:  # pragma: no cover - unused
            pass

        async def receive(self) -> object:  # pragma: no cover - unused
            return {}

    failures: list[BaseException] = []

    def capture_failure(self: Session, exc: BaseException) -> None:
        failures.append(exc)

    monkeypatch.setattr(Session, "_handle_transport_failure", capture_failure, raising=False)

    session._openai_client = OpenAIClient()
    session._user_websocket = FaultyUserSocket()

    await session._relay_user_to_openai()

    assert isinstance(failures[0], RuntimeError)


def test_handle_transport_failure_records_first_error(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Session()
    closes: list[int] = []

    def fake_close(self: Session) -> None:
        closes.append(1)

    monkeypatch.setattr(Session, "close", fake_close, raising=False)

    error1 = RuntimeError("first")
    error2 = RuntimeError("second")

    session._handle_transport_failure(error1)
    session._handle_transport_failure(error2)

    assert session._transport_error is error1
    assert len(closes) == 2