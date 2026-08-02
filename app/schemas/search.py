from typing import Optional, Any
from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    question: str           = Field(..., min_length=3, description='السؤال أو العبارة')
    top_k:    int           = Field(6,  ge=1, le=20)
    category: Optional[str] = None
    project:  Optional[str] = None


class ChunkResult(BaseModel):
    id:           str
    file_name:    str
    title:        Optional[str]
    category:     str
    folder:       str
    score:        float
    chunk_text:   str
    token_estimate: Optional[int]
    metadata:     Optional[Any]


class SearchResponse(BaseModel):
    question:    str
    results:     list[ChunkResult]
    total:       int
    search_ms:   int
