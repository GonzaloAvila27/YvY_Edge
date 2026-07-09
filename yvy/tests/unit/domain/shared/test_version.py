"""Tests del semver canónico (INI-2 · 2.1.1 · H2).

Lo importante acá no es el parseo (es trivial) sino la **política ante versiones
no parseables**: antes vivía escondida en el ``except`` de dos helpers distintos,
con valores opuestos, en la ruta OTA. Ahora es un parámetro obligatorio y estos
tests fijan que cada call site conserve la suya.
"""

from __future__ import annotations

import pytest

from yvy.domain.shared.version import parse_semver, version_gte, version_lte


@pytest.mark.unit
class TestParseSemver:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("1.5.1", (1, 5, 1)),
            ("0.0.0", (0, 0, 0)),
            ("10.20.30", (10, 20, 30)),
            ("99.0.0", (99, 0, 0)),
            # Sufijos: `installer` NO los descartaba (reventaba); ahora sí.
            ("1.5.1-rc1", (1, 5, 1)),
            ("1.5.1+build.7", (1, 5, 1)),
            ("1.5.1-rc1+build", (1, 5, 1)),
            # Componentes de más se ignoran.
            ("1.2.3.4", (1, 2, 3)),
            # Faltantes se completan con ceros.
            ("1.5", (1, 5, 0)),
            ("2", (2, 0, 0)),
            ("  1.5.1  ", (1, 5, 1)),
        ],
    )
    def test_parsea(self, value, expected):
        assert parse_semver(value) == expected

    @pytest.mark.parametrize(
        "value",
        ["", "no-es-semver", "abc", "1.x.3", "1..3", ".", "v1.5.1", None, 151],
    )
    def test_no_parseable_devuelve_none(self, value):
        assert parse_semver(value) is None

    def test_nunca_lanza(self):
        """El caller decide qué hacer; el parser no puede explotar."""
        for value in ["", None, [], {}, "1.5.1", "💥"]:
            parse_semver(value)  # type: ignore[arg-type]

    def test_una_version_de_dos_partes_iguala_a_la_de_tres(self):
        """Corrección respecto de las dos impls viejas, que daban (1,5) < (1,5,0)."""
        assert parse_semver("1.5") == parse_semver("1.5.0")


@pytest.mark.unit
class TestComparadores:
    def test_gte(self):
        assert version_gte("1.5.1", "1.5.0", on_unparseable=False) is True
        assert version_gte("1.5.0", "1.5.0", on_unparseable=False) is True
        assert version_gte("1.4.9", "1.5.0", on_unparseable=False) is False

    def test_lte(self):
        assert version_lte("1.5.0", "1.5.1", on_unparseable=True) is True
        assert version_lte("1.5.1", "1.5.1", on_unparseable=True) is True
        assert version_lte("1.5.2", "1.5.1", on_unparseable=True) is False

    def test_compara_ignorando_sufijos(self):
        assert version_gte("1.5.1-rc1", "1.5.1", on_unparseable=False) is True
        assert version_lte("1.5.1+build", "1.5.1", on_unparseable=False) is True


@pytest.mark.unit
class TestPoliticaDeError:
    """El corazón de H2: la política es explícita y no tiene default."""

    def test_on_unparseable_es_obligatorio_y_keyword_only(self):
        with pytest.raises(TypeError):
            version_gte("1.5.1", "x")  # type: ignore[call-arg]
        with pytest.raises(TypeError):
            version_lte("1.5.1", "x")  # type: ignore[call-arg]
        with pytest.raises(TypeError):
            version_gte("1.5.1", "x", True)  # type: ignore[misc]

    @pytest.mark.parametrize("policy", [True, False])
    @pytest.mark.parametrize(
        ("a", "b"),
        [("no-semver", "1.5.1"), ("1.5.1", "no-semver"), ("x", "y")],
    )
    def test_devuelve_la_politica_ante_no_parseable(self, a, b, policy):
        assert version_gte(a, b, on_unparseable=policy) is policy
        assert version_lte(a, b, on_unparseable=policy) is policy

    def test_politica_del_installer_no_bloquear(self):
        """`min_edge_version` corrupto NO debe impedir instalar."""
        assert version_gte("1.5.1", "basura", on_unparseable=True) is True

    def test_politica_de_app_config_no_descartar_el_pending(self):
        """Un pending con versión ilegible NO debe borrarse por las dudas."""
        assert version_lte("basura", "1.5.1", on_unparseable=False) is False
