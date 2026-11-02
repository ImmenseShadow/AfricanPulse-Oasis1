from __future__ import annotations

import os
from typing import Optional

from src.models.article import ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER
from src.storage.user_repository import UserRepository


class AuthService:
    def __init__(self, repo: UserRepository):
        self.repo = repo

    def bootstrap_admin_if_configured(self) -> Optional[dict]:
        username = (os.environ.get("APOASIS_ADMIN_USERNAME") or "").strip()
        password = (os.environ.get("APOASIS_ADMIN_PASSWORD") or "").strip()
        if not username or not password:
            return None
        existing = self.repo.get_by_username(username)
        if existing is None:
            return self.repo.create_user(username, password, ROLE_ADMIN, True)
        if existing["role"] != ROLE_ADMIN:
            self.repo.update_role(existing["id"], ROLE_ADMIN)
        return existing

    def login(self, username: str, password: str) -> Optional[dict]:
        user = self.repo.verify_password(username, password)
        if user is None or not user["active"]:
            return None
        self.repo.update_last_login(user["id"])
        return user

    def ensure_user(self, username: str, password: str, role: str, active: bool = True) -> dict:
        user = self.repo.get_by_username(username)
        if user is None:
            self.repo.create_user(username, password, role, active)
            user = self.repo.get_by_username(username)
        return user

    def role_allowed(self, user, *allowed_roles: str) -> bool:
        if user is None:
            return False
        if user.get("active") in (0, False):
            return False
        return user.get("role") in allowed_roles

    def require_roles(self, user, *allowed_roles: str) -> bool:
        return self.role_allowed(user, *allowed_roles)
