"""Authenticated Web ticket endpoints."""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from gateway.extensions.auth.credential_authenticator import AuthContext
from gateway.extensions.sdk.application_plugin import HTTPRouteContribution
from gateway.extensions.superagent.sidecar import SidecarError
from gateway.extensions.superagent.workbench import WorkbenchAPI


PREFIX = "/api/superagent/v1"
_ERRORS = {
    "FORBIDDEN": 403, "NOT_FOUND": 404, "BAD_REQUEST": 400, "CONFLICT": 409,
    "TICKET_STOPPED": 409, "EXECUTION_UNCERTAIN": 409, "STALE_INTERACTION": 409,
    "INVALID_ANSWER": 400,
}


class TicketInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=12000)


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(max_length=1000)
    selected_options: list[str] = Field(default_factory=list, max_length=30)
    custom_input: str = Field(default="", max_length=2000)
    card_id: str | None = Field(default=None, max_length=128)


class InteractionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers: list[Answer] = Field(min_length=1, max_length=30)


class TicketAPI:
    def __init__(self, plugin, public_origin: str):
        origin = urlsplit(public_origin)
        if origin.scheme not in ("http", "https") or not origin.netloc or origin.path not in ("", "/"):
            raise ValueError("superagent.public_origin must identify the Web origin")
        self.origin = f"{origin.scheme}://{origin.netloc}"
        self.plugin = plugin
        self.workbench = WorkbenchAPI(self)

    def routes(self):
        return (
            HTTPRouteContribution(PREFIX + "/tickets", self.tickets, ("GET", "POST")),
            HTTPRouteContribution(PREFIX + "/tickets/{ticket_id}", self.detail),
            HTTPRouteContribution(PREFIX + "/tickets/{ticket_id}/follow", self.follow, ("POST",)),
            HTTPRouteContribution(PREFIX + "/tickets/{ticket_id}/stop", self.stop, ("POST",)),
            HTTPRouteContribution(PREFIX + "/tickets/{ticket_id}/interactions/{interaction_id}/answer",
                                  self.answer, ("POST",)),
            HTTPRouteContribution(PREFIX + "/sessions/{session_id}", self.managed_session),
            HTTPRouteContribution("/orchestrator/api/{view}", self.management, ("GET", "POST", "PUT")),
            HTTPRouteContribution("/orchestrator/api/{view}/{item_id}", self.management, ("GET", "POST", "PUT")),
            HTTPRouteContribution("/orchestrator/api/{view}/{item_id}/{action}", self.management, ("POST",)),
            *self.workbench.routes(),
        )

    async def _owner(self, request: Request):
        if request.method != "GET" and request.headers.get("origin") != self.origin:
            raise HTTPException(403, detail="ORIGIN_DENIED")
        account = self.plugin.account_authority()
        if account is not None:
            result = await account.authenticate(AuthContext(channel_type="http", headers=dict(request.headers)))
        elif self.plugin.channel is not None:
            result = await self.plugin.channel.authenticate_handshake(
                path=request.url.path, headers=request.headers, channel="web",
            )
        else:
            result = None
        if result is None or not result.success:
            raise HTTPException(401, detail="AUTHENTICATION_REQUIRED")
        details = result.extensions or {}
        guard = details.get("request_guard")
        if callable(guard):
            try:
                await guard()
            except (PermissionError, ValueError, RuntimeError, OSError):
                raise HTTPException(401, detail="AUTHENTICATION_REQUIRED") from None
        owner = details.get("routing_user_id") or result.user_id
        if owner not in self.plugin.settings["members"]:
            raise HTTPException(403, detail="PROJECT_NOT_ALLOWED")
        return owner

    @staticmethod
    async def _body(request, schema):
        try:
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > 64 * 1024:
                    raise HTTPException(413, detail="REQUEST_TOO_LARGE")
            return schema.model_validate_json(raw)
        except ValidationError:
            raise HTTPException(400, detail="BAD_REQUEST") from None

    async def _call(self, method, owner, **fields):
        service = self.plugin.service
        if service is None:
            raise HTTPException(503, detail="PLUGIN_NOT_READY")
        try:
            return await service.sidecar.call(method, {"owner": owner, **fields})
        except SidecarError as error:
            code = str(error)
            raise HTTPException(_ERRORS.get(code, 503), detail=code) from None

    async def tickets(self, request: Request):
        owner = await self._owner(request)
        if request.method == "GET":
            items = await self._call("requests", owner)
            for item in items:
                if item.get("ticket"):
                    self._include_interaction(item["ticket"], owner)
            return items
        data = await self._body(request, TicketInput)
        return await self._call("submit", owner, **data.model_dump())

    def _include_interaction(self, ticket, owner):
        ticket["interaction"] = self.plugin.service.interaction(ticket["id"], owner)
        return ticket

    async def detail(self, request: Request):
        owner = await self._owner(request)
        ticket = await self._call("ticket", owner, ticket_id=request.path_params["ticket_id"])
        return self._include_interaction(ticket, owner)

    async def follow(self, request: Request):
        owner = await self._owner(request)
        data = await self._body(request, TicketInput)
        return await self._call("follow", owner, ticket_id=request.path_params["ticket_id"], **data.model_dump())

    async def stop(self, request: Request):
        owner = await self._owner(request)
        return await self._call("cancel", owner, ticket_id=request.path_params["ticket_id"])

    async def answer(self, request: Request):
        owner = await self._owner(request)
        ticket_id = request.path_params["ticket_id"]
        data = await self._body(request, InteractionInput)
        ticket = await self._call("ticket", owner, ticket_id=ticket_id)
        if ticket.get("outcome"):
            raise HTTPException(409, detail="TICKET_ENDED")
        try:
            self.plugin.service.answer(ticket_id, owner, request.path_params["interaction_id"],
                                       [item.model_dump(exclude_none=True) for item in data.answers])
        except SidecarError as error:
            raise HTTPException(_ERRORS.get(str(error), 503), detail=str(error)) from None
        return {"accepted": True}

    async def managed_session(self, request: Request):
        owner = await self._owner(request)
        ticket = await self._call("managed_session", owner, session_id=request.path_params["session_id"])
        return self._include_interaction(ticket, owner)

    async def management(self, request: Request):
        owner = await self._owner(request)
        path = request.path_params
        view = path["view"]
        item_id = path.get("item_id")
        if request.method == "POST" and view == "tickets" and path.get("action") == "stop":
            await self._call("cancel", owner, ticket_id=item_id)
            return {"stopped": True}
        if request.method == "GET":
            if item_id and view in {"tickets", "threads"}:
                view = {"tickets": "ticket", "threads": "thread"}[view]
            params = {name: request.query_params[name] for name in
                      ("q", "filter", "kind", "window", "offset", "limit", "state")
                      if name in request.query_params}
            params.setdefault("state", "open")
            params.setdefault("filter", "subscribed")
            result = await self._call("management", owner, view=view, id=item_id, **params)
            if result is not None:
                return result
            if view in {"ticket", "thread"}:
                raise HTTPException(404, detail="NOT_FOUND")
        return JSONResponse(
            status_code=501,
            content={"error": "此项由原宿主配置 / This operation requires configuration in the original host."},
        )
