from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite

from masking.db.schema import initialize_schema
from settings import get_settings


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.connection, None]:

    db_path: Path = get_settings().DB_PATH

    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        await db.execute("PRAGMA journal_mode=WAL")

        await db.execute("PRAGMA foreign_keys=ON")

        await initialize_schema(db)

        yield db
