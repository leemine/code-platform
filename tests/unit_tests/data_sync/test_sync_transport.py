"""Real loopback WebChannel, AccountStore, ProjectStore and SQLite replicas."""
import asyncio
import json
import os
import socket
import sys

import pytest
import uvicorn
from websockets.exceptions import ConnectionClosedError

from gateway.auth.accounts import AccountStore
from gateway.auth.account_authenticator import AccountAuthenticator
from gateway.channel_manager.base import RobotMessageRouter
from gateway.channel_manager.web.web_channel_app import build_web_channel_app
from gateway.channel_manager.web.web_connect import WebChannel, WebChannelConfig
from gateway.extensions.auth.credential_authenticator import AuthContext
from gateway.extensions.data_sync.extension import DataSyncPlugin
from gateway.services.data_sync.store import DirectoryStore
from jiuwenswarm.data_sync.connector import DirectoryConnector, DirectoryReplica, register_source
from jiuwenswarm.data_sync.contract import SyncError
from jiuwenswarm.data_sync.transport import DirectoryRPC


@pytest.mark.asyncio
async def test_real_websocket_source_publish_receive_revoke_and_logout(tmp_path, monkeypatch):
    from jiuwenswarm.server.runtime.session import project_store
    monkeypatch.setattr(project_store, "get_agent_root_dir", lambda: tmp_path / "original-agent")
    original = project_store.create_project("Original empty project", str(tmp_path / "original-directory"), "code")
    original_bytes = (tmp_path / "original-agent/projects.json").read_bytes()
    accounts = AccountStore(tmp_path / "account/authority.db", "isolated-authority")
    accounts.register("wire-user", "isolated-wire-test-password")
    login = accounts.login("wire-user", "isolated-wire-test-password")
    auth = AccountAuthenticator(accounts)
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    async def authenticate(**values):
        return await auth.authenticate(AuthContext(channel_type="web", headers=dict(values["headers"])))
    channel.set_handshake_auth(authenticate)
    DataSyncPlugin(DirectoryStore(tmp_path / "broker"), lambda identity: "original-cloud-binding").bind_web_channel(channel, None)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(16)
    url = f"ws://127.0.0.1:{sock.getsockname()[1]}/ws"
    server = uvicorn.Server(uvicorn.Config(build_web_channel_app(channel), log_level="error", lifespan="off"))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(30):
            while not server.started:
                if task.done():
                    await task
                await asyncio.sleep(0.01)
            async with DirectoryRPC(url, login["token"], timeout=5) as writer_rpc, DirectoryRPC(url, login["token"], timeout=5) as reader_rpc:
                source = await register_source(writer_rpc.request, "original-installation", "a" * 64)
                reader_source = await register_source(reader_rpc.request, "consumer-installation", "b" * 64)
                writer = DirectoryConnector(writer_rpc.request, source, "a" * 64, DirectoryReplica(tmp_path / "writer", source["id"]))
                reader = DirectoryConnector(reader_rpc.request, reader_source, "b" * 64, DirectoryReplica(tmp_path / "reader", reader_source["id"]))
                await writer.publish([original.project_id])
                assert [row["project"]["name"] for row in await reader.pull()] == ["Original empty project"]
                assert reader.replica.get("ack") is None and reader.replica.get("status")["state"] == "current"
                child_env = {**os.environ, "CODE_PLATFORM_SYNC_ACCOUNT_TOKEN": login["token"],
                             "CODE_PLATFORM_SYNC_SOURCE_PROOF": "c" * 64,
                             "JIUWENSWARM_DATA_DIR": str(tmp_path / "cli-data")}
                child = await asyncio.create_subprocess_exec(
                    sys.executable, "-P", "-m", "jiuwenswarm.data_sync", "--url", url,
                    "--installation-id", "cli-reader", "--receive-only", env=child_env,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stdout, stderr = await asyncio.wait_for(child.communicate(), 10)
                    assert child.returncode == 0, stderr.decode()
                    assert json.loads(stdout.decode().splitlines()[-1])["projects"] == 1
                    assert login["token"].encode() not in stdout + stderr
                finally:
                    if child.returncode is None:
                        child.kill()
                        await child.wait()
                await writer.publish([])
                assert await reader.pull() == []
                await writer_rpc.request("data_sync.source.revoke", {"source_id": source["id"]})
                with pytest.raises(SyncError, match="SOURCE_UNAUTHORIZED"):
                    await writer.publish([original.project_id])
                accounts.logout(login["token"])
                with pytest.raises(ConnectionClosedError) as denied:
                    await reader.pull()
                assert denied.value.rcvd.code == 1008
                assert reader.replica.get("status")["state"] == "stale"
            assert (tmp_path / "original-agent/projects.json").read_bytes() == original_bytes
            assert not (tmp_path / "original-directory").exists()
    finally:
        server.should_exit = True
        await channel.stop()
        await asyncio.wait_for(task, 5)
        sock.close()
        project_store.invalidate_cache()


def test_transport_never_sends_secrets_to_plaintext_remote_or_url_selectors():
    for url in ["ws://cloud.example/ws", "wss://user:password@cloud.example/ws", "wss://cloud.example/ws?user_id=forged"]:
        with pytest.raises(ValueError):
            DirectoryRPC(url, "x" * 40)


@pytest.mark.asyncio
async def test_redirect_cannot_forward_the_account_token():
    reached = []
    async def target(reader, writer):
        reached.append(True)
        writer.close()
        await writer.wait_closed()
    destination = await asyncio.start_server(target, "127.0.0.1", 0)
    port = destination.sockets[0].getsockname()[1]
    async def redirect(reader, writer):
        try:
            await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 3)
            writer.write((f"HTTP/1.1 302 Found\r\nLocation: ws://127.0.0.1:{port}/ws\r\nContent-Length: 0\r\nConnection: close\r\n\r\n").encode())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
    origin = await asyncio.start_server(redirect, "127.0.0.1", 0)
    try:
        url = f"ws://127.0.0.1:{origin.sockets[0].getsockname()[1]}/ws"
        with pytest.raises(SyncError, match="SYNC_REDIRECT_DENIED"):
            async with DirectoryRPC(url, "x" * 40, timeout=3):
                pass
        assert reached == []
    finally:
        origin.close()
        destination.close()
        await origin.wait_closed()
        await destination.wait_closed()
