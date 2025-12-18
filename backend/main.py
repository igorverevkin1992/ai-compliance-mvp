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
from tasks import get_embedding

app = FastAPI(title="AI-Lawyer Enterprise Backend")

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- МОДЕЛИ ДАННЫХ ---

# Обновленная модель для сохранения правки
class VerificationRequest(BaseModel):
    asset_id: str
    verified_json: Dict[str, Any] = {} # ИСПРАВЛЕНО: теперь принимает словарь (весь отчет)
    rating: Optional[int] = 5
    user_comment: Optional[str] = None
    final_risk: Optional[str] = "UNKNOWN"

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

@app.put("/verify")
async def verify_analysis(req: VerificationRequest, x_api_key: str = Header(..., alias="X-API-Key")):
    try:
        db = SessionLocal()
        
        # 1. Создаем эмбеддинг для комментария учителя
        # Мы "математизируем" логику: почему это SAFE или HIGH
        vector = None
        if req.user_comment:
            from tasks import get_embedding # Импорт внутри чтобы избежать циклов
            vector = get_embedding(req.user_comment, x_api_key)

        # 2. Сохраняем в human_review (основной лог)
        sql_review = text("""
            INSERT INTO human_review (asset_id, final_risk, notes, status, verified_json)
            VALUES (:aid, :risk, :notes, 'DONE', :v_json)
            RETURNING id
        """)
        review_res = db.execute(sql_review, {
            "aid": req.asset_id, "risk": req.final_risk, 
            "notes": req.user_comment, "v_json": json.dumps(req.verified_json)
        }).fetchone()

        # 3. Сохраняем в ВЕКТОРНУЮ ПАМЯТЬ (case_memory)
        if vector:
            sql_memory = text("""
                INSERT INTO case_memory (review_id, memory_type, text, embedding, meta)
                VALUES (:rid, 'HUMAN_CORRECTION', :txt, :vec, :meta)
            """)
            db.execute(sql_memory, {
                "rid": review_res.id,
                "txt": req.user_comment,
                "vec": str(vector),
                "meta": json.dumps({"final_risk": req.final_risk})
            })
        
        db.commit()
        db.close()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))