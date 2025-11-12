import pytest
import uuid

from realtime_agent import Session

def test_session_builds(
    monkeypatch: pytest.MonkeyPatch,
    session_id: uuid.UUID,
    session: Session,
):
    assert session.id == session_id.hex

def test_session_created_at_is_set(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
):
pass
    
