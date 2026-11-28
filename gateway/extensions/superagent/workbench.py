"""WorkSwarm transport for the retained SuperAgent Workbench."""

from __future__ import annotations

from copy import deepcopy
from functools import cached_property
import json
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from gateway.extensions.sdk.application_plugin import HTTPRouteContribution


PROJECT = "pj-order"
ASSETS = Path(__file__).parent / "frontend" / "dist"
DEMO_ID = "poc-interest-allocation"


class CatalogReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assetId: str = Field(max_length=160)
    revisionId: str = Field(max_length=160)
    sectionId: str = Field(max_length=160)


class WorkbenchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    projectId: str
    text: str = Field(min_length=1, max_length=12000)
    threadId: UUID | None = None
    asset: CatalogReference | None = None
    useCaseId: str | None = Field(default=None, max_length=160)


class Ruling(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    threadId: UUID
    ticketId: str = Field(min_length=1, max_length=160)
    attentionId: str = Field(min_length=1, max_length=160)
    choice: str


class Catalog:
    def __init__(self):
        snapshot = json.loads((ASSETS / "business-catalog.json").read_text())
        fixtures = json.loads((ASSETS / "workbench-fixtures.json").read_text())
        source = {"label": "Workbench PoC 测试资料", "ref": "workbench/fixtures.js"}
        rule = fixtures["asset"]
        self.assets = {
            item["id"]: dict(item, demo=False, simulation=snapshot["mode"] == "simulation")
            for item in snapshot["assets"]
        }
        self.assets[DEMO_ID] = {
            "id": DEMO_ID, "name": rule["title"], "projectId": PROJECT,
            "description": "用于验证口径冲突、人工裁定及版本引用。", "demo": True,
            "revisions": [{"id": rule["revisionId"], "source": source, "sections": [{
                "id": rule["sectionId"], "title": "还款尾差归属", "body": rule["body"],
            }]}],
        }
        self.cases = {item["id"]: item for item in snapshot["useCases"]}
        demo_case = fixtures["useCase"]
        self.cases[demo_case["id"]] = dict(demo_case, assetId=DEMO_ID, source=source)
        self.experts = json.loads((ASSETS / "experts.json").read_text())

    def directory(self):
        assets = deepcopy(list(self.assets.values()))
        for asset in assets:
            asset["revisions"].sort(key=lambda item: (item.get("publishedAt", ""), item["id"]), reverse=True)
            for revision in asset["revisions"]:
                for section in revision["sections"]:
                    section.pop("body")
        return {
            "assets": assets,
            "useCases": [{key: value for key, value in item.items() if key != "body"}
                         for item in self.cases.values()],
            "experts": [{**{key: value for key, value in item.items() if key not in {"procedure", "key"}},
                         "skill": item["title"]} for item in self.experts],
        }

    def section(self, reference):
        asset = self.assets.get(reference["assetId"])
        revision = next((item for item in (asset or {}).get("revisions", [])
                         if item["id"] == reference["revisionId"]), None)
        section = next((item for item in (revision or {}).get("sections", [])
                        if item["id"] == reference["sectionId"]), None)
        if section is None:
            raise HTTPException(404, detail="ASSET_VERSION_NOT_FOUND")
        return {**reference, "assetName": asset["name"], "title": section["title"],
                "body": section["body"], "source": revision["source"]}

    def use_case(self, item_id):
        item = self.cases.get(item_id)
        if not item:
            raise HTTPException(404, detail="USE_CASE_NOT_FOUND")
        return item

    def evidence(self, data: WorkbenchInput):
        section = self.section(data.asset.model_dump()) if data.asset else None
        case = self.use_case(data.useCaseId) if data.useCaseId else None
        if not section and not case:
            return {}
        if section and case and case.get("assetId") not in {None, section["assetId"]}:
            raise HTTPException(400, detail="USE_CASE_ASSET_MISMATCH")
        citation = {key: value for key, value in (section or {}).items() if key != "body"}
        if case:
            citation["useCaseId"] = case["id"]
        content = json.dumps({"asset_version": section, "use_case": case}, ensure_ascii=False)
        return {"evidence": {"citation": citation, "content": content}}


class WorkbenchAPI:
    def __init__(self, tickets):
        self.tickets = tickets

    @cached_property
    def catalog(self):
        return Catalog()

    def routes(self):
        return (
            HTTPRouteContribution("/workbench/room", self.room),
            HTTPRouteContribution("/workbench/messages", self.message, ("POST",)),
            HTTPRouteContribution("/workbench/decisions", self.ruling, ("POST",)),
        )

    def snapshot(self, entry, owner):
        ticket = entry.get("ticket") or {}
        report = ticket.get("report") or {}
        attention = ticket.get("attention")
        if attention and report.get("at"):
            ticket["attention"] = {**attention, "at": report["at"]}
        approval = self.tickets.plugin.service.interaction(ticket.get("id"), owner)
        messages = [dict(message, kind="human", by="human") for message in entry["messages"]]
        messages.sort(key=lambda message: message["at"])
        ruling_open = bool(attention and not approval and report.get("state") == "blocked"
                           and (entry.get("citation") or {}).get("assetId")
                           and not entry.get("ruling") and not ticket.get("ended"))
        status = entry["status"]
        if ticket.get("uncertain") or status == "uncertain":
            phase = "failed"
        elif ticket.get("ended", {}).get("by") == "human":
            phase = "ended"
        elif ruling_open:
            phase = "awaiting_decision"
        elif approval or ticket.get("stage", {}).get("stage") == "working":
            phase = "working"
        else:
            phase = {"ready": "ready", "blocked": "failed", "failed": "failed"}.get(
                report.get("state"), "ended" if status == "ignore" else "routing",
            )
        artifact = None
        reports = entry.get("reports", [])
        if not reports and report.get("summary") and report.get("at") and report.get("state") != "progress":
            reports = [{"id": f"{ticket['id']}:{report['at']}", **report}]
        for index, item in enumerate(reports):
            text = item["summary"]
            if index == len(reports) - 1:
                url = f"/workbench/#{entry['id']}"
                artifact = {"url": url, "text": text, "citation": entry.get("citation")}
                text = f"{text}\n{url}"
            messages.append({"id": item["id"], "text": text, "at": item["at"], "kind": "reply", "by": "小需"})
        if status == "ignore" and entry.get("route"):
            messages.append({"id": f"{entry['id']}:ignore", "text": entry["route"]["reason"],
                             "at": messages[-1]["at"], "kind": "reply", "by": "小需"})
        messages = [messages[0], *sorted(messages[1:], key=lambda message: message["at"])]
        return {
            "id": entry["id"], "phase": phase, "messages": messages,
            "ticket": ticket or None, "sessionId": ticket.get("session_id"),
            "uncertain": ticket.get("uncertain", False), "pendingApproval": bool(approval),
            "stopped": ticket.get("ended", {}).get("by") == "human",
            "reads": [entry["citation"]] if entry.get("citation") else [],
            "artifact": artifact, "citation": entry.get("citation"),
            "businessDecision": ruling_open,
        }

    async def room(self, request: Request):
        owner = await self.tickets._owner(request)
        query = request.query_params
        view = query.get("view")
        if view == "catalog":
            return self.catalog.directory()
        if view == "asset":
            return self.catalog.section({"assetId": query.get("asset"), "revisionId": query.get("revision"),
                                         "sectionId": query.get("section")})
        if view == "use-case":
            return self.catalog.use_case(query.get("case"))
        if query.get("project", PROJECT) != PROJECT:
            return []
        topic = query.get("id")
        entries = await self.tickets._call("workbench_topics", owner, topic_id=topic) if topic \
            else await self.tickets._call("workbench_topics", owner)
        if topic and not entries:
            raise HTTPException(404, detail="NOT_FOUND")
        items = [self.snapshot(item, owner) for item in entries]
        return items[0] if topic else items

    async def message(self, request: Request):
        owner = await self.tickets._owner(request)
        data = await self.tickets._body(request, WorkbenchInput)
        if data.projectId != PROJECT:
            raise HTTPException(400, detail="PROJECT_NOT_ALLOWED")
        topic = str(data.threadId or data.id)
        return await self.tickets._call("workbench_message", owner, operation_id=str(data.id),
                                        topic_id=topic, is_follow=data.threadId is not None,
                                        text=data.text, **self.catalog.evidence(data))

    async def ruling(self, request: Request):
        owner = await self.tickets._owner(request)
        data = await self.tickets._body(request, Ruling)
        choices = {"published": "采纳已发布规则", "exception": "保留项目例外"}
        if data.choice not in choices:
            raise HTTPException(400, detail="INVALID_RULING")
        return await self.tickets._call(
            "workbench_ruling", owner, operation_id=str(data.id), topic_id=str(data.threadId),
            ticket_id=data.ticketId, attention_id=data.attentionId,
            choice=data.choice, text=f"用户人工裁定：{choices[data.choice]}。沿用本话题的证据继续完成任务。",
        )
