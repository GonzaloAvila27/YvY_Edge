"""Enums del subdominio ``empirical``."""

from __future__ import annotations

from enum import StrEnum


class WindDirection(StrEnum):
    N = "N"
    NE = "NE"
    E = "E"
    SE = "SE"
    S = "S"
    SO = "SO"
    O = "O"  # noqa: E741 — Oeste (punto cardinal del dominio), no ambiguo acá
    NO = "NO"


class HumidityPercept(StrEnum):
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"
    SATURADA = "saturada"


class CloudType(StrEnum):
    CIRROS = "cirros"
    CUMULOS = "cumulos"
    ESTRATOS = "estratos"
    CUMULONIMBOS = "cumulonimbos"
    MEZCLA = "mezcla"
    SIN_NUBES = "sin_nubes"


class SoilState(StrEnum):
    SECO = "seco"
    HUMEDO = "humedo"
    ENCHARCADO = "encharcado"
    HELADO = "helado"
    ESCARCHA = "escarcha"


class Visibility(StrEnum):
    BUENA = "buena"
    REGULAR = "regular"
    NIEBLA = "niebla"
    BRUMA = "bruma"


class PrecipitationNow(StrEnum):
    NO = "no"
    LLOVIZNA = "llovizna"
    LLUVIA_LEVE = "lluvia_leve"
    LLUVIA = "lluvia"
    LLUVIA_INTENSA = "lluvia_intensa"
    GRANIZO = "granizo"


class LivestockState(StrEnum):
    NORMAL = "normal"
    REFUGIADOS = "refugiados"
    AGITADOS = "agitados"
    OTRO = "otro"


class EventType(StrEnum):
    HELADA = "helada"
    GRANIZO = "granizo"
    VIENTO_FUERTE = "viento_fuerte"
    LLUVIA_TORRENCIAL = "lluvia_torrencial"
    SEQUIA = "sequia"
    NIEBLA_DENSA = "niebla_densa"
    TORMENTA_ELECTRICA = "tormenta_electrica"


class HailSize(StrEnum):
    ARROZ = "arroz"
    LENTEJA = "lenteja"
    POROTO = "poroto"
    CANICA = "canica"
    NUEZ = "nuez"


SKY_COVERAGE_VALUES: frozenset[int] = frozenset({0, 25, 50, 75, 100})

BEAUFORT_MIN: int = 0
BEAUFORT_MAX: int = 12

RAIN_MM_MIN: float = 0.0
RAIN_MM_MAX: float = 500.0

TEMP_C_MIN: float = -30.0
TEMP_C_MAX: float = 55.0

BEAUFORT_DESCRIPTIONS: dict[int, str] = {
    0: "0 · Calma — humo vertical",
    1: "1 · Ventolina — humo se inclina",
    2: "2 · Brisa muy débil — se siente en la cara",
    3: "3 · Brisa débil — banderas extendidas",
    4: "4 · Brisa moderada — levanta polvo",
    5: "5 · Brisa fresca — árboles pequeños se balancean",
    6: "6 · Viento fuerte — silbido en cables",
    7: "7 · Viento muy fuerte — caminar incómodo",
    8: "8 · Temporal — ramas se rompen",
    9: "9 · Vendaval — daños menores",
    10: "10 · Tormenta — daños en estructuras",
    11: "11 · Borrasca — daños extensos",
    12: "12 · Huracán — devastación",
}

CLOUD_TYPE_DESCRIPTIONS: dict[CloudType, str] = {
    CloudType.CIRROS: "Cirros — altos, blancos, en plumas o hilos",
    CloudType.CUMULOS: "Cúmulos — algodonosos, base plana, buen tiempo",
    CloudType.ESTRATOS: "Estratos — capa baja gris, lluvia leve",
    CloudType.CUMULONIMBOS: "Cumulonimbos — torres altas, tormenta",
    CloudType.MEZCLA: "Mezcla — varios tipos visibles",
    CloudType.SIN_NUBES: "Sin nubes — cielo despejado",
}
