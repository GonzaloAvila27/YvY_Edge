"""Tests del CLI: subcomando migrate."""

from __future__ import annotations

from pathlib import Path

import pytest

from yvy.main import main


@pytest.mark.integration
class TestCliMigrate:
    def test_migrate_creates_db_and_applies(
        self, tmp_path: Path, migrations_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db_path = tmp_path / "yvy.sqlite"
        exit_code = main(["migrate", "--db", str(db_path), "--migrations", str(migrations_dir)])

        assert exit_code == 0
        assert db_path.exists()

        captured = capsys.readouterr()
        assert "Aplicadas" in captured.out or "Schema al día" in captured.out

    def test_migrate_idempotent(
        self, tmp_path: Path, migrations_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db_path = tmp_path / "yvy.sqlite"

        main(["migrate", "--db", str(db_path), "--migrations", str(migrations_dir)])
        capsys.readouterr()  # descartar primera salida

        exit_code = main(["migrate", "--db", str(db_path), "--migrations", str(migrations_dir)])
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "Schema al día" in captured.out

    def test_version_command(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(["version"])
        assert exit_code == 0

        captured = capsys.readouterr()
        from yvy import __version__

        assert __version__ in captured.out
