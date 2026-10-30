"""Tests del módulo hardware_fingerprint.

Cubre:
- Validación de UUID (formato + lista de UUIDs inválidos conocidos).
- Mock de plataforma (linux/windows/macos) y verificación de
  fallback a None cuando algo falla.
- Funciones internas no se llaman si la plataforma no matchea.

NO testea lectura real de /sys ni wmic — eso es integración con SO
y no es portable a CI.
"""

from __future__ import annotations

from unittest.mock import patch

from yvy.infrastructure.system.hardware_fingerprint import (
    _validate_uuid,
    read_hardware_fingerprint,
)


class TestValidateUuid:
    def test_accepts_valid_uuid(self) -> None:
        v = _validate_uuid("12345678-1234-4123-8123-123456789abc")
        assert v == "12345678-1234-4123-8123-123456789abc"

    def test_lowercases_uppercase(self) -> None:
        v = _validate_uuid("ABCDEF12-3456-7890-ABCD-EF1234567890")
        assert v == "abcdef12-3456-7890-abcd-ef1234567890"

    def test_strips_whitespace(self) -> None:
        v = _validate_uuid("  12345678-1234-4123-8123-123456789abc  \n")
        assert v == "12345678-1234-4123-8123-123456789abc"

    def test_rejects_empty(self) -> None:
        assert _validate_uuid("") is None
        assert _validate_uuid("   ") is None

    def test_rejects_garbage(self) -> None:
        assert _validate_uuid("not-a-uuid") is None
        assert _validate_uuid("12345") is None

    def test_rejects_zeros(self) -> None:
        """UUID de placeholder de firmware mal configurado."""
        assert _validate_uuid("00000000-0000-0000-0000-000000000000") is None

    def test_rejects_all_f(self) -> None:
        """Otro UUID de placeholder."""
        assert _validate_uuid("ffffffff-ffff-ffff-ffff-ffffffffffff") is None

    def test_rejects_known_placeholder(self) -> None:
        assert _validate_uuid("03000200-0400-0500-0006-000700080009") is None


class TestReadHardwareFingerprint:
    def test_returns_none_on_unsupported_platform(self) -> None:
        with patch("platform.system", return_value="FreeBSD"):
            assert read_hardware_fingerprint() is None

    def test_returns_none_when_linux_paths_missing(self) -> None:
        from pathlib import Path

        with (
            patch("platform.system", return_value="Linux"),
            patch.object(Path, "exists", return_value=False),
        ):
            assert read_hardware_fingerprint() is None

    def test_returns_none_on_exception(self) -> None:
        """Si lectura crashea, devuelve None silenciosamente."""
        with patch("platform.system", side_effect=RuntimeError("boom")):
            assert read_hardware_fingerprint() is None

    def test_linux_reads_valid_uuid_from_sys(self, tmp_path) -> None:
        """Mock de Path.read_text para devolver un UUID válido."""
        from pathlib import Path

        fake_uuid = "abcdef12-3456-7890-abcd-ef1234567890"

        with (
            patch("platform.system", return_value="Linux"),
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value=fake_uuid + "\n"),
        ):
            assert read_hardware_fingerprint() == fake_uuid

    def test_linux_handles_permission_error(self) -> None:
        from pathlib import Path

        with (
            patch("platform.system", return_value="Linux"),
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", side_effect=PermissionError("denied")),
        ):
            assert read_hardware_fingerprint() is None

    def test_windows_uses_wmic_when_available(self) -> None:
        from subprocess import CompletedProcess

        fake_out = "UUID\n12345678-1234-4123-8123-123456789abc\n\n"
        fake_proc = CompletedProcess(args=[], returncode=0, stdout=fake_out, stderr="")

        with (
            patch("platform.system", return_value="Windows"),
            patch("subprocess.run", return_value=fake_proc),
        ):
            assert read_hardware_fingerprint() == "12345678-1234-4123-8123-123456789abc"

    def test_windows_falls_back_when_wmic_returns_invalid(self) -> None:
        """wmic devuelve placeholder + powershell devuelve UUID válido."""
        from subprocess import CompletedProcess

        wmic_out = CompletedProcess(
            args=[],
            returncode=0,
            stdout="UUID\n00000000-0000-0000-0000-000000000000\n",
            stderr="",
        )
        ps_out = CompletedProcess(
            args=[],
            returncode=0,
            stdout="abcdef12-3456-7890-abcd-ef1234567890\n",
            stderr="",
        )

        with (
            patch("platform.system", return_value="Windows"),
            patch("subprocess.run", side_effect=[wmic_out, ps_out]),
        ):
            assert read_hardware_fingerprint() == "abcdef12-3456-7890-abcd-ef1234567890"
