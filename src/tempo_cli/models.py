"""Modelos de datos para Tempo CLI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class Worklog:
    """Representa un worklog registrado en Tempo."""

    id: int | None
    issue_key: str
    hours: float
    start_date: date
    start_time: str
    description: str | None = None
    source: str = "manual"  # manual | calendar

    @property
    def time_spent_seconds(self) -> int:
        return int(self.hours * 3600)


@dataclass
class CalendarEvent:
    """Representa un evento de calendario detectado por Tempo."""

    id: int
    issue_key: str
    hours: float
    start_date: date
    start_time: str
    description: str


@dataclass
class FrequentIssue:
    """Representa un ticket frecuente con alias."""

    key: str
    alias: str
    description: str
    default_hours: float


@dataclass
class TemplateEntry:
    """Representa una entrada dentro de un template."""

    issue: str  # alias o issue key
    hours: float
    description: str
