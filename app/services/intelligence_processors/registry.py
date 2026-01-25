from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

# A processor function receives: (db, run_id) and does the work
ProcessorFn = Callable[[AsyncSession, UUID], Awaitable[None]]


@dataclass(frozen=True)
class ProcessorSpec:
    name: str
    version: str
    handler: ProcessorFn
