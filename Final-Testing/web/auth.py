"""
User accounts and sign-in sessions for the web front end.

Uses only the Python standard library: accounts and sessions are kept in
a small SQLite file, and passwords are stored as salted PBKDF2-SHA256
hashes (never in plain text).

Accounts can also be managed from the command line, which is useful when
self-service sign-up is switched off (RAG_ALLOW_SIGNUP=0):

    python web/auth.py add <username>       # prompts for a password
    python web/auth.py passwd <username>    # reset a password
    python web/auth.py remove <username>
    python web/auth.py list
"""

import contextlib
import hashlib
import hmac
import re
import secrets
import sqlite3
import threading
import time

PBKDF2_ITERATIONS = 310_000
SESSION_SECONDS = 7 * 24 * 3600
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,32}$")
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 256
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 60


class AuthError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def hash_password(password, iterations=PBKDF2_ITERATIONS):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    try:
        algorithm, iterations, salt_hex, digest_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


# Used to spend the same time on unknown usernames as on wrong passwords,
# so response times don't reveal which usernames exist.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def _token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def validate_username(username):
    if not USERNAME_RE.match(username or ""):
        raise AuthError(
            "Usernames must be 3–32 characters: letters, numbers, dots, "
            "hyphens or underscores."
        )


def validate_password(password):
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Passwords must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise AuthError(f"Passwords must be at most {MAX_PASSWORD_LENGTH} characters.")


class UserStore:
    def __init__(self, path):
        self.path = str(path)
        self._failures = {}
        self._failures_lock = threading.Lock()

        with self._db() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at REAL NOT NULL
                );
                """
            )

    @contextlib.contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute("PRAGMA foreign_keys = ON")
            with db:
                yield db
        finally:
            db.close()

    # ---------- accounts ----------

    def create_user(self, username, password):
        username = (username or "").strip()
        validate_username(username)
        validate_password(password)
        try:
            with self._db() as db:
                cursor = db.execute(
                    "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                    (username, hash_password(password), time.time()),
                )
                return cursor.lastrowid
        except sqlite3.IntegrityError:
            raise AuthError("That username is already taken.", 409)

    def set_password(self, username, password):
        validate_password(password)
        with self._db() as db:
            updated = db.execute(
                "UPDATE users SET password_hash = ? WHERE username = ?",
                (hash_password(password), username),
            ).rowcount
            if not updated:
                raise AuthError("No such user.", 404)
            # Sign the user out everywhere after a password change.
            db.execute(
                "DELETE FROM sessions WHERE user_id = (SELECT id FROM users WHERE username = ?)",
                (username,),
            )

    def remove_user(self, username):
        with self._db() as db:
            if not db.execute("DELETE FROM users WHERE username = ?", (username,)).rowcount:
                raise AuthError("No such user.", 404)

    def list_users(self):
        with self._db() as db:
            return [row[0] for row in db.execute("SELECT username FROM users ORDER BY username")]

    def count_users(self):
        with self._db() as db:
            return db.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    # ---------- sign-in ----------

    def _check_lockout(self, key):
        with self._failures_lock:
            count, locked_until = self._failures.get(key, (0, 0))
            remaining = locked_until - time.time()
            if remaining > 0:
                raise AuthError(
                    f"Too many failed attempts. Try again in {int(remaining) + 1} seconds.", 429
                )

    def _record_failure(self, key):
        with self._failures_lock:
            count, _ = self._failures.get(key, (0, 0))
            count += 1
            if count >= MAX_FAILED_ATTEMPTS:
                self._failures[key] = (0, time.time() + LOCKOUT_SECONDS)
            else:
                self._failures[key] = (count, 0)

    def authenticate(self, username, password):
        """Return (user_id, username) or raise AuthError."""
        username = (username or "").strip()
        key = username.lower()
        self._check_lockout(key)

        with self._db() as db:
            row = db.execute(
                "SELECT id, username, password_hash FROM users WHERE username = ?",
                (username,),
            ).fetchone()

        if row is None:
            verify_password(password or "", _DUMMY_HASH)
            valid = False
        else:
            valid = verify_password(password or "", row[2])

        if not valid:
            self._record_failure(key)
            raise AuthError("Incorrect username or password.", 401)

        with self._failures_lock:
            self._failures.pop(key, None)
        return row[0], row[1]

    # ---------- sessions ----------

    def create_session(self, user_id):
        token = secrets.token_urlsafe(32)
        with self._db() as db:
            db.execute("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))
            db.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (_token_hash(token), user_id, time.time() + SESSION_SECONDS),
            )
        return token

    def user_for_session(self, token):
        """Return the username for a valid session token, else None."""
        if not token:
            return None
        with self._db() as db:
            row = db.execute(
                "SELECT u.username FROM sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token_hash = ? AND s.expires_at > ?",
                (_token_hash(token), time.time()),
            ).fetchone()
        return row[0] if row else None

    def delete_session(self, token):
        if token:
            with self._db() as db:
                db.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


# ============================================================
# COMMAND LINE
# ============================================================

if __name__ == "__main__":
    import getpass
    import os
    import sys
    from pathlib import Path

    db_path = os.environ.get("RAG_USERS_DB", str(Path(__file__).resolve().parent / "users.db"))
    store = UserStore(db_path)
    usage = "Usage: python web/auth.py add|passwd|remove <username>  |  python web/auth.py list"

    if len(sys.argv) < 2:
        sys.exit(usage)

    command = sys.argv[1]
    try:
        if command == "list":
            users = store.list_users()
            print("\n".join(users) if users else "(no users)")
        elif command in ("add", "passwd", "remove") and len(sys.argv) == 3:
            name = sys.argv[2]
            if command == "remove":
                store.remove_user(name)
                print(f"Removed {name}.")
            else:
                password = getpass.getpass("Password: ")
                if password != getpass.getpass("Repeat password: "):
                    sys.exit("Passwords do not match.")
                if command == "add":
                    store.create_user(name, password)
                    print(f"Created {name}.")
                else:
                    store.set_password(name, password)
                    print(f"Password changed for {name}; existing sessions signed out.")
        else:
            sys.exit(usage)
    except AuthError as exc:
        sys.exit(exc.message)
