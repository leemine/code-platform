"""Register the opt-in SuperAgent application with the existing Gateway."""

from __future__ import annotations

from pathlib import Path
import shutil

from filelock import FileLock

from gateway.common.config import get_config
from gateway.common.paths import get_root_dir
from gateway.common.work_mode import is_default_project_id
from gateway.extensions.sdk.application_plugin import (
    ApplicationPluginExtension,
    FrontendContribution,
)
from gateway.extensions.superagent.api import TicketAPI
from gateway.extensions.superagent.platform_executor import PlatformExecutor
from gateway.extensions.superagent.router_adapter import RouterAdapter
from gateway.extensions.superagent.service import TicketService
from gateway.extensions.superagent.sidecar import Sidecar


class SuperAgentPlugin(ApplicationPluginExtension):
    plugin_id = "superagent"

    def __init__(self, registry):
        self.registry = registry
        self.settings = {}
        self.executor = None
        self.service = None
        self.channel = None
        self.api = None
        self.lease = None

    async def initialize(self, config):
        settings = config.config.get("superagent")
        if settings is None:
            settings = get_config().get("superagent")
        self.settings = settings or {}
        if not self.is_enabled():
            return
        if is_default_project_id(self.settings.get("project_id")):
            raise ValueError("superagent.project_id must identify a registered Code project")
        members = self.settings.get("members")
        if not isinstance(members, list) or not members or not all(
            isinstance(member, str) and 0 < len(member) <= 160 and member.strip() == member
            for member in members
        ):
            raise ValueError("superagent.members must list authenticated project participants")
        self.api = TicketAPI(self, self.settings.get("public_origin", ""))

    def is_enabled(self) -> bool:
        return self.settings.get("enabled") is True

    def account_authority(self):
        cloud = self.registry.get_application_plugin("cloud_workspace")
        return getattr(cloud, "authenticator", None)

    async def configure_services(self, services):
        if not self.is_enabled():
            return
        self.executor = PlatformExecutor(
            services.require_agent_client(), self.settings["project_id"], self.settings["model_selection"],
            self.settings.get("execution_provider", "opencode-direct"),
        )
        root = get_root_dir() / "superagent"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        node = shutil.which(self.settings.get("node_executable", "node"))
        entry = self._get_extension_dir() / "orchestrator" / "dist" / "main.mjs"
        if not node or not entry.is_file():
            raise RuntimeError("Install the built SuperAgent plugin with Node.js 22.19+")
        self.lease = FileLock(root / "gateway.lock", timeout=0)
        self.lease.acquire()
        try:
            sidecar = Sidecar(entry, root / "tickets.sqlite", self.settings["members"], node)
            router = RouterAdapter(root / "router", self.settings["router_model"])
            self.service = TicketService(sidecar, router, self.executor)
            self.service.start()
        except BaseException:
            self.lease.release()
            self.lease = None
            raise

    def bind_web_channel(self, channel, services):
        del services
        self.channel = channel

    def http_routes(self):
        return self.api.routes() if self.api is not None else ()

    def frontend_contributions(self):
        pages = (
            FrontendContribution(id="superagent-panel", nav_key="app:superagent", title="SuperAgent",
                                 render_mode="iframe", entrypoint="panel.html", position=180),
            FrontendContribution(id="superagent-workbench", nav_key="app:superagent-workbench", title="Workbench",
                                 render_mode="iframe", entrypoint="workbench.html", position=181),
        )
        if self.settings.get("acceptance_page") is True:
            pages += (FrontendContribution(
                id="superagent-tickets", nav_key="app:superagent-acceptance", title="SuperAgent 验收",
                render_mode="iframe", entrypoint="index.html", position=182,
            ),)
        return pages

    async def shutdown(self):
        try:
            if self.service is not None:
                await self.service.close()
        finally:
            if self.lease is not None:
                self.lease.release()
            self.service = self.executor = self.lease = None


async def register_extensions(registry):
    plugin = SuperAgentPlugin(registry)
    registry.register_application_plugin(plugin)
    return [plugin]
