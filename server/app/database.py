"""SQLAlchemy engine, declarative base, and session configuration."""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://psa:psa@localhost:5432/psa",
)


class Base(DeclarativeBase):
    """Base class for all persisted supply-chain models."""

    pass


engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
