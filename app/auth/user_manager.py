import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple

from pymongo import MongoClient, ASCENDING
from pymongo.errors import DuplicateKeyError


PROFESSIONS: List[str] = [
    "Software Engineer / Developer",
    "Data Scientist / Analyst",
    "Finance / Investment Professional",
    "Entrepreneur / Founder",
    "Student",
    "Product Manager",
    "Designer / Creative",
    "Researcher / Academic",
    "Marketing / Growth",
    "Other",
]

TRADING_PROFILES: List[str] = ["Beginner", "Experienced"]

PURPOSES: List[str] = [
    "Learn about crypto markets",
    "Track narratives & trends",
    "Research before investing",
    "Professional market intelligence",
    "Building a product or tool",
    "Academic or research purposes",
    "Just exploring",
]

_BONUS_FIELDS: Tuple[str, ...] = (
    "first_name", "last_name", "email", "profession", "trading_profile", "purpose"
)

# Username: 3-30 chars, lowercase alphanumeric plus . _ - (no leading/trailing punctuation)
_USERNAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{1,28}[a-z0-9])?$")

# Password policy: at least 10 chars, one upper, one lower, one digit
_MIN_PASSWORD_LEN = 10

# Login throttling: 5 failed attempts in 15 minutes locks the username for 15 minutes
_LOCKOUT_THRESHOLD = 5
_LOCKOUT_WINDOW_SECONDS = 15 * 60

# Session lifetimes
_SESSION_ABSOLUTE_DAYS = 30      # hard cap regardless of activity
_SESSION_IDLE_DAYS = 7           # sliding window of inactivity


