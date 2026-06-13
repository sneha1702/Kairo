import hashlib
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

    def create_user(
        self,
        username: str,
        password: str,
        role: str = "user",
        email: str = "",
    ) -> bool:
        """Insert a new user. Returns False if username already taken."""
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

    def authenticate(self, username: str, password: str) -> Optional[dict]:
        """Return full profile dict on success, None on failure."""
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
        return self._to_profile(user)

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
        """Verify old password then replace. Returns True on success."""
        user = self._col.find_one({"username": username.strip().lower()})
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
        return True

    def has_any_admin(self) -> bool:
        return self._col.count_documents({"role": "admin"}) > 0

    def ensure_default_admin(self) -> bool:
        """Create admin/kairo-admin if no admin exists yet. Returns True if created."""
        if not self.has_any_admin():
            return self.create_user("admin", "kairo-admin", role="admin")
        return False

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
