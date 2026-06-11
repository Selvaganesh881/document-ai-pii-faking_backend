import pytest
from pathlib import Path
import os

import aiosqlite

from typing import AsyncGenerator

from masker.db.schema import initialize_schema

# Initialize Test Config

@pytest.fixture()
def config_yaml(tem_path: Path = Path("./tests")) -> Path:
    p = tem_path / "config_test.yaml"
    p.write_text(
        "model_name: roberta-base\n"
        "model_path: ./store_api/roberta-pii\n"
        "model_threshold: 0.5\n",
        encoding="utf-8"
    )
    return p

# Initialize Test DB

@pytest.fixture(autouse=True, scope= "session")
async def db_clean(tem_path: Path = Path("./tests")):
    db_path: Path = tem_path / "test.db"
    os.remove(db_path)
    

@pytest.fixture()
async def db(tem_path: Path = Path("./tests")):
    db_path: Path = tem_path / "test.db"
    #db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        await initialize_schema(db)
        yield db


        

    
    
