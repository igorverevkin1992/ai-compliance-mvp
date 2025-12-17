import os
import shutil
import google.generativeai as genai
from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Form
from celery.result import AsyncResult
from tasks import analyze_media_task
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from sqlalchemy import text # Используем прямой SQL для надежности
from database import SessionLocal

app = FastAPI(title="AI-Lawyer Enterprise Backend")

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- МОДЕЛИ ДАННЫХ ---

# Обновленная модель для сохранения правки
class VerificationRequest(BaseModel):
    asset_id: str  # ТЕПЕРЬ ЭТО СТРОКА (UUID)
    verified_json: List[Dict[str, Any]] = []
    rating: Optional[int] = 5
    user_comment: Optional[str] = None
    final_risk: Optional[str] = "UNKNOWN" # Новый уровень риска от учителя

class ApiKeyRequest(BaseModel):
    api_key: str

# --- ЭНДПОИНТЫ ---

@app.post("/list-models")
async def list_google_models(req: ApiKeyRequest):
    try:
        genai.configure(api_key=req.api_key)
        models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods and "gemini" in m.name:
                models.append(m.name.replace("models/", ""))
        models.sort(reverse=True)
        return {"models": models}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/analyze")
async def start_analysis(
    file: UploadFile = File(...), 
    original_filename: str = Form(None),
    model_name: str = Form("gemini-1.5-flash"),
    profile: str = Form("ntv"), # <--- НОВОЕ ПОЛЕ
    x_api_key: str = Header(..., alias="X-API-Key")
):
    try:
        real_name = original_filename if original_filename else file.filename
        save_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        task = analyze_media_task.delay(save_path, real_name, x_api_key, model_name, profile)
        return {"task_id": task.id, "status": "Queued"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status/{task_id}")
async def get_task_status(task_id: str):
    task_result = AsyncResult(task_id)
    response = {"task_id": task_id, "state": task_result.state}
    if task_result.state == 'PROGRESS':
        response["status"] = task_result.info.get('status', 'Processing...')
    elif task_result.state == 'SUCCESS':
        response["result"] = task_result.result
    elif task_result.state == 'FAILURE':
        response["error"] = str(task_result.result)
    return response

# --- НОВЫЙ ЭНДПОИНТ СОХРАНЕНИЯ (UUID SUPPORT) ---
@app.put("/verify")
async def verify_analysis(req: VerificationRequest):
    try:
        db = SessionLocal()
        
        # Мы сохраняем это в таблицу human_review
        # Используем Raw SQL, чтобы точно попасть в новую структуру v6.0
        sql = text("""
            INSERT INTO human_review (asset_id, final_risk, notes, status, created_at)
            VALUES (:aid, :risk, :notes, 'DONE', now())
            RETURNING id
        """)
        
        result = db.execute(sql, {
            "aid": req.asset_id,      # UUID ассета
            "risk": req.final_risk,   # SAFE, HIGH...
            "notes": req.user_comment # Комментарий учителя
        })
        
        db.commit()
        db.close()
        return {"status": "success", "message": "Feedback saved to Knowledge Base"}
    
    except Exception as e:
        print(f"DB Error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")