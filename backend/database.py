import os
from sqlalchemy import create_engine, Column, Integer, String, JSON, DateTime, Boolean, Text, ForeignKey, Float
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.dialects.postgresql import UUID, ARRAY
import uuid
from datetime import datetime

# Получаем URL из окружения
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 1. Ассеты (Файлы)
class MediaAsset(Base):
    __tablename__ = "media_asset"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String, nullable=False)
    source_uri = Column(String)
    mime_type = Column(String)
    duration_ms = Column(Integer, default=0)
    metadata_json = Column("metadata", JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)

# 2. Результаты работы Агента (Runs)
class AgentRun(Base):
    __tablename__ = "agent_run"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("media_asset.id", ondelete="CASCADE"))
    model = Column(String, nullable=False)
    output_json = Column(JSON)
    overall_risk = Column(String)
    overall_confidence = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

# 3. Доказательства (Evidence)
class Evidence(Base):
    __tablename__ = "evidence"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("media_asset.id", ondelete="CASCADE"))
    type = Column(String) # audio_span, frame_span...
    start_ms = Column(Integer, default=0)
    end_ms = Column(Integer, default=0)
    payload = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)

# 4. Найденные нарушения (Detections)
class LabelDetection(Base):
    __tablename__ = "label_detection"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("agent_run.id", ondelete="CASCADE"))
    label_code = Column(String, nullable=False)
    severity = Column(Integer)
    confidence = Column(Float)
    rationale = Column(Text)
    evidence_ids = Column(ARRAY(UUID(as_uuid=True))) # Массив ссылок на Evidence
    created_at = Column(DateTime, default=datetime.utcnow)

# 5. Рекомендации (Recommendations)
class Recommendation(Base):
    __tablename__ = "recommendation"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("agent_run.id", ondelete="CASCADE"))
    action = Column(String)
    priority = Column(String)
    params = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)

# 6. Юридические требования (Policies)
class LegalDoc(Base):
    __tablename__ = "legal_doc"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    publisher = Column(String, nullable=False) # НТВ, YouTube
    title = Column(String, nullable=False)
    version = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class LegalRequirement(Base):
    __tablename__ = "legal_requirement"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doc_id = Column(UUID(as_uuid=True), ForeignKey("legal_doc.id", ondelete="CASCADE"))
    req_code = Column(String, unique=True, nullable=False)
    requirement_type = Column(String)
    risk_floor = Column(String)
    summary = Column(String, nullable=False)
    full_text = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

# 7. Проверки Человеком (Human Review)
class HumanReview(Base):
    __tablename__ = "human_review"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("media_asset.id", ondelete="CASCADE"))
    run_id = Column(UUID(as_uuid=True), ForeignKey("agent_run.id", ondelete="SET NULL"), nullable=True)
    status = Column(String, default="DONE")
    final_risk = Column(String)
    notes = Column(Text)
    verified_json = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

# 8. Векторная Память (Case Memory / RAG)
class CaseMemory(Base):
    __tablename__ = "case_memory"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id = Column(UUID(as_uuid=True), ForeignKey("human_review.id", ondelete="SET NULL"), nullable=True)
    memory_type = Column(String)
    text = Column(Text, nullable=False)
    meta = Column(JSON, default={})
    # Храним как текст для совместимости, в SQL будем кастить в vector
    embedding = Column(Text) 

def init_db():
    Base.metadata.create_all(bind=engine)