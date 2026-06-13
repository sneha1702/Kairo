import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional

from pymongo import MongoClient, ASCENDING
from pymongo.errors import DuplicateKeyError


class UserManager:
    COLLECTION = "kairo_users"

    def __init__(self, mongo_uri: str, mongo_db: str):
        from config.config import mongo_tls_ca_file
        ca = mongo_tls_ca_file()
        self._client = MongoClient(mongo_uri, tlsCAFile=ca)
        self._col = self._client[mongo_db][self.COLLECTION]
        self._col.create_index([("username", ASCENDING)], unique=True)

    @staticmethod
    def _hash(password: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), 260_000
        ).hex()

    def create_user(self, username: str, password: str, role: str = "user") -> bool:
        """Insert a new user. Returns False if username already taken."""
        salt = secrets.token_hex(16)
        try:
            self._col.insert_one({
                "username": username.strip().lower(),
                "password_hash": self._hash(password, salt),
                "salt": salt,
                "role": role,
                "created_at": datetime.now(timezone.utc),
                "last_login": None,
            })
            return True
        except DuplicateKeyError:
            return False

    def authenticate(self, username: str, password: str) -> Optional[dict]:
        """Return {username, role} on success, None on failure."""
        user = self._col.find_one({"username": username.strip().lower()})
        if not user:
            return None
        if not secrets.compare_digest(
            self._hash(password, user["salt"]),
            user["password_hash"],
        ):
            return None
        self._col.update_one(
            {"_id": user["_id"]},
            {"$set": {"last_login": datetime.now(timezone.utc)}},
        )
        return {"username": user["username"], "role": user["role"]}

    def has_any_admin(self) -> bool:
        return self._col.count_documents({"role": "admin"}) > 0

    def ensure_default_admin(self) -> bool:
        """Create admin/kairo-admin if no admin exists yet. Returns True if created."""
        if not self.has_any_admin():
            return self.create_user("admin", "kairo-admin", role="admin")
        return False
