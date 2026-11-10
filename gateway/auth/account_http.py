"""Standalone account authority HTTP assembly, independent of applications."""
from __future__ import annotations
import argparse
import asyncio
import ssl
import time
from collections import OrderedDict, deque
from aiohttp import web

def register_account_routes(app, store):
    """Private HTTPS authority API; browser credentials are handled by Gateway."""
    from gateway.auth.accounts import AccountError, credential
    attempts = OrderedDict()
    password_slots = asyncio.Semaphore(2)

    async def account_rpc(request):
        method = request.match_info["method"]
        try:
            # Sharing bundles have a larger allowance; password endpoints do
            # not inherit it. Applies to chunked bodies as well.
            request = request.clone(client_max_size=4096)
            body = await request.json()
            if not isinstance(body, dict):
                raise AccountError("BAD_REQUEST", "object required")
            if method in {"register", "login"}:
                # A bounded per-address bucket limits password hashing work.
                key = request.remote or "unknown"
                now = time.monotonic()
                bucket = attempts.setdefault(key, deque())
                attempts.move_to_end(key)
                while bucket and bucket[0] < now - 60:
                    bucket.popleft()
                if len(bucket) >= 30:
                    raise AccountError("RATE_LIMITED", "try again later", 429)
                bucket.append(now)
                while len(attempts) > 1024:
                    attempts.popitem(last=False)
                async with password_slots:
                    if method == "register":
                        result = await asyncio.to_thread(store.register, body.get("username"), body.get("password"), operation_id=body.get("operation_id"))
                    else:
                        result = await asyncio.to_thread(store.login, body.get("username"), body.get("password"))
            elif method == "session":
                result = await asyncio.to_thread(store.session, credential(request.headers))
            elif method == "logout":
                await asyncio.to_thread(store.logout, credential(request.headers))
                result = {"authenticated": False}
            elif method == "members":
                result = {"users": await asyncio.to_thread(store.members, credential(request.headers))}
            else:
                raise AccountError("NOT_FOUND", "unknown account operation", 404)
            return web.json_response(result, headers={"Cache-Control": "no-store"})
        except PermissionError:
            return web.json_response({"error": "login required"}, status=401)
        except AccountError as exc:
            return web.json_response({"error": str(exc), "code": exc.code}, status=exc.status)
        except (ValueError, TypeError):
            return web.json_response({"error": "invalid request"}, status=400)

    app.router.add_post("/accounts/{method}", account_rpc)


def create_app(store):
    app = web.Application(client_max_size=4096)
    register_account_routes(app, store)
    app.router.add_get('/health', lambda _: web.json_response({'ok': True}))
    return app

def main():
    from .accounts import AccountStore, private_config
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account-auth-file', required=True)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=19580)
    parser.add_argument('--cert')
    parser.add_argument('--key')
    args = parser.parse_args()
    if bool(args.cert) != bool(args.key) or (args.host not in {'127.0.0.1', '::1'} and not args.cert):
        parser.error('non-loopback authority requires TLS certificate and key')
    context = None
    if args.cert:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(args.cert, args.key)
    cfg = private_config(args.account_auth_file)
    store = AccountStore(cfg['database'], cfg['authority'], cfg.get('session_ttl', 86400))
    web.run_app(create_app(store), host=args.host, port=args.port, ssl_context=context)

if __name__ == '__main__':
    main()
