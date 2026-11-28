from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.extensions.superagent.service import PendingInteraction, TicketService
from gateway.extensions.superagent.sidecar import SidecarError
from gateway.extensions.superagent.router_adapter import _SCHEMA
from jiuwenswarm.channels.process_cli.machine_policy import parse_structured_output


def test_report_requires_worker_result_not_just_chat_final():
    assert TicketService._report({"content": "Done"})["state"] == "blocked"
    assert TicketService._report({"content": '{"state":"ready","summary":"wrote test file"}'}) == {
        "state": "ready", "summary": "wrote test file",
    }


def test_router_accept_requires_a_title_before_the_result_reaches_core():
    decision = {"action": "accept", "reason": "new task", "instruction": "write the requested file"}
    with pytest.raises(ValueError, match="output_schema"):
        parse_structured_output(json.dumps(decision), _SCHEMA)
    assert parse_structured_output(json.dumps({**decision, "title": "Fixture"}), _SCHEMA)["title"] == "Fixture"


@pytest.mark.asyncio
async def test_approval_scope_and_replay():
    service = TicketService(None, None, None)
    answer = asyncio.get_running_loop().create_future()
    event = {"request_id": "native-permission", "source": "permission_interrupt",
             "questions": [{"question": "write?", "options": [
                 {"value": "allow_once", "label": "允许一次"}]}]}
    service.interactions["ticket"] = PendingInteraction("owner", "session", "operation", event, answer)
    reply = [{"question": "write?", "selected_options": ["allow_once"], "custom_input": ""}]
    assert service.interaction("ticket", "other") is None
    with pytest.raises(SidecarError, match="STALE_INTERACTION"):
        service.answer("ticket", "other", "native-permission", reply)
    with pytest.raises(SidecarError, match="STALE_INTERACTION"):
        service.answer("ticket", "owner", "different-permission", reply)
    with pytest.raises(SidecarError, match="INVALID_ANSWER"):
        service.answer("ticket", "owner", "native-permission", [
            {"question": "write?", "selected_options": ["allow_always"]},
        ])
    service.answer("ticket", "owner", "native-permission", reply)
    assert answer.result() == reply
    with pytest.raises(SidecarError, match="STALE_INTERACTION"):
        service.answer("ticket", "owner", "native-permission", reply)


@pytest.mark.asyncio
async def test_approval_keeps_the_original_worker_stream():
    continued = asyncio.Event()

    class Executor:
        async def answer(self, user, session, interaction, source, replies):
            assert (user, session, interaction, source) == ("owner", "session", "approval", "permission_interrupt")
            assert replies[0]["selected_options"] == ["allow_once"]
            continued.set()
            await asyncio.Event().wait()  # The control acknowledgement goes to the Gateway push handler.

    async def stream():
        yield {"event_type": "chat.ask_user_question", "request_id": "approval",
               "source": "permission_interrupt", "questions": [{"question": "Write file?"}]}
        await continued.wait()
        yield {"event_type": "chat.final", "complete": True,
               "content": '{"state":"ready","summary":"Wrote the file"}'}

    service = TicketService(None, None, Executor())
    service._wait_for_interaction = AsyncMock(return_value=[{"selected_options": ["allow_once"]}])
    service._operation = AsyncMock()
    operation = {"owner": "owner", "kind": "start"}
    async with asyncio.timeout(1):
        await service._consume(stream(), operation, "session")
    service._operation.assert_awaited_once_with(
        "report", operation, report={"state": "ready", "summary": "Wrote the file"},
    )


@pytest.mark.asyncio
async def test_worker_stream_without_a_terminal_event_requires_reconciliation():
    async def stream():
        yield {"event_type": "chat.delta", "content": "Work may have started"}

    service = TicketService(None, None, None)
    service._operation = AsyncMock()
    operation = {"kind": "start"}
    await service._consume(stream(), operation, "session")
    service._operation.assert_awaited_once_with("uncertain", operation)


@pytest.mark.asyncio
async def test_stop_drains_only_after_runtime_receives_dispatch():
    transport_ready = asyncio.Event()
    runtime_ready = asyncio.Event()

    async def stream(*args):
        transport_ready.set()
        yield {"event_type": "keepalive"}
        await runtime_ready.wait()
        yield {"event_type": "chat.delta"}

    executor = SimpleNamespace(stream=stream, stop=AsyncMock())
    service = TicketService(None, None, executor)
    service._operation = AsyncMock(return_value=True)
    operation = {"kind": "deliver", "owner": "owner", "ticketId": "ticket", "id": "work",
                 "session_id": "session", "project_dir": "/workspace"}
    async with asyncio.timeout(1):
        worker = asyncio.create_task(service._worker(operation))
        await transport_ready.wait()
        cancel = asyncio.create_task(service._stop({**operation, "id": "cancel"}))
        await asyncio.sleep(0)
        executor.stop.assert_not_awaited()
        runtime_ready.set()
        await asyncio.gather(worker, cancel)
    executor.stop.assert_awaited_once_with("owner", "session", "cancel")
