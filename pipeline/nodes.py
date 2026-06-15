from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from extraction.llm_extractor import LLMExtractor

# Import your core engines
from ingestion.pdf_ingestor import PDFIngestor
from masking.db import repository
from masking.db.connection import get_db
from masking.faker_engine import PIIFakerEngine
from masking.recognizer import PIIRecognizer
from utils import calculate_file_hash

from pipeline.state import Pipeline_State

logger = logging.getLogger(__name__)


async def hash_and_check_cache_node(state: Pipeline_State) -> Pipeline_State:
    """Calculates file hash and checks SQLite for existing processed sessions."""
    file_path = Path(state["input_file"])
    file_hash = calculate_file_hash(file_path)

    async with get_db() as db:
        existing_session = await repository.get_session_by_hash(db, file_hash)

    if existing_session:
        logger.info("Cache hit! Document already processed.")
        return {
            **state,
            "file_hash": file_hash,
            "cache_hit": True,
            "session_id": existing_session["session_id"],
        }

    return {
        **state,
        "file_hash": file_hash,
        "cache_hit": False,
        "session_id": str(uuid.uuid4()),
    }


async def ingest_document_node(state: Pipeline_State) -> Pipeline_State:
    """Reads PDF and populates the state chunk list."""
    if state.get("cache_hit"):
        return state  # Skip if already processed

    ingestor = PDFIngestor()
    chunks = await ingestor.ingest(state["input_file"])

    # Convert TextChunk objects to dicts for the LangGraph State
    chunk_dicts = [{"chunk_id": str(c.chunk_id), "text": c.text} for c in chunks]

    # Capture the full original string
    full_original = "\n\n".join([c.text for c in chunks])

    return {**state, "chunk": chunk_dicts, "original_text": full_original}


async def mask_pii_node(state: Pipeline_State) -> Pipeline_State:
    """Runs RoBERTa/Presidio, masks text via Faker, and logs to SQLite."""
    if state.get("cache_hit"):
        return state

    recognizer = PIIRecognizer()
    faker = PIIFakerEngine()

    masked_chunks = []

    # entity_type_tracker: dict[str, str] = {}

    for c in state["chunk"]:
        entities = await recognizer.analyze(c["text"])
        #     for entity in entities:
        #         if entity.text.strip() not in entity_type_tracker:
        #             entity_type_tracker[entity.text.strip()] = entity.entity_type
        masked_text = faker.mask_text(c["text"], entities)
        masked_chunks.append({"chunk_id": c["chunk_id"], "text": masked_text})

    # Save session and mappings to SQLite
    db_mappings = [
        {
            "entity_type": faker.entity_types.get(orig, "UNKNOWN"),
            "original_value": orig,
            "masked_value": fake,
        }
        for (orig, fake) in faker.global_mapping.items()
    ]

    async with get_db() as db:
        await repository.insert_session(
            db=db,
            session_id=state["session_id"],
            original_filename=Path(state["input_file"]).name,
            masked_filename=f"masked_{state['session_id']}.md",
            file_hash=state["file_hash"],
            entity_count=len(db_mappings),
        )
        await repository.insert_mapping(db, state["session_id"], db_mappings)

    full_masked = "\n\n".join([c["text"] for c in masked_chunks])

    return {**state, "chunk": masked_chunks, "masked_text": full_masked}


async def extract_llm_node(state: Pipeline_State) -> Pipeline_State:
    """Passes the fully masked markdown to Qwen3-4B vLLM for JSON extraction."""
    if state.get("cache_hit"):
        return state  # Ideally, fetch existing JSON from DB here

    extractor = LLMExtractor()

    # Combine all chunk text into a single payload for the LLM
    full_masked_text = "\n\n".join([c["text"] for c in state["chunk"]])

    logger.info(f"[{state['session_id']}] Executing Qwen3-4B structured extraction...")

    extraction_result = await extractor.extract_structured_data(
        text_payload=full_masked_text,
        user_instruction=state["user_instruction"],
        json_schema=state["json_schema"],
    )

    if "error" in extraction_result:
        return {**state, "error": extraction_result["error"]}

    return {**state, "extracted_json": extraction_result}


# Add this function to the bottom of pipeline/nodes.py


async def unmask_pii_node(state: Pipeline_State) -> Pipeline_State:
    """Retrieves mappings from DB and restores original values in the extracted JSON."""
    if "error" in state or "extracted_json" not in state:
        return state

    session_id = state["session_id"]

    # 1. Fetch the mappings from SQLite
    async with get_db() as db:
        mappings = await repository.get_mappings_by_session_id(db, session_id)

    if not mappings:
        return {**state, "unmasked_json": state["extracted_json"]}

    # 2. Build reverse dictionary: { "Fake_Name": "Real_Name" }
    # CRITICAL: Sort by length descending. This prevents partial word replacements
    # (e.g., preventing "Fake_1" from accidentally replacing the start of "Fake_10")
    sorted_mappings = sorted(
        mappings, key=lambda m: len(m["masked_value"]), reverse=True
    )
    reverse_map = {m["masked_value"]: m["original_value"] for m in sorted_mappings}

    # 3. Recursive unmasking function
    def restore_values(data: Any) -> Any:
        if isinstance(data, dict):
            return {k: restore_values(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [restore_values(item) for item in data]
        elif isinstance(data, str):
            restored_str = data
            for fake_val, real_val in reverse_map.items():
                if fake_val in restored_str:
                    restored_str = restored_str.replace(fake_val, real_val)
            return restored_str
        else:
            return data  # Ints, floats, booleans pass through untouched

    # 4. Execute restoration
    final_json = restore_values(state["extracted_json"])

    logger.info(f"[{session_id}] PII successfully unmasked in final JSON.")
    return {"unmasked_json": final_json}
