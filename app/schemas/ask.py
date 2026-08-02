from typing import Optional
from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question:     str            = Field(..., min_length=3, description='السؤال')
    top_k:        int            = Field(6,  ge=1, le=20, description='عدد المصادر')
    category:     Optional[str]  = Field(None, description='core/domain/project/playbook/template/example/evaluation/prompt')
    project:      Optional[str]  = Field(None, description='اسم المشروع')
    task_type:    Optional[str]  = Field(None, description='diagnosis/strategy/brief/debug/...')
    show_sources: bool           = Field(True, description='هل ترجع المصادر مع الإجابة؟')


class SourceItem(BaseModel):
    file_name: str
    title:     Optional[str]
    category:  str
    score:     float
    chunk_text: str


class AskResponse(BaseModel):
    answer:      str
    sources:     list[SourceItem]
    model:       str
    tokens_used: int
    search_ms:   int
    llm_ms:      int
