"""Account store extracted from codeswarm account_auth.py (76b79fdc0).

Preserves the scrypt password and revocable session-digest formats. OAuth/model
credentials remain in gateway.auth; this optional backend owns platform accounts.
"""
from contextlib import contextmanager
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import time

class AccountError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.status = code, status


class AccountStore:
    """One durable identity per registered account; only session digests persist."""

    def __init__(self, path, authority="code-platform", ttl=86400):
        candidate = Path(path)
        if candidate.is_symlink():
            raise PermissionError("invalid account database")
        self.path = candidate.absolute()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.authority, self.ttl = authority, ttl
        fd = os.open(
            self.path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600
        )
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or (
                os.name == "posix"
                and (info.st_uid != os.getuid() or info.st_mode & 0o077)
            ):
                raise PermissionError("account database must be owner-only")
        finally:
            os.close(fd)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS accounts (
                    user_id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS registration_receipts (
                    operation_id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES accounts);
                CREATE TABLE IF NOT EXISTS login_sessions (
                    digest TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES accounts,
                    expires REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
            """)
            db.execute(
                "INSERT OR IGNORE INTO settings VALUES ('authority', ?)", (authority,)
            )
            if (
                db.execute(
                    "SELECT value FROM settings WHERE key='authority'"
                ).fetchone()[0]
                != authority
            ):
                raise PermissionError("account authority changed")
        self._dummy = self.password_hash(secrets.token_urlsafe(24))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def password_hash(password, salt=None):
        salt = salt or secrets.token_hex(16)
        result = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt),
            n=32768,
            r=8,
            p=3,
            maxmem=128 * 1024 * 1024,
        )
        return f"scrypt$32768$8$3${salt}${result.hex()}"

    @classmethod
    def check_password(cls, password, encoded):
        salt = encoded.split("$")[-2]
        return hmac.compare_digest(cls.password_hash(password, salt), encoded)

    @staticmethod
    def validate(username, password):
        if not isinstance(username, str) or not re.fullmatch(
            r"[a-zA-Z0-9][a-zA-Z0-9_.-]{2,31}", username
        ):
            raise AccountError(
                "INVALID_USERNAME",
                "username must be 3-32 letters, digits, dots, underscores or hyphens",
            )
        if not isinstance(password, str) or not 8 <= len(password) <= 128:
            raise AccountError("INVALID_PASSWORD", "password must be 8-128 characters")
        return username.lower()

    def register(self, username, password, *, operation_id=None):
        username = self.validate(username, password)
        if operation_id is not None and not re.fullmatch(r"[0-9a-f]{32}", operation_id):
            raise AccountError("INVALID_OPERATION", "invalid registration operation")
        encoded = self.password_hash(password)
        try:
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                if operation_id:
                    previous = db.execute(
                        "SELECT a.* FROM registration_receipts r JOIN accounts a USING(user_id) "
                        "WHERE r.operation_id=?", (operation_id,),
                    ).fetchone()
                    if previous:
                        if previous["username"] != username or not self.check_password(password, previous["password_hash"]):
                            raise AccountError("REGISTRATION_MISMATCH", "registration operation differs", 409)
                        return {"user_id": previous["user_id"], "username": username, "authority": self.authority}
                user_id = "u_" + secrets.token_hex(16)
                db.execute("INSERT INTO accounts VALUES (?,?,?,?)", (user_id, username, encoded, time.time()))
                if operation_id:
                    db.execute("INSERT INTO registration_receipts VALUES (?,?)", (operation_id, user_id))
        except sqlite3.IntegrityError as exc:
            raise AccountError("USERNAME_EXISTS", "username already registered", 409) from exc
        return {"user_id": user_id, "username": username, "authority": self.authority}

    def login(self, username, password):
        username = self.validate(username, password)
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM accounts WHERE username=?", (username,)
            ).fetchone()
        valid = self.check_password(
            password, row["password_hash"] if row else self._dummy
        )
        if not valid or row is None:
            raise AccountError(
                "INVALID_CREDENTIALS", "invalid username or password", 401
            )
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute(
                "INSERT INTO login_sessions(digest,user_id,expires) VALUES (?,?,?)",
                (
                    hashlib.sha256(token.encode()).hexdigest(),
                    row["user_id"],
                    time.time() + self.ttl,
                ),
            )
        return {**self.session(token), "token": token}

    def session(self, token):
        if not isinstance(token, str) or not 32 <= len(token) <= 512:
            raise PermissionError("login required")
        with self.connect() as db:
            row = db.execute(
                "SELECT a.user_id,a.username FROM accounts a JOIN login_sessions s USING(user_id) WHERE s.digest=? AND s.revoked=0 AND s.expires>?",
                (hashlib.sha256(token.encode()).hexdigest(), time.time()),
            ).fetchone()
        if row is None:
            raise PermissionError("login session ended or expired")
        return {
            "user_id": row["user_id"],
            "username": row["username"],
            "authority": self.authority,
        }

    def logout(self, token):
        # Idempotent; account and other device sessions remain intact.
        with self.connect() as db:
            db.execute(
                "UPDATE login_sessions SET revoked=1 WHERE digest=?",
                (hashlib.sha256(token.encode()).hexdigest(),),
            )

    def members(self, token):
        self.session(token)
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT user_id,username FROM accounts ORDER BY username"
                )
            ]




def credential(headers):
    from http.cookies import SimpleCookie, CookieError
    lowered = {str(k).lower(): str(v) for k, v in headers.items()}
    value = lowered.get("authorization", "")
    if value.startswith("Bearer "):
        return value[7:]
    cookie = SimpleCookie()
    try:
        cookie.load(lowered.get("cookie", ""))
    except CookieError:
        return ""
    item = cookie.get("jiuwenswarm_organization")
    return item.value if item else ""


def private_config(path):
    import json
    path = Path(path)
    if path.is_symlink():
        raise PermissionError("private configuration cannot be a symlink")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or (os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o077)):
        raise PermissionError("private configuration must be owner-only")
    return json.loads(path.read_text())
