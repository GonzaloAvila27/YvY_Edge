"""Implementación SQLite de UserRepository."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from yvy.domain.auth.enums import Role
from yvy.domain.auth.models import User
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory


class SQLiteUserRepository:
    """Persistencia SQLite de users."""

    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self._factory = factory

    def find_by_username(self, username: str) -> User | None:
        conn = self._factory.get_connection()
        cur = conn.execute(
            """
            SELECT id, user_uuid, username, full_name, role, is_active,
                   can_export_raw, created_at, last_login
            FROM users WHERE username = ?
            """,
            (username,),
        )
        row = cur.fetchone()
        return _row_to_user(row) if row else None

    def find_by_id(self, user_id: int) -> User | None:
        conn = self._factory.get_connection()
        cur = conn.execute(
            """
            SELECT id, user_uuid, username, full_name, role, is_active,
                   can_export_raw, created_at, last_login
            FROM users WHERE id = ?
            """,
            (user_id,),
        )
        row = cur.fetchone()
        return _row_to_user(row) if row else None

    def find_by_uuid(self, user_uuid: UUID) -> User | None:
        conn = self._factory.get_connection()
        cur = conn.execute(
            """
            SELECT id, user_uuid, username, full_name, role, is_active,
                   can_export_raw, created_at, last_login
            FROM users WHERE user_uuid = ?
            """,
            (str(user_uuid),),
        )
        row = cur.fetchone()
        return _row_to_user(row) if row else None

    def save(self, user: User, password_hash: str) -> int:
        """INSERT si user.id is None, UPDATE si existe."""
        conn = self._factory.get_connection()

        if user.id is None:
            cur = conn.execute(
                """
                INSERT INTO users (
                    user_uuid, username, full_name, password_hash,
                    role, is_active, can_export_raw
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(user.user_uuid),
                    user.username,
                    user.full_name,
                    password_hash,
                    str(user.role),
                    1 if user.is_active else 0,
                    1 if user.can_export_raw else 0,
                ),
            )
            new_id = cur.lastrowid
            assert new_id is not None
            return int(new_id)

        # UPDATE
        conn.execute(
            """
            UPDATE users
               SET username        = ?,
                   full_name       = ?,
                   password_hash   = ?,
                   role            = ?,
                   is_active       = ?,
                   can_export_raw  = ?
             WHERE id = ?
            """,
            (
                user.username,
                user.full_name,
                password_hash,
                str(user.role),
                1 if user.is_active else 0,
                1 if user.can_export_raw else 0,
                user.id,
            ),
        )
        return user.id

    def get_password_hash(self, user_id: int) -> str | None:
        conn = self._factory.get_connection()
        cur = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?",
            (user_id,),
        )
        row = cur.fetchone()
        return str(row[0]) if row else None

    def list_active(self) -> list[User]:
        conn = self._factory.get_connection()
        cur = conn.execute(
            """
            SELECT id, user_uuid, username, full_name, role, is_active,
                   can_export_raw, created_at, last_login
            FROM users WHERE is_active = 1
            ORDER BY username
            """
        )
        return [_row_to_user(r) for r in cur.fetchall()]

    def list_all(self) -> list[User]:
        conn = self._factory.get_connection()
        cur = conn.execute(
            """
            SELECT id, user_uuid, username, full_name, role, is_active,
                   can_export_raw, created_at, last_login
            FROM users ORDER BY username
            """
        )
        return [_row_to_user(r) for r in cur.fetchall()]

    def count_by_role(self, role: Role) -> int:
        conn = self._factory.get_connection()
        cur = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role = ?",
            (str(role),),
        )
        return int(cur.fetchone()[0])

    def count_active_admins(self) -> int:
        conn = self._factory.get_connection()
        cur = conn.execute(
            """
            SELECT COUNT(*) FROM users
             WHERE is_active = 1
               AND role IN ('admin', 'superadmin')
            """
        )
        return int(cur.fetchone()[0])

    def update_last_login(self, user_id: int, when: datetime) -> None:
        conn = self._factory.get_connection()
        iso = when.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        conn.execute(
            "UPDATE users SET last_login = ? WHERE id = ?",
            (iso, user_id),
        )


def _row_to_user(row: Any) -> User:
    """Mapea fila de DB a User entity."""
    last_login = (
        datetime.fromisoformat(row["last_login"]) if row["last_login"] else None
    )
    created_at = (
        datetime.fromisoformat(row["created_at"]) if row["created_at"] else None
    )
    return User(
        id=row["id"],
        user_uuid=UUID(row["user_uuid"]),
        username=row["username"],
        full_name=row["full_name"],
        role=Role(row["role"]),
        is_active=bool(row["is_active"]),
        can_export_raw=bool(row["can_export_raw"]),
        created_at=created_at,
        last_login=last_login,
    )
