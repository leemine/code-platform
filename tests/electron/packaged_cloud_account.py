"""Exercise the installed Electron app against an isolated HTTPS account authority."""

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from urllib.parse import urljoin

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import FastAPI
from playwright.async_api import Error as PlaywrightError, async_playwright, expect
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
import psutil
import uvicorn

from gateway.auth.account_authenticator import AccountAuthenticator
from gateway.auth.accounts import AccountStore
from gateway.extensions.cloud_workspace.extension import CloudWorkspacePlugin
from gateway.services.data_sync.ui import DESKTOP_CONFIG_NAME, WINDOWS_DESKTOP_CLOUD_ORIGIN

SIGNED_OUT_LABEL = re.compile(r"^(登录|Sign in)$")


def loopback_socket():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    return listener


def write_test_certificate(root):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(hours=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
        .sign(key, hashes.SHA256())
    )
    certificate_path, key_path = root / "ca.pem", root / "tls.key"
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
    ))
    return certificate_path, key_path


def write_local_config(path, origin, certificate):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "public_origin": "http://127.0.0.1:5173",
        "cloud_origin": origin,
        "ca_file": str(certificate),
        "installation_id": "desktop-cloud-smoke",
    }), encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)
        return

    import ntsecuritycon
    import win32api
    import win32con
    import win32security

    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        token.Close()
    acl = win32security.ACL()
    acl.AddAccessAllowedAce(win32security.ACL_REVISION, ntsecuritycon.FILE_ALL_ACCESS, sid)
    win32security.SetNamedSecurityInfo(
        str(path), win32security.SE_FILE_OBJECT,
        win32security.OWNER_SECURITY_INFORMATION | win32security.DACL_SECURITY_INFORMATION
        | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
        sid, None, acl, None,
    )


async def renderer(browser, child):
    while True:
        if child.poll() is not None:
            raise RuntimeError(f"Installed Electron exited with code {child.returncode}")
        for context in browser.contexts:
            for page in context.pages:
                if page.url.startswith("http://127.0.0.1:5173/"):
                    return page
        await asyncio.sleep(0.2)


async def dismiss_model_setup(page):
    skip_model_setup = page.get_by_test_id("model-setup-guide-skip")
    if not await skip_model_setup.is_visible():
        return False
    await skip_model_setup.click()
    await expect(page.get_by_test_id("model-setup-guide")).to_be_hidden()
    print("Skipped first-run model setup using the desktop UI", flush=True)
    return True


async def click_account_trigger(page, trigger):
    try:
        await trigger.click(timeout=6000)
    except PlaywrightTimeoutError:
        if not await dismiss_model_setup(page):
            raise
        await trigger.click()


async def assert_account(page, username, password, screenshot):
    page.set_default_timeout(12_000)
    trigger = page.get_by_test_id("session-sidebar-rail").get_by_test_id("cloud-workspace-local-account-trigger")
    await expect(trigger).to_have_text(SIGNED_OUT_LABEL, timeout=90_000)
    status = await page.request.get(urljoin(page.url, "/api/v1/data-sync/status"))
    assert status.status == 200 and (await status.json())["authenticated"] is False
    print("Signed-out account button is visible", flush=True)
    await click_account_trigger(page, trigger)
    await expect(page.get_by_test_id("cloud-workspace-local-account-dialog")).to_be_visible()
    print("Local cloud account form is visible", flush=True)
    await page.get_by_test_id("cloud-workspace-local-account-username").fill(username)
    await page.get_by_test_id("cloud-workspace-local-account-password").fill(password)
    async with page.expect_response(lambda response: response.url.endswith("/api/v1/data-sync/login")) as login:
        await page.get_by_test_id("cloud-workspace-local-account-login").click()
    login_response = await login.value
    assert login_response.status == 200, f"Login returned {login_response.status}"
    print("Login returned 200", flush=True)
    await expect(trigger).to_have_text(username[:2].upper())
    await expect(trigger).to_have_attribute("aria-label", username)
    print("The sidebar avatar displays the account", flush=True)
    await click_account_trigger(page, trigger)
    await expect(page.get_by_test_id("cloud-workspace-local-account-name")).to_have_text(username)
    await page.screenshot(path=str(screenshot))
    logout_item = page.get_by_test_id("cloud-workspace-local-account-menu-logout")
    async with page.expect_response(lambda response: response.url.endswith("/api/v1/data-sync/logout")) as logout:
        try:
            await logout_item.click(timeout=6000)
        except PlaywrightTimeoutError:
            if not await dismiss_model_setup(page):
                raise
            if not await logout_item.is_visible():
                await trigger.click()
            await logout_item.click()
    assert (await logout.value).status == 200
    await expect(trigger).to_have_text(SIGNED_OUT_LABEL)
    print("Logout returned 200 and restored the signed-out account button", flush=True)


async def assert_default_windows_account(page):
    trigger = page.get_by_test_id("session-sidebar-rail").get_by_test_id("cloud-workspace-local-account-trigger")
    await expect(trigger).to_have_text(SIGNED_OUT_LABEL, timeout=90_000)
    status = await page.request.get(urljoin(page.url, "/api/v1/data-sync/status"))
    assert status.status == 200
    identity = await status.json()
    assert identity["authenticated"] is False
    assert identity["cloud_origin"] == WINDOWS_DESKTOP_CLOUD_ORIGIN
    await click_account_trigger(page, trigger)
    await expect(page.get_by_test_id("cloud-workspace-local-account-destination")).to_contain_text(
        WINDOWS_DESKTOP_CLOUD_ORIGIN
    )
    await expect(page.get_by_test_id("cloud-workspace-local-account-form")).to_be_visible()
    print("Clean Windows launch displays the default cloud account login with no local config override", flush=True)


