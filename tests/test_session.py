import asyncio

import pytest

from realtime_agent import Event, EventHandlerError, Session, SessionClosedError


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

    async def accept(self) -> None:
        self.accept_calls += 1

    async def send(self, message: dict[str, object]) -> None:
        self.sent.append(message)

    async def receive(self) -> dict[str, object]:
        return await self.to_receive.get()

    async def close(self) -> None:
        self.closed = True


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

