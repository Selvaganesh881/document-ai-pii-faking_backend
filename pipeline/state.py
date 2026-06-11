from __future__ import annotations

from typing import Optional, TypedDict

class Pipeline_State(TypedDict, total=False):
    input_file: str
    output_dir: str
    
    file_hash: str
    cache_hit: bool
    
    session_id: str
    masked_filename: str
    
    chunk: list[dict[str,str]]
    
    error: Optional[str]