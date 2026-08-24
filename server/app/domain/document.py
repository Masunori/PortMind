"""Contracts for normalized documents and collection results."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class DocumentStatus(str, Enum):
    """Represent document processing progress."""

    NEW = "NEW"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class RawDocument(BaseModel):
    """Return normalized source content with immutable provenance."""

    id: str
    source_id: str
    title: str
    source_url: str | None
    media_type: str
    content: str
    content_hash: str
    status: DocumentStatus
    error: str | None
    collected_at: datetime
    created_at: datetime


class DocumentCreate(BaseModel):
    """Fields needed to persist extracted source content."""

    source_id: str
    title: str = Field(min_length=1, max_length=500)
    source_url: str | None = None
    media_type: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    collected_at: datetime | None = None


class DocumentStoreResult(BaseModel):
    """Report whether collection created or deduplicated a document."""

    document: RawDocument
    created: bool