async def smoke(executable, screenshot, root):
    username, password = "desktop-smoke", secrets.token_urlsafe(24)
    certificate, key = write_test_certificate(root)
    accounts = AccountStore(root / "authority" / "accounts.db", "packaged-desktop-smoke")
    accounts.register(username, password)
    with loopback_socket() as authority_socket:
        authority_socket.listen(16)
        origin = f"https://127.0.0.1:{authority_socket.getsockname()[1]}"
        cloud = CloudWorkspacePlugin(SimpleNamespace(
            public_origin=origin, api_prefix="/api/v1/auth/organization", authority=accounts.authority,
            registration_enabled=False,
        ))
        cloud.accounts = accounts
        cloud.authenticator = AccountAuthenticator(accounts)
        cloud.environments = SimpleNamespace(store=SimpleNamespace(revoke=lambda *_: None))
        app = FastAPI()
        for route in cloud.http_routes():
            app.add_api_route(route.path, route.endpoint, methods=list(route.methods))
        server = uvicorn.Server(uvicorn.Config(
            app, log_level="warning", access_log=False, lifespan="off",
            ssl_certfile=str(certificate), ssl_keyfile=str(key),
        ))
        serving = asyncio.create_task(server.serve(sockets=[authority_socket]))
        try:
            async with asyncio.timeout(180):
                while not server.started:
                    if serving.done():
                        await serving
                        raise RuntimeError("HTTPS account authority did not start")
                    await asyncio.sleep(0.05)
                if os.name == "nt":
                    await run_desktop(executable, screenshot, root, origin, certificate, username, password,
                                      use_windows_default=True)
                await run_desktop(executable, screenshot, root, origin, certificate, username, password)
        finally:
            server.should_exit = True
            await asyncio.wait_for(serving, 10)


async def run_desktop(executable, screenshot, root, origin, certificate, username, password, *,
                      use_windows_default=False):
    data = root / "data"
    config = data / "config" / DESKTOP_CONFIG_NAME if os.name == "nt" else root / "local-cloud.json"
    if not use_windows_default:
        write_local_config(config, origin, certificate)
    with loopback_socket() as reserved:
        cdp = reserved.getsockname()[1]
    environment = {
        **os.environ,
        "JIUWENSWARM_DATA_DIR": str(data),
        "JIUWENSWARM_CONFIG_URL": "off",
        "CODE_PLATFORM_LOCAL_SYNC_CONFIG": str(config),
        "JIUWENSWARM_ELECTRON_CDP_PORT": str(cdp),
    }
    if os.name == "nt":
        environment.pop("CODE_PLATFORM_LOCAL_SYNC_CONFIG")
    gateway_log = Path.home() / ".jiuwenswarm" / "logs" / "electron-gateway.log"
    gateway_offset = gateway_log.stat().st_size if gateway_log.exists() else 0
    with (root / "desktop.log").open("wb") as log:
        child = subprocess.Popen(
            [str(executable), f"--user-data-dir={root / 'profile'}"], cwd=root, env=environment,
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            async with asyncio.timeout(45):
                while True:
                    if child.poll() is not None:
                        raise RuntimeError(f"Installed Electron exited with code {child.returncode}")
                    try:
                        _, connection = await asyncio.open_connection("127.0.0.1", cdp)
                    except ConnectionRefusedError:
                        await asyncio.sleep(0.2)
                        continue
                    connection.close()
                    await connection.wait_closed()
                    break
            async with async_playwright() as playwright:
                browser = await playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp}", timeout=60_000)
                page = await renderer(browser, child)
                try:
                    if use_windows_default:
                        await assert_default_windows_account(page)
                    else:
                        await assert_account(page, username, password, screenshot)
                except Exception:
                    try:
                        await page.screenshot(path=str(screenshot.with_stem(screenshot.stem + "-error")), timeout=3000)
                    except PlaywrightError:
                        pass
                    raise
                finally:
                    try:
                        async with asyncio.timeout(4):
                            session = await browser.new_browser_cdp_session()
                            await session.send("Browser.close")
                    except (PlaywrightError, TimeoutError):
                        pass  # The process cleanup below also covers a stalled CDP close.
        except Exception:
            if gateway_log.exists():
                with gateway_log.open("rb") as service_log:
                    service_log.seek(gateway_offset)
                    for line in service_log:
                        if b"[ExtensionManager]" in line and b"data_sync" in line:
                            print(line.decode(errors="replace").rstrip(), flush=True)
            raise
        finally:
            try:
                child.wait(timeout=20)
            except subprocess.TimeoutExpired:
                try:
                    descendants = psutil.Process(child.pid).children(recursive=True)
                except psutil.NoSuchProcess:
                    descendants = []
                for process in reversed(descendants):
                    try:
                        process.terminate()
                    except psutil.NoSuchProcess:
                        pass
                child.kill()
                child.wait(timeout=10)
            if child.returncode:
                print((root / "desktop.log").read_text(errors="replace")[-6000:], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("screenshot", type=Path)
    args = parser.parse_args()
    if not args.executable.is_file():
        parser.error("Installed Electron executable not found")
    args.screenshot.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="workswarm-account-smoke-") as scratch:
        asyncio.run(smoke(args.executable.resolve(), args.screenshot.resolve(), Path(scratch)))


if __name__ == "__main__":
    main()