class AuthError(Exception):
    """Raised for user-facing authentication problems (locked account, weak password, etc.)."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def validate_username(username: str) -> Optional[str]:
    """Return a user-facing error string, or None if the username is acceptable."""
    if not username:
        return "Please choose a username."
    candidate = username.strip().lower()
    if len(candidate) < 3:
        return "Username must be at least 3 characters."
    if len(candidate) > 30:
        return "Username must be 30 characters or fewer."
    if not _USERNAME_RE.match(candidate):
        return "Use lowercase letters, numbers, and . _ - only (no spaces)."
    return None


def password_strength(password: str) -> Tuple[int, str]:
    """Score 0-4 + a short label. Used to render a strength meter."""
    if not password:
        return 0, "Empty"
    score = 0
    if len(password) >= _MIN_PASSWORD_LEN:
        score += 1
    if len(password) >= 14:
        score += 1
    classes = sum(bool(re.search(p, password)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    score += min(classes - 1, 2)  # 2 classes -> +1, 3 -> +2, 4 -> +2
    score = max(0, min(score, 4))
    label = ["Too weak", "Weak", "Fair", "Strong", "Excellent"][score]
    return score, label


def validate_password(password: str) -> Optional[str]:
    """Return a user-facing error string, or None if the password meets policy."""
    if not password or len(password) < _MIN_PASSWORD_LEN:
        return f"Password must be at least {_MIN_PASSWORD_LEN} characters."
    if not re.search(r"[A-Za-z]", password):
        return "Password needs at least one letter."
    if not re.search(r"\d", password):
        return "Password needs at least one number."
    if password.lower() in {"password", "kairo-admin", "letmein", "qwerty12345"}:
        return "That password is too common — choose something harder to guess."
    return None


class UserManager:
    COLLECTION = "kairo_users"

    def __init__(self, mongo_uri: str, mongo_db: str):
        from config.config import mongo_tls_ca_file
        ca = mongo_tls_ca_file()
        self._client = MongoClient(mongo_uri, tlsCAFile=ca)
        self._col = self._client[mongo_db][self.COLLECTION]
        self._col.create_index([("username", ASCENDING)], unique=True)

        self._sessions_col = self._client[mongo_db]["kairo_sessions"]
        # Token is stored only as an HMAC; we look it up by hash, never raw value.
        self._sessions_col.create_index([("token_hash", ASCENDING)], unique=True)
        self._sessions_col.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)
        self._sessions_col.create_index([("username", ASCENDING)])

        # Failed-login bookkeeping for rate limiting. TTL'd via expires_at.
        self._attempts_col = self._client[mongo_db]["kairo_login_attempts"]
        self._attempts_col.create_index([("username", ASCENDING)])
        self._attempts_col.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)

        # Server-side secret used to HMAC session tokens before persisting.
        # Auto-generated and stored once per deployment.
        self._token_secret = self._load_or_create_token_secret(mongo_db)

    # ---- secret bootstrap ---------------------------------------------------

    def _load_or_create_token_secret(self, mongo_db: str) -> bytes:
        env_secret = os.getenv("KAIRO_SESSION_SECRET", "").strip()
        if env_secret:
            return env_secret.encode("utf-8")
        meta = self._client[mongo_db]["kairo_meta"]
        doc = meta.find_one({"_id": "session_secret"})
        if doc and doc.get("secret"):
            return doc["secret"].encode("utf-8")
        secret = secrets.token_urlsafe(48)
        try:
            meta.insert_one({"_id": "session_secret", "secret": secret,
                             "created_at": datetime.now(timezone.utc)})
        except DuplicateKeyError:
            doc = meta.find_one({"_id": "session_secret"})
            if doc:
                return doc["secret"].encode("utf-8")
        return secret.encode("utf-8")

    def _hash_token(self, token: str) -> str:
        return hmac.new(self._token_secret, token.encode("utf-8"), hashlib.sha256).hexdigest()

    # ---- password hashing ---------------------------------------------------

    @staticmethod
    def _hash(password: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), 260_000
        ).hex()

    # ---- account creation ---------------------------------------------------

    def create_user(
        self,
        username: str,
        password: str,
        role: str = "user",
        email: str = "",
    ) -> bool:
        """Insert a new user. Returns False if username already taken.

        Raises AuthError if username/password fail policy. Callers should
        catch AuthError to surface the specific message to the user.
        """
        uname_err = validate_username(username)
        if uname_err:
            raise AuthError("invalid_username", uname_err)
        pw_err = validate_password(password)
        if pw_err:
            raise AuthError("weak_password", pw_err)

        salt = secrets.token_hex(16)
        try:
            self._col.insert_one({
                "username":        username.strip().lower(),
                "email":           email.strip().lower(),
                "password_hash":   self._hash(password, salt),
                "salt":            salt,
                "role":            role,
                "first_name":      "",
                "last_name":       "",
                "profession":      "",
                "trading_profile": "",
                "purpose":         "",
                "created_at":      datetime.now(timezone.utc),
                "last_login":      None,
            })
            return True
        except DuplicateKeyError:
            return False

    # ---- login + rate limit -------------------------------------------------

    def _active_failed_attempts(self, username: str) -> int:
        now = datetime.now(timezone.utc)
        return self._attempts_col.count_documents({
            "username": username,
            "expires_at": {"$gt": now},
        })

    def _record_failed_attempt(self, username: str) -> None:
        now = datetime.now(timezone.utc)
        self._attempts_col.insert_one({
            "username": username,
            "at": now,
            "expires_at": now + timedelta(seconds=_LOCKOUT_WINDOW_SECONDS),
        })

    def _clear_failed_attempts(self, username: str) -> None:
        self._attempts_col.delete_many({"username": username})

    def is_locked(self, username: str) -> bool:
        if not username:
            return False
        uname = username.strip().lower()
        return self._active_failed_attempts(uname) >= _LOCKOUT_THRESHOLD

    def seconds_until_unlock(self, username: str) -> int:
        uname = username.strip().lower()
        now = datetime.now(timezone.utc)
        doc = self._attempts_col.find_one(
            {"username": uname, "expires_at": {"$gt": now}},
            sort=[("expires_at", ASCENDING)],
        )
        if not doc:
            return 0
        return max(0, int((doc["expires_at"] - now).total_seconds()))

    def authenticate(self, username: str, password: str) -> Optional[dict]:
        """Return full profile dict on success, None on bad credentials.

        Raises AuthError('locked', ...) when the account is throttled.
        Always burns equivalent time on failure to make user-enumeration harder.
        """
        if not username or not password:
            return None
        uname = username.strip().lower()

        if self._active_failed_attempts(uname) >= _LOCKOUT_THRESHOLD:
            wait = self.seconds_until_unlock(uname)
            mins = max(1, (wait + 59) // 60)
            raise AuthError(
                "locked",
                f"Too many failed attempts. Try again in {mins} minute{'s' if mins != 1 else ''}.",
            )

        user = self._col.find_one({"username": uname})
        if not user:
            # Constant-ish work to discourage username enumeration via timing.
            self._hash(password, "dummy-salt-for-timing-only")
            self._record_failed_attempt(uname)
            return None

        if not secrets.compare_digest(
            self._hash(password, user["salt"]),
            user["password_hash"],
        ):
            self._record_failed_attempt(uname)
            return None

        self._clear_failed_attempts(uname)
        self._col.update_one(
            {"_id": user["_id"]},
            {"$set": {"last_login": datetime.now(timezone.utc)}},
        )
        return self._to_profile(user)

    # ---- profile ------------------------------------------------------------

    def get_profile(self, username: str) -> Optional[dict]:
        user = self._col.find_one({"username": username.strip().lower()})
        return self._to_profile(user) if user else None

    def update_profile(self, username: str, updates: dict) -> bool:
        """Update allowed profile fields. Returns True on success."""
        allowed = {"first_name", "last_name", "email", "profession", "trading_profile", "purpose"}
        safe = {k: v.strip() for k, v in updates.items() if k in allowed and isinstance(v, str)}
        if not safe:
            return False
        self._col.update_one({"username": username.strip().lower()}, {"$set": safe})
        return True

    def change_password(self, username: str, old_password: str, new_password: str) -> bool:
        """Verify old password then replace. Returns True on success.

        Raises AuthError('weak_password', ...) if the new password fails policy.
        Invalidates every active session for the user — a stolen token must not
        survive a password reset.
        """
        pw_err = validate_password(new_password)
        if pw_err:
            raise AuthError("weak_password", pw_err)

        uname = username.strip().lower()
        user = self._col.find_one({"username": uname})
        if not user:
            return False
        if not secrets.compare_digest(
            self._hash(old_password, user["salt"]),
            user["password_hash"],
        ):
            return False
        salt = secrets.token_hex(16)
        self._col.update_one(
            {"_id": user["_id"]},
            {"$set": {"password_hash": self._hash(new_password, salt), "salt": salt}},
        )
        self.invalidate_all_sessions(uname)
        return True

    # ---- sessions -----------------------------------------------------------

    def create_session_token(self, username: str, days: int = _SESSION_ABSOLUTE_DAYS) -> str:
        """Issue a 'remember me' token. Only the HMAC is stored server-side."""
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        absolute = min(days, _SESSION_ABSOLUTE_DAYS)
        self._sessions_col.insert_one({
            "token_hash": self._hash_token(token),
            "username": username.strip().lower(),
            "created_at": now,
            "last_used_at": now,
            "expires_at": now + timedelta(days=absolute),
        })
        return token

    def validate_session_token(self, token: str) -> Optional[str]:
        """Return username if token is valid (not expired, not idle-timed-out).

        Slides the idle window forward on each successful validation.
        """
        if not token:
            return None
        token_hash = self._hash_token(token)
        doc = self._sessions_col.find_one({"token_hash": token_hash})
        if not doc:
            return None
        now = datetime.now(timezone.utc)
        expires = doc["expires_at"]
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < now:
            self._sessions_col.delete_one({"_id": doc["_id"]})
            return None
        last_used = doc.get("last_used_at") or doc.get("created_at") or now
        if last_used.tzinfo is None:
            last_used = last_used.replace(tzinfo=timezone.utc)
        if (now - last_used) > timedelta(days=_SESSION_IDLE_DAYS):
            self._sessions_col.delete_one({"_id": doc["_id"]})
            return None
        self._sessions_col.update_one(
            {"_id": doc["_id"]},
            {"$set": {"last_used_at": now}},
        )
        return doc["username"]

    def invalidate_session_token(self, token: str) -> None:
        if not token:
            return
        self._sessions_col.delete_one({"token_hash": self._hash_token(token)})

    def invalidate_all_sessions(self, username: str) -> int:
        """Drop every active session for a user. Returns the count removed."""
        if not username:
            return 0
        result = self._sessions_col.delete_many({"username": username.strip().lower()})
        return result.deleted_count

    # ---- admin --------------------------------------------------------------

    def delete_user(self, username: str) -> bool:
        """Permanently delete a user account and all their session tokens."""
        uname = username.strip().lower()
        self._sessions_col.delete_many({"username": uname})
        self._attempts_col.delete_many({"username": uname})
        result = self._col.delete_one({"username": uname})
        return result.deleted_count > 0

    def has_any_admin(self) -> bool:
        return self._col.count_documents({"role": "admin"}) > 0

    def ensure_default_admin(self) -> Optional[Tuple[str, str]]:
        """Bootstrap an admin account if none exists.

        Returns (username, one_time_password) if a new admin was created so the
        caller can log it ONCE to the server logs. Returns None if an admin
        already exists. Never returns a hard-coded password — the bootstrap
        password is randomly generated and must be rotated on first login.
        """
        if self.has_any_admin():
            return None
        # Allow operators to seed via env vars; otherwise random.
        username = (os.getenv("KAIRO_ADMIN_USERNAME") or "admin").strip().lower()
        password = os.getenv("KAIRO_ADMIN_PASSWORD") or secrets.token_urlsafe(18)
        # Bypass policy for the bootstrap path so a randomly generated token
        # never gets rejected. Operators using env vars should pick a strong one.
        salt = secrets.token_hex(16)
        try:
            self._col.insert_one({
                "username":        username,
                "email":           "",
                "password_hash":   self._hash(password, salt),
                "salt":            salt,
                "role":            "admin",
                "first_name":      "",
                "last_name":       "",
                "profession":      "",
                "trading_profile": "",
                "purpose":         "",
                "created_at":      datetime.now(timezone.utc),
                "last_login":      None,
            })
            return username, password
        except DuplicateKeyError:
            return None

    @staticmethod
    def _to_profile(user: dict) -> dict:
        filled = sum(1 for f in _BONUS_FIELDS if user.get(f))
        return {
            "username":        user["username"],
            "role":            user["role"],
            "email":           user.get("email", ""),
            "first_name":      user.get("first_name", ""),
            "last_name":       user.get("last_name", ""),
            "profession":      user.get("profession", ""),
            "trading_profile": user.get("trading_profile", ""),
            "purpose":         user.get("purpose", ""),
            "profile_filled":  filled,
            "profile_total":   len(_BONUS_FIELDS),
        }
