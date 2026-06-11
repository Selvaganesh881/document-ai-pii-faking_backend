from __future__ import annotations

import aiosqlite

from typing import Optional, Any

# Get Sessions

async def get_session_by_hash(db: aiosqlite.Connection, 
                              hash: str
                              ) -> Optional[dict[str, str]]:
    async with db.execute(
        "SELECT * FROM pii_masking_sessions WHERE file_hash = ?", (hash,)
        ) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def get_session_by_session_id(db: aiosqlite.Connection, 
                              session_id: str
                              ) -> Optional[dict[str, str]]:
    async with db.execute(
        "SELECT * FROM pii_masking_sessions WHERE session_id = ?", (session_id,)
        ) as c:
        row = await c.fetchone()
    return dict(row) if row else None

# Insert Session

async def insert_session(
    db: aiosqlite.Connection, 
    session_id: str,
    original_filename: str,
    masked_filename:str,
    file_hash: str,
    entity_count: int,
) -> Optional[bool]:
    
    await db.execute(
    """
    INSERT INTO pii_masking_sessions
        (session_id, original_filename, masked_filename, file_hash, entity_count) VALUES (?, ?, ?, ?, ?)
    """,
    (session_id, original_filename, masked_filename, file_hash, entity_count)
    )

    await db.commit()
    
    return True

# Delete Session

async def delete_session_by_hash(db: aiosqlite.Connection, 
                              hash: str
                              ) -> Optional[dict[str, str]]:
    await db.execute(
        "DELETE * FROM pii_masking_sessions WHERE file_hash = ?", (hash,)
        )
    
    await db.commit()
    return db.total_changes > 0


async def delete_session_by_session_id(db: aiosqlite.Connection, 
                              session_id: str
                              ) -> Optional[dict[str, str]]:
    await db.execute(
        "DELETE * FROM pii_masking_sessions WHERE session_id = ?", (session_id,)
        )
    
    await db.commit()
    return db.total_changes > 0

# Insert Mapping

async def insert_mapping(
    db: aiosqlite.Connection, 
    session_id: str,
    mappings: list[dict[str, str]],
) -> Optional[bool]:
    
    if not mappings:
        return None
    
    await db.execute(
    """
    INSERT INTO pii_masking_mappings
        (session_id, entity_type, original_value, masked_value) VALUES (?, ?, ?, ?)
    """,
    [
        (session_id,m["entity_type"], m["original_value"], m["masked_value"]) 
        for m in mappings
    ] 
    )
    await db.commit()
    return True
    
# Get Session Mapping with Session Id

async def get_mappings_by_session_id(db: aiosqlite.Connection, 
                              session_id: str
                              ) -> list[dict[str, str]]:
    async with db.execute(
        "SELECT * FROM pii_masking_mappings WHERE session_id = ? ORDER BY id", (session_id)
        ) as c:
        rows = await c.fetchall()
    return [dict(row) for row in rows]

# Get all sessions

async def get_all_session(db: aiosqlite.Connection) -> list[dict[str, str]]:
    async with db.execute(
        "SELECT * FROM pii_masking_sessions ORDER BY created_at DESC"
        ) as c:
        rows = await c.fetchall()
    return [dict(row) for row in rows]



