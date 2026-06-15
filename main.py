import json
import os

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware

# Import your LangGraph pipeline
from pipeline.graph import build_pipeline_graph

app = FastAPI()

# --- CORS Configuration ---
# This tells the backend: "It is okay to accept requests from the React frontend running on port 5173"
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Critical: The asterisk allows any frontend to connect
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure upload directory exists
os.makedirs("uploads", exist_ok=True)


@app.post("/api/process")
async def process_document(
    file: UploadFile = File(...),
    user_instruction: str = Form(...),
    json_schema: str = Form(...),
):
    try:
        # 1. Save the uploaded PDF
        file_path = f"uploads/{file.filename}"
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())

        # 2. Parse the schema string into a dictionary
        parsed_schema = json.loads(json_schema)

        # 3. Run your LangGraph Pipeline
        graph_app = build_pipeline_graph()
        initial_state = {
            "input_file": file_path,
            "user_instruction": user_instruction,
            "json_schema": parsed_schema,
        }

        final_state = await graph_app.ainvoke(initial_state)

        response = {
            "status": "success",
            "original_text": final_state.get("original_text", ""),
            "masked_text": final_state.get("masked_text", ""),
            "extracted_json": final_state.get("extracted_json", {}),
            "unmasked_json": final_state.get("unmasked_json", {}),
        }

        if "error" in final_state:
            response["status"] = "error"
            response["message"] = final_state["error"]

        return response

    except Exception as e:
        return {"status": "error", "message": str(e)}


from masking.db import repository
from masking.db.connection import get_db


@app.get("/api/dashboard-stats")
async def get_dashboard_stats():
    try:
        async with get_db() as db:
            # 1. Fetch all sessions from the database
            all_sessions = await repository.get_all_session(db)

            # 2. Calculate the total statistics
            total_documents = len(all_sessions)
            total_entities = sum(
                session.get("entity_count", 0) for session in all_sessions
            )

            # 3. Get the 5 most recent runs for the table
            recent_runs = all_sessions[:5]

            return {
                "status": "success",
                "stats": {
                    "documents_processed": total_documents,
                    "entities_masked": total_entities,
                    "records_in_db": total_documents,  # Usually 1 record per document in this PoC
                },
                "recent_runs": recent_runs,
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def _fetch_results() -> dict[str, object]:
    async with get_db() as db:
        session_rows = await repository.get_all_session(db)

        results = []
        for row in session_rows:
            session_id = row.get("session_id", "")
            mappings = await repository.get_mappings_by_session_id(db, session_id)

            extracted_json = {
                "mappings": [
                    {
                        "entity_type": mapping.get("entity_type", ""),
                        "masked_value": mapping.get("masked_value", ""),
                        "original_value": mapping.get("original_value", ""),
                    }
                    for mapping in mappings
                ]
            }
            unmasked_json = {
                "mappings": [
                    {
                        "entity_type": mapping.get("entity_type", ""),
                        "value": mapping.get("original_value", ""),
                    }
                    for mapping in mappings
                ]
            }

            results.append(
                {
                    "id": session_id,
                    "original_filename": row.get("original_filename", ""),
                    "created_at": row.get("created_at", ""),
                    "status": "complete",
                    "extracted_json": extracted_json,
                    "unmasked_json": unmasked_json,
                }
            )

    return {"status": "success", "results": results}


@app.get("/api/results")
async def get_results():
    try:
        return await _fetch_results()
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/result")
async def get_result():
    try:
        return await _fetch_results()
    except Exception as e:
        return {"status": "error", "message": str(e)}
