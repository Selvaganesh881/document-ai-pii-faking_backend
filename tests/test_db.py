from masker.db.repository import get_all_session, insert_session, get_session_by_session_id
import aiosqlite

async def test_get_all_sessions(db: aiosqlite.Connection):
    data  = await get_all_session(db=db)
    assert isinstance(data, list)
    
    
async def test_insert_sessions(db: aiosqlite.Connection):
    result = await insert_session(
        db=db,
        session_id= "test_session_id",
        original_filename = "test_original_filename",
        masked_filename = "test_masked_filename",
        file_hash= "test_file_hash",
        entity_count= 4,
    )
    assert result == True
    
async def test_get_session_by_session_id(db:aiosqlite.Connection):
    result = await get_session_by_session_id(
        db=db,
        session_id="test_session_id"
    )
    assert result["original_filename"] == "test_original_filename"



