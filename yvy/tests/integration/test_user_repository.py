"""Tests integration de SQLiteUserRepository."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from yvy.domain.auth.enums import Role
from yvy.domain.auth.models import User
from yvy.infrastructure.persistence.sqlite_user_repository import SQLiteUserRepository


def _new_user(
    *,
    role: Role = Role.ALUMNO,
    username: str = "testuser",
    full_name: str = "Test User",
    is_active: bool = True,
    can_export_raw: bool = False,
) -> User:
    return User(
        user_uuid=uuid4(),
        username=username,
        full_name=full_name,
        role=role,
        is_active=is_active,
        can_export_raw=can_export_raw,
    )


@pytest.mark.integration
class TestSaveAndFind:
    def test_save_new_user_returns_id(
        self, user_repo: SQLiteUserRepository
    ) -> None:
        u = _new_user()
        new_id = user_repo.save(u, "fake_hash_$2b$04$abc")
        assert new_id > 0

    def test_find_by_username_returns_persisted_data(
        self, user_repo: SQLiteUserRepository
    ) -> None:
        u = _new_user(username="alice", full_name="Alice Smith", role=Role.PROFESOR)
        new_id = user_repo.save(u, "hash1")

        found = user_repo.find_by_username("alice")
        assert found is not None
        assert found.id == new_id
        assert found.username == "alice"
        assert found.full_name == "Alice Smith"
        assert found.role == Role.PROFESOR
        assert found.is_active is True
        assert found.can_export_raw is False
        assert found.user_uuid == u.user_uuid
        assert found.created_at is not None  # default del schema
        assert found.last_login is None

    def test_find_by_username_returns_none_for_unknown(
        self, user_repo: SQLiteUserRepository
    ) -> None:
        assert user_repo.find_by_username("ghost") is None

    def test_find_by_id(self, user_repo: SQLiteUserRepository) -> None:
        u = _new_user()
        new_id = user_repo.save(u, "h")
        found = user_repo.find_by_id(new_id)
        assert found is not None
        assert found.id == new_id

    def test_find_by_uuid(self, user_repo: SQLiteUserRepository) -> None:
        u = _new_user()
        user_repo.save(u, "h")
        found = user_repo.find_by_uuid(u.user_uuid)
        assert found is not None
        assert found.username == u.username

    def test_get_password_hash_returns_stored(
        self, user_repo: SQLiteUserRepository
    ) -> None:
        u = _new_user()
        new_id = user_repo.save(u, "stored_hash_xyz")
        h = user_repo.get_password_hash(new_id)
        assert h == "stored_hash_xyz"

    def test_get_password_hash_returns_none_for_unknown_id(
        self, user_repo: SQLiteUserRepository
    ) -> None:
        assert user_repo.get_password_hash(99999) is None


@pytest.mark.integration
class TestUpdate:
    def test_save_existing_user_updates_fields(
        self, user_repo: SQLiteUserRepository
    ) -> None:
        u = _new_user(username="alice", role=Role.ALUMNO)
        new_id = user_repo.save(u, "h1")

        # Modificar y re-save
        from dataclasses import replace
        modified = replace(
            u,
            id=new_id,
            full_name="Alice Updated",
            role=Role.PROFESOR,
            can_export_raw=True,
        )
        user_repo.save(modified, "h2")

        found = user_repo.find_by_id(new_id)
        assert found is not None
        assert found.full_name == "Alice Updated"
        assert found.role == Role.PROFESOR
        assert found.can_export_raw is True
        # Hash actualizado
        assert user_repo.get_password_hash(new_id) == "h2"

    def test_update_last_login(
        self, user_repo: SQLiteUserRepository
    ) -> None:
        u = _new_user()
        new_id = user_repo.save(u, "h")

        when = datetime(2026, 5, 1, 10, 30, 0, tzinfo=UTC)
        user_repo.update_last_login(new_id, when)

        found = user_repo.find_by_id(new_id)
        assert found is not None
        assert found.last_login is not None
        assert found.last_login.replace(tzinfo=None) == when.replace(tzinfo=None)


@pytest.mark.integration
class TestList:
    def test_list_active_returns_only_active(
        self, user_repo: SQLiteUserRepository
    ) -> None:
        user_repo.save(_new_user(username="aaa"), "h")
        user_repo.save(_new_user(username="bbb", is_active=False), "h")
        user_repo.save(_new_user(username="ccc"), "h")

        active = user_repo.list_active()
        names = {u.username for u in active}
        assert names == {"aaa", "ccc"}

    def test_list_all_includes_inactive(
        self, user_repo: SQLiteUserRepository
    ) -> None:
        user_repo.save(_new_user(username="aaa"), "h")
        user_repo.save(_new_user(username="bbb", is_active=False), "h")

        all_users = user_repo.list_all()
        assert {u.username for u in all_users} == {"aaa", "bbb"}

    def test_list_all_ordered_by_username(
        self, user_repo: SQLiteUserRepository
    ) -> None:
        user_repo.save(_new_user(username="zoe"), "h")
        user_repo.save(_new_user(username="alice"), "h")
        user_repo.save(_new_user(username="bob"), "h")

        all_users = user_repo.list_all()
        assert [u.username for u in all_users] == ["alice", "bob", "zoe"]


@pytest.mark.integration
class TestCounts:
    def test_count_by_role(self, user_repo: SQLiteUserRepository) -> None:
        user_repo.save(_new_user(username="su1", role=Role.SUPERADMIN), "h")
        user_repo.save(_new_user(username="ad1", role=Role.ADMIN), "h")
        user_repo.save(_new_user(username="pr1", role=Role.PROFESOR), "h")
        user_repo.save(_new_user(username="al1", role=Role.ALUMNO), "h")
        user_repo.save(_new_user(username="al2", role=Role.ALUMNO), "h")

        assert user_repo.count_by_role(Role.SUPERADMIN) == 1
        assert user_repo.count_by_role(Role.ADMIN) == 1
        assert user_repo.count_by_role(Role.PROFESOR) == 1
        assert user_repo.count_by_role(Role.ALUMNO) == 2

    def test_count_by_role_includes_inactive(
        self, user_repo: SQLiteUserRepository
    ) -> None:
        """Para enforcing del límite de 2 admins, contamos TODOS (activos o no).

        Razón: si desactivás un admin y creás otro, técnicamente estás
        bypaseando el límite. Mejor contar todo y exigir borrar antes
        de crear nuevo.
        """
        user_repo.save(
            _new_user(username="ad1", role=Role.ADMIN, is_active=False),
            "h",
        )
        user_repo.save(_new_user(username="ad2", role=Role.ADMIN), "h")
        assert user_repo.count_by_role(Role.ADMIN) == 2

    def test_count_active_admins(self, user_repo: SQLiteUserRepository) -> None:
        user_repo.save(_new_user(username="su1", role=Role.SUPERADMIN), "h")
        user_repo.save(_new_user(username="ad1", role=Role.ADMIN), "h")
        user_repo.save(
            _new_user(username="ad2", role=Role.ADMIN, is_active=False),
            "h",
        )
        user_repo.save(_new_user(username="pr1", role=Role.PROFESOR), "h")

        # Activos administrativos: 1 superadmin + 1 admin activo
        assert user_repo.count_active_admins() == 2

    def test_count_active_admins_zero_when_no_admins(
        self, user_repo: SQLiteUserRepository
    ) -> None:
        user_repo.save(_new_user(username="alumno1", role=Role.ALUMNO), "h")
        user_repo.save(_new_user(username="profe1", role=Role.PROFESOR), "h")
        assert user_repo.count_active_admins() == 0
