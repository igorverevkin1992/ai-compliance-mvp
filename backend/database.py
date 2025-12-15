import os
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    JSON,
    DateTime,
    Boolean,
    Text,
)
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

# Получаем URL из docker-compose
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://admin:adminpassword@db:5432/ailawyer_db"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class AnalysisRecord(Base):
    """
    Таблица для хранения истории проверок.
    """

    __tablename__ = "analysis_records"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String)
    file_type = Column(String)  # 'media' или 'text'
    created_at = Column(DateTime, default=datetime.utcnow)

    # То, что выдал AI (Original)
    ai_result_json = Column(JSON)

    # То, что исправил человек (Golden Set для обучения)
    verified_result_json = Column(JSON, nullable=True)

    # Метаданные проверки
    is_verified = Column(Boolean, default=False)
    user_comment = Column(Text, nullable=True)
    rating = Column(Integer, default=0)  # Оценка качества работы AI (1-5)


def init_db():
    """Создает таблицы в базе, если их нет"""
    Base.metadata.create_all(bind=engine)
