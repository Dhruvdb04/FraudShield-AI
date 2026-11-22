"""SQLite tables for the analyst and scored transactions."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import NullPool

from backend.app.config import ensure_dirs, sqlite_url


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    hour: Mapped[float] = mapped_column(Float, nullable=False)
    country_risk: Mapped[float] = mapped_column(Float, nullable=False)
    device_trust: Mapped[float] = mapped_column(Float, nullable=False)
    velocity_1h: Mapped[float] = mapped_column(Float, nullable=False)
    merchant_category: Mapped[int] = mapped_column(Integer, nullable=False)
    card_age_days: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_from_home_km: Mapped[float] = mapped_column(Float, nullable=False)
    is_international: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    model_decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    rules_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    label: Mapped[int | None] = mapped_column(Integer, nullable=True)
    explanation_json: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey("transactions.transaction_id"),
        unique=True,
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    analyst_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


engine = create_engine(sqlite_url(), connect_args={"check_same_thread": False}, poolclass=NullPool)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _migrate() -> None:
    """Add rule columns on databases created before the case queue."""
    with engine.begin() as conn:
        tables = {
            str(row[0])
            for row in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "transactions" not in tables:
            return
        columns = {str(row[1]) for row in conn.exec_driver_sql("PRAGMA table_info(transactions)")}
        if "model_decision" not in columns:
            conn.exec_driver_sql("ALTER TABLE transactions ADD COLUMN model_decision VARCHAR(16)")
        if "rules_json" not in columns:
            conn.exec_driver_sql("ALTER TABLE transactions ADD COLUMN rules_json TEXT")


def init_db() -> None:
    ensure_dirs()
    Base.metadata.create_all(engine)
    _migrate()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
