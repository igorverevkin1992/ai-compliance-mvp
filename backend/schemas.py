from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field

# 1. Доказательства (Evidence)
class EvidenceItem(BaseModel):
    id: str
    type: Literal["transcript_span", "audio_span", "frame_span", "metadata"]
    start_ms: Optional[int] = 0
    end_ms: Optional[int] = 0
    text_quote: Optional[str] = ""
    notes: Optional[str] = ""

# 2. Сработавшие Политики (из НТВ документа)
class PolicyHit(BaseModel):
    req_code: str # Например: NTV_AGE18_001
    priority: Literal["P0", "P1", "P2"]
    why: str
    evidence_ids: List[str] = []

# 3. Найденные нарушения (Labels)
class LabelDetection(BaseModel):
    code: str  # Например: EXTREMISM_CALLS
    severity: int = Field(..., ge=0, le=3)
    confidence: float = Field(..., ge=0.0, le=1.0)
    rationale: str
    evidence_ids: List[str] = []
    policy_refs: List[str] = [] # Ссылки на PolicyHit

# 4. Рекомендации монтажеру
class Recommendation(BaseModel):
    action: Literal["CUT", "BLEEP", "BLUR", "AGE_GATE", "DISCLAIMER", "REMOVE_LOGO", "LEGAL_REVIEW"]
    priority: Literal["P0", "P1", "P2"]
    target_evidence_ids: List[str] = []
    params: Dict[str, Any] = {}
    expected_effect: str

# 5. Итог (Overall)
class OverallAssessment(BaseModel):
    risk_level: Literal["SAFE", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
    confidence: float
    age_rating: str # 0+, 6+, 12+, 16+, 18+
    summary: str

# --- ГЛАВНАЯ СХЕМА ОТВЕТА ---
class ComplianceReport(BaseModel):
    schema_version: str = "1.1"
    overall: OverallAssessment
    labels: List[LabelDetection] = []
    evidence: List[EvidenceItem] = []
    policy_hits: List[PolicyHit] = []
    recommendations: List[Recommendation] = []