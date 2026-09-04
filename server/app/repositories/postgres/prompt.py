"""PostgreSQL prompt override repository."""
from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from app.database import SessionLocal
from app.domain.prompt import AgentName, AgentPrompt
from app.models import AgentPromptRecord
from app.repositories.postgres.common import translate
from app.repositories.contracts import Page
from app.repositories.postgres.common import decode_offset, encode_offset, validate_limit

class PostgresPromptRepository:
    def __init__(self, session_factory=None): self.session_factory = session_factory or SessionLocal
    def list(self, *, limit: int = 100, continuation_token: str | None = None) -> Page[AgentPrompt]:
        validate_limit(limit);offset=decode_offset(continuation_token)
        try:
            with self.session_factory() as session: rows = session.scalars(select(AgentPromptRecord).order_by(AgentPromptRecord.agent).offset(offset).limit(limit+1)).all()
        except SQLAlchemyError as error: translate(error)
        return Page(tuple(AgentPrompt(agent=row.agent, prompt=row.prompt, is_custom=True, updated_at=row.updated_at) for row in rows[:limit]),encode_offset(offset,limit) if len(rows)>limit else None)
    def get(self, agent: AgentName) -> AgentPrompt | None:
        try:
            with self.session_factory() as session: row = session.get(AgentPromptRecord, agent)
        except SQLAlchemyError as error: translate(error)
        return AgentPrompt(agent=agent, prompt=row.prompt, is_custom=True, updated_at=row.updated_at) if row else None
    def save(self, agent: AgentName, prompt: str) -> AgentPrompt:
        now = datetime.now(timezone.utc)
        try:
            with self.session_factory.begin() as session:
                row = session.get(AgentPromptRecord, agent)
                if row is None: row = AgentPromptRecord(agent=agent, prompt=prompt, updated_at=now); session.add(row)
                else: row.prompt = prompt; row.updated_at = now
        except SQLAlchemyError as error: translate(error)
        return AgentPrompt(agent=agent, prompt=prompt, is_custom=True, updated_at=now)
    def reset(self, agent: AgentName) -> bool:
        try:
            with self.session_factory.begin() as session:
                row = session.get(AgentPromptRecord, agent)
                if row is None: return False
                session.delete(row)
        except SQLAlchemyError as error: translate(error)
        return True
