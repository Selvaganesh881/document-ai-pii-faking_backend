from __future__ import annotations

import aiosqlite

CREATE_SESSIONS = """
CREATE TABLE IF NOT EXISTS pii_masking_sessions(
    session_id TEXT PRIMARY KEY,
    original_filename TEXT NOT NULL,
    masked_filename TEXT NOT NULL,
    file_hash TEXT NOT NULL UNIQUE,
    entity_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
"""
CREATE_MAPPINGS = """
CREATE TABLE IF NOT EXISTS pii_masking_mappings(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL REFERENCES pii_masking_sessions(session_id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    original_value TEXT NOT NULL,
    masked_value TEXT NOT NULL
);
"""

CREATE_INDEX = [
    "CREATE INDEX IF NOT EXISTS idx_sessions_file_hash ON pii_masking_sessions(file_hash);",
    "CREATE INDEX IF NOT EXISTS idx_mappings_session_id ON pii_masking_mappings(session_id);",
    "CREATE INDEX IF NOT EXISTS idx_mappings_masked_value ON pii_masking_mappings(masked_value);"   
]

async def initialize_schema(db: aiosqlite.connection) -> None:
    await db.execute(CREATE_SESSIONS)
    await db.execute(CREATE_MAPPINGS)
    for sql_statement in CREATE_INDEX:
        await db.execute(sql_statement)
    
    await db.commit()
    