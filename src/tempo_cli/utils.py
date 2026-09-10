"""Utilidades: parseo de horas, fechas, y helpers generales."""

from __future__ import annotations

import re
from datetime import date, timedelta


def parse_hours(value: str) -> float:
    """Parsea formatos flexibles de horas.

    Soporta: '4h', '4.5h', '4h30m', '30m', '2'
    """
    value = value.strip().lower()

    # 4h30m
    match = re.match(r"^(\d+)h(\d+)m$", value)
    if match:
        return int(match.group(1)) + int(match.group(2)) / 60

    # 4h o 4.5h
    match = re.match(r"^(\d+\.?\d*)h$", value)
    if match:
        return float(match.group(1))

    # 30m
    match = re.match(r"^(\d+)m$", value)
    if match:
        return int(match.group(1)) / 60

    # número directo (asume horas)
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"Formato de horas no reconocido: '{value}'")


def parse_date(value: str | None) -> date:
    """Parsea fechas con soporte para atajos.

    Soporta: YYYY-MM-DD, 'today', 'yesterday', 'monday'...'friday', 'last-monday'...'last-friday'
    """
    if value is None:
        return date.today()

    value = value.strip().lower()

    if value == "today":
        return date.today()

    if value == "yesterday":
        return date.today() - timedelta(days=1)

    weekdays = {
        "monday": 0, "tuesday": 1, "wednesday": 2,
        "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
    }

    # last-monday, last-friday, etc.
    if value.startswith("last-"):
        day_name = value[5:]
        if day_name in weekdays:
            target = weekdays[day_name]
            today = date.today()
            days_back = (today.weekday() - target) % 7
            if days_back == 0:
                days_back = 7
            return today - timedelta(days=days_back)

    # monday, tuesday, etc. (de esta semana)
    if value in weekdays:
        target = weekdays[value]
        today = date.today()
        days_diff = target - today.weekday()
        return today + timedelta(days=days_diff)

    # ISO format YYYY-MM-DD
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"Formato de fecha no reconocido: '{value}'")


def get_week_range(target_date: date | None = None) -> tuple[date, date]:
    """Retorna el lunes y viernes de la semana de la fecha dada."""
    d = target_date or date.today()
    monday = d - timedelta(days=d.weekday())
    friday = monday + timedelta(days=4)
    return monday, friday


def get_timesheet_period(target_date: date | None = None) -> tuple[date, date]:
    """Retorna el lunes y domingo de la semana de la fecha dada.

    Tempo maneja los períodos de timesheet de lunes a domingo, no lunes a viernes.
    """
    d = target_date or date.today()
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


_DAY_NAMES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def day_name(d: date) -> str:
    """Retorna el nombre del día de la semana en español."""
    return _DAY_NAMES[d.weekday()]


def is_weekend(d: date) -> bool:
    """Retorna True si la fecha es sábado o domingo."""
    return d.weekday() >= 5


def fmt_hours(hours: float) -> str:
    """Formatea horas para mostrar sin redondeo engañoso.

    Usa 2 decimales para reflejar fielmente incrementos de 15 min (0.25)
    y 30 min (0.5), pero elimina ceros finales innecesarios.
    Ejemplos: 1.75 → '1.75', 2.0 → '2', 0.5 → '0.5', 0.25 → '0.25'
    """
    # Redondear a 2 decimales para evitar errores de punto flotante
    rounded = round(hours, 2)
    # Formatear con 2 decimales y quitar ceros finales
    text = f"{rounded:.2f}".rstrip("0").rstrip(".")
    return text
