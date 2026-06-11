from __future__ import annotations

from typing import Any

from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict, Field

class TextChunk(BaseModel):
    
    model_config = ConfigDict(frozen=True)
    
    chunk_id: int = Field(..., ge=0)
    text: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    
class BaseIngestor(ABC):
    
    @abstractmethod
    def ingest(self, file_path: str) -> list[TextChunk]:
        return []
    

