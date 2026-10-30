"""Tests para allowed_chart_labels_for_role (Fix 5.1 — filtrado por rol)."""

from yvy.presentation.views.dashboard_admin import (
    _CHART_LABELS,
    _FROST_LABEL,
    allowed_chart_labels_for_role,
)

# ─── Alumno ───────────────────────────────────────────────────────────────────


def test_alumno_excludes_frost() -> None:
    """El alumno no debe ver 'Heladas y eventos térmicos' (D81)."""
    labels = allowed_chart_labels_for_role("alumno")
    assert _FROST_LABEL not in labels


def test_alumno_sees_remaining_charts() -> None:
    """El alumno ve todos los gráficos excepto Heladas."""
    labels = allowed_chart_labels_for_role("alumno")
    expected = [l for l in _CHART_LABELS if l != _FROST_LABEL]
    assert labels == expected


# ─── Roles con acceso completo ────────────────────────────────────────────────


def test_profesor_includes_frost() -> None:
    labels = allowed_chart_labels_for_role("profesor")
    assert _FROST_LABEL in labels


def test_admin_includes_frost() -> None:
    labels = allowed_chart_labels_for_role("admin")
    assert _FROST_LABEL in labels


def test_superadmin_includes_frost() -> None:
    labels = allowed_chart_labels_for_role("superadmin")
    assert _FROST_LABEL in labels


def test_full_access_roles_return_all_labels() -> None:
    """Roles con acceso completo devuelven exactamente _CHART_LABELS."""
    for role in ("profesor", "admin", "superadmin"):
        assert allowed_chart_labels_for_role(role) == list(_CHART_LABELS)


# ─── Fail-safe para rol desconocido ──────────────────────────────────────────


def test_unknown_role_returns_alumno_subset() -> None:
    """Rol desconocido → subconjunto alumno (fail-safe al más restrictivo)."""
    labels = allowed_chart_labels_for_role("inspector_externo")
    assert _FROST_LABEL not in labels
    expected = [l for l in _CHART_LABELS if l != _FROST_LABEL]
    assert labels == expected


def test_empty_role_string_returns_alumno_subset() -> None:
    labels = allowed_chart_labels_for_role("")
    assert _FROST_LABEL not in labels


# ─── Propiedades del resultado ────────────────────────────────────────────────


def test_order_preserved_for_full_access() -> None:
    """El orden de las etiquetas respeta el orden de _CHART_LABEL_TO_KEY."""
    labels = allowed_chart_labels_for_role("admin")
    assert labels == list(_CHART_LABELS)


def test_alumno_list_is_non_empty() -> None:
    labels = allowed_chart_labels_for_role("alumno")
    assert len(labels) > 0


def test_alumno_list_is_shorter_than_full() -> None:
    alumno = allowed_chart_labels_for_role("alumno")
    full = allowed_chart_labels_for_role("admin")
    assert len(alumno) == len(full) - 1
