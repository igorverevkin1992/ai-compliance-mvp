import os
import shutil
from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Form, Body
from celery.result import AsyncResult
from tasks import analyze_media_task
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

# Импорты БД
from database import SessionLocal, AnalysisRecord

app = FastAPI(title="AI-Lawyer Async Backend")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# Модель данных для верификации
class VerificationRequest(BaseModel):
    record_id: int
    verified_json: List[Dict[str, Any]]
    rating: Optional[int] = 5
    user_comment: Optional[str] = ""


@app.post("/analyze")
async def start_analysis(
    file: UploadFile = File(...),
    original_filename: str = Form(None),
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    try:
        real_name = original_filename if original_filename else file.filename
        save_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        task = analyze_media_task.delay(save_path, real_name, x_api_key)
        return {"task_id": task.id, "status": "Queued"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status/{task_id}")
async def get_task_status(task_id: str):
    task_result = AsyncResult(task_id)
    response = {"task_id": task_id, "state": task_result.state}
    if task_result.state == "PROGRESS":
        response["status"] = task_result.info.get("status", "Processing...")
    elif task_result.state == "SUCCESS":
        response["result"] = task_result.result
    elif task_result.state == "FAILURE":
        response["error"] = str(task_result.result)
    return response


# --- НОВЫЙ ЭНДПОИНТ: СОХРАНЕНИЕ РАЗМЕТКИ ---
@app.put("/verify")
async def verify_analysis(req: VerificationRequest):
    try:
        db = SessionLocal()
        record = (
            db.query(AnalysisRecord).filter(AnalysisRecord.id == req.record_id).first()
        )

        if not record:
            db.close()
            raise HTTPException(status_code=404, detail="Record not found")

        # Обновляем запись
        record.verified_result_json = req.verified_json
        record.is_verified = True
        record.rating = req.rating
        record.user_comment = req.user_comment

        db.commit()
        db.close()
        return {"status": "success", "message": "Data saved for fine-tuning"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
