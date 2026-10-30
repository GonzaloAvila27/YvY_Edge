"""Semver canónico: un parser, políticas de error explícitas (INI-2 · 2.1.1 · H2).

Había **dos** implementaciones de comparación de versiones, con políticas
**opuestas** ante una versión no parseable:

===========================  ================  ==================================
sitio                        ante no-parseable qué significaba
===========================  ================  ==================================
``installer._version_gte``   ``True``          "ante la duda, no bloquear el install"
``app_config._parse_semver`` ``False``         "ante la duda, no descartar el pending"
===========================  ================  ==================================

Las dos son correctas **en su contexto**: una falla hacia *permitir*, la otra
hacia *conservar*. El problema no era que difirieran, sino que la política
estuviera **escondida dentro del ``except``** de cada helper — invisible en el
call site, y en la ruta OTA, que es la de mayor consecuencia.

Acá el parser es único y la política viaja como **parámetro obligatorio**
(``on_unparseable``, keyword-only): quien compara versiones tiene que declarar
explícitamente hacia dónde falla.

Además el parser es uno solo, así que el manejo de sufijos deja de divergir:
``installer`` no los descartaba (``"1.5.1-rc1"`` reventaba y caía al ``True``),
``app_config`` sí. Ahora ambos parsean igual.
"""

from __future__ import annotations

__all__ = ["Version", "parse_semver", "version_gte", "version_lte"]

#: Versión normalizada a 3 componentes: ``(major, minor, patch)``.
Version = tuple[int, int, int]

_MAX_PARTS = 3


def parse_semver(value: str) -> Version | None:
    """``"1.5.1"`` → ``(1, 5, 1)``. ``None`` si no se puede parsear.

    - Descarta sufijos de pre-release y build: ``"1.5.1-rc1"`` y ``"1.5.1+abc"``
      parsean a ``(1, 5, 1)``.
    - Ignora componentes de más: ``"1.2.3.4"`` → ``(1, 2, 3)``.
    - Completa con ceros los que falten: ``"1.5"`` → ``(1, 5, 0)``, de modo que
      ``"1.5" == "1.5.0"`` (las dos implementaciones viejas las trataban como
      distintas: ``(1, 5) < (1, 5, 0)``).

    Nunca lanza: devolver ``None`` obliga al caller a declarar su política.
    """
    if not isinstance(value, str):
        return None

    base = value.split("-", 1)[0].split("+", 1)[0].strip()
    parts = base.split(".")[:_MAX_PARTS]
    try:
        numbers = [int(part) for part in parts]
    except (TypeError, ValueError):
        return None
    if not numbers:
        return None

    numbers += [0] * (_MAX_PARTS - len(numbers))
    return (numbers[0], numbers[1], numbers[2])


def version_gte(value: str, minimum: str, *, on_unparseable: bool) -> bool:
    """``value >= minimum``.

    Args:
        on_unparseable: qué devolver si alguna de las dos no parsea. Es
            obligatorio y keyword-only: la política de falla debe ser una
            decisión visible del call site, no un default heredado.
    """
    parsed_value = parse_semver(value)
    parsed_minimum = parse_semver(minimum)
    if parsed_value is None or parsed_minimum is None:
        return on_unparseable
    return parsed_value >= parsed_minimum


def version_lte(value: str, other: str, *, on_unparseable: bool) -> bool:
    """``value <= other``. Ver :func:`version_gte` sobre ``on_unparseable``."""
    parsed_value = parse_semver(value)
    parsed_other = parse_semver(other)
    if parsed_value is None or parsed_other is None:
        return on_unparseable
    return parsed_value <= parsed_other
