"""Call the existing platform session and interaction transport."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import contextlib
from pathlib import Path
from uuid import uuid4

from jiuwenswarm.common.e2a.gateway_normalize import e2a_from_agent_fields
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.runtime.interaction import InteractionAnswerInput
from jiuwenswarm.runtime.events import TERMINAL_ERROR_EVENT_TYPES


class PlatformExecutionError(RuntimeError):
    """A platform operation failed or its outcome could not be established."""


class PlatformExecutor:
    def __init__(self, agent_client, project_id: str, model_selection: dict[str, str]):
        self.client = agent_client
        self.project_id = project_id
        self.model_selection = dict(model_selection)

    @staticmethod
    def _envelope(method, request_id, user_id, session_id, params, *, stream=False):
        return e2a_from_agent_fields(
            request_id=request_id,
            req_method=method,
            channel_id="web",
            session_id=session_id,
            user_id=user_id,
            params=params,
            is_stream=stream,
        )

    async def _request(self, method, request_id, user_id, params, session_id=None):
        envelope = self._envelope(method, request_id, user_id, session_id, params)
        async with asyncio.timeout(40):
            response = await self.client.send_request(envelope)
        payload = response.payload or {}
        if not response.ok or payload.get("success") is False:
            raise PlatformExecutionError(str(payload.get("code") or "PLATFORM_REQUEST_FAILED"))
        return payload

    async def create(self, user_id: str, create_token: str, title: str) -> tuple[str, str]:
        result = await self._request(
            ReqMethod.SESSION_CREATE,
            f"superagent-create-{create_token}",
            user_id,
            {
                "project_id": self.project_id,
                "execution_provider": "opencode-direct",
                "mode": "code",
                "work_mode": "code",
                "persist_session": True,
                "create_token": create_token,
                "title": title,
                "model_selection": self.model_selection,
            },
        )
        session_id = result.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise PlatformExecutionError("SESSION_ID_UNCONFIRMED")
        project_dir = result.get("projectDir")
        if result.get("projectId") != self.project_id or not isinstance(project_dir, str) \
                or not Path(project_dir).is_absolute():
            raise PlatformExecutionError("PROJECT_BINDING_UNCONFIRMED")
        return session_id, project_dir

    async def stream(self, user_id: str, session_id: str, project_dir: str,
                     request_id: str, text: str) -> AsyncIterator[dict]:
        envelope = self._envelope(
            ReqMethod.CHAT_SEND, request_id, user_id, session_id,
            {
                "query": text,
                "content": text,
                "mode": "code",
                "work_mode": "code",
                "project_id": self.project_id,
                "project_dir": project_dir,
                "cwd": project_dir,
                "execution_provider": "opencode-direct",
                "model_selection": self.model_selection,
                "supports_user_interaction": True,
            },
            stream=True,
        )
        async with contextlib.aclosing(self._events(envelope)) as events:
            async for event in events:
                yield event

    async def answer(self, user_id: str, session_id: str, interaction_id: str,
                     source: str, answers: list[dict]) -> None:
        command = InteractionAnswerInput(
            request_id=f"superagent-answer-{uuid4().hex}",
            channel_id="web",
            session_id=session_id,
            interaction_id=interaction_id,
            answers=tuple(answers),
            source=source,
            mode="code",
            work_mode="code",
        ).to_agent_request()
        envelope = self._envelope(
            command.req_method, command.request_id, user_id, session_id, command.params,
            stream=command.is_stream,
        )
        if command.is_stream:
            # AgentServer can publish the acknowledgement as a control push.
            # Execution output remains on the original OpenCode request.
            async with contextlib.aclosing(self._events(envelope)) as responses:
                async for event in responses:
                    if event.get("failed"):
                        raise PlatformExecutionError("INTERACTION_ANSWER_REJECTED")
        else:
            response = await self.client.send_request(envelope)
            if not response.ok or (response.payload or {}).get("success") is False:
                raise PlatformExecutionError("INTERACTION_ANSWER_REJECTED")

    async def _events(self, envelope) -> AsyncIterator[dict]:
        async with contextlib.aclosing(self.client.send_request_stream(envelope)) as responses:
            async for chunk in responses:
                payload = chunk.payload if isinstance(chunk.payload, dict) else {}
                data = dict(payload)
                data["complete"] = bool(chunk.is_complete)
                data["failed"] = data.get("success") is False or data.get("event_type") in TERMINAL_ERROR_EVENT_TYPES
                yield data

    async def stop(self, user_id: str, session_id: str, operation_id: str) -> None:
        result = await self._request(
            ReqMethod.CHAT_CANCEL,
            f"superagent-stop-{operation_id}-{uuid4().hex}",
            user_id,
            {"intent": "cancel", "mode": "code", "work_mode": "code", "wait_for_stop": True},
            session_id,
        )
        if result.get("success") is not True:
            raise PlatformExecutionError("PLATFORM_STOP_UNCONFIRMED")
