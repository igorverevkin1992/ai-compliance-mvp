import os
import json
import re
import subprocess
import asyncio
import google.generativeai as genai
from sqlalchemy import text

# Наши модули
from celery_app import app
from prompts.instructions import SYSTEM_PROMPT_TEMPLATE
from shazam_helper import recognize_music
from database import SessionLocal, init_db

# --- НАСТРОЙКИ БЕЗОПАСНОСТИ (ОТКЛЮЧАЕМ ЦЕНЗУРУ) ---
# Это критически важно для модерации контента.
# Мы разрешаем модели видеть всё, чтобы она могла найти нарушения.
SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def clean_json_text(text: str) -> str:
    # Удаляем Markdown ```json ... ```
    text = re.sub(r"^```json\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^```\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"```$", "", text, flags=re.MULTILINE)
    return text.strip()

def compress_audio_ffmpeg(input_path: str) -> str:
    output_path = f"{os.path.splitext(input_path)[0]}_compressed.m4a"
    command = ["ffmpeg", "-y", "-i", input_path, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "aac", output_path]
    try:
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_path if os.path.exists(output_path) else None
    except: return None

def upload_to_gemini(path: str, mime_type: str):
    try: return genai.upload_file(path, mime_type=mime_type)
    except: return None

def get_rag_context(db):
    # 1. Политики
    policies = db.execute(text("SELECT req_code, summary, full_text FROM legal_requirement")).fetchall()
    policies_text = "\n".join([f"- [{p.req_code}] {p.summary}: {p.full_text[:200]}..." for p in policies])

    # 2. Таксономия
    taxonomy = db.execute(text("SELECT code, title FROM taxonomy_label")).fetchall()
    taxonomy_text = "\n".join([f"- {t.code}: {t.title}" for t in taxonomy])

    # 3. Примеры (RAG)
    # ИСПРАВЛЕНО: 
    # 1. Убрали 'is_verified=true' (такой колонки нет).
    # 2. Сортируем по created_at (так как id теперь UUID и не имеют порядка).
    reviews = db.execute(text("""
        SELECT notes, verified_json 
        FROM human_review 
        WHERE verified_json IS NOT NULL 
        ORDER BY created_at DESC 
        LIMIT 5
    """)).fetchall()
    
    human_examples = "Нет примеров."
    if reviews:
        examples_list = []
        for r in reviews:
            # Формируем читаемый пример
            if r.notes:
                examples_list.append(f"СИТУАЦИЯ: {r.notes}")
        
        if examples_list:
            human_examples = "\n\n".join(examples_list)

    return policies_text, taxonomy_text, human_examples

def save_results_to_db(db, asset_id, result_json):
    # 1. Agent Run
    risk = result_json.get('overall', {}).get('risk_level', 'UNKNOWN')
    conf = result_json.get('overall', {}).get('confidence', 0.0)
    
    run_res = db.execute(text("""
        INSERT INTO agent_run (asset_id, model, output_json, overall_risk, overall_confidence)
        VALUES (:aid, 'gemini-2.5-flash', :json, :risk, :conf)
        RETURNING id
    """), {"aid": asset_id, "json": json.dumps(result_json), "risk": risk, "conf": conf}).fetchone()
    run_id = run_res.id

    # 2. Evidence
    evidence_map = {}
    for ev in result_json.get('evidence', []):
        pay = {"text": ev.get('text_quote'), "notes": ev.get('notes')}
        ev_res = db.execute(text("""
            INSERT INTO evidence (asset_id, type, start_ms, end_ms, payload)
            VALUES (:aid, :type, :start, :end, :pay)
            RETURNING id
        """), {
            "aid": asset_id, "type": ev.get('type'), 
            "start": ev.get('start_ms', 0), "end": ev.get('end_ms', 0), 
            "pay": json.dumps(pay)
        }).fetchone()
        evidence_map[ev.get('id')] = ev_res.id

    # 3. Labels
    for lbl in result_json.get('labels', []):
        # Превращаем текстовые ID (e1) в UUID базы
        db_ev_ids = [evidence_map[eid] for eid in lbl.get('evidence_ids', []) if eid in evidence_map]
        
        db.execute(text("""
            INSERT INTO label_detection (run_id, label_code, severity, confidence, rationale, evidence_ids)
            VALUES (:rid, :code, :sev, :conf, :rat, :evs)
        """), {
            "rid": run_id, "code": lbl.get('code'), "sev": lbl.get('severity'),
            "conf": lbl.get('confidence'), "rat": lbl.get('rationale'),
            "evs": db_ev_ids
        })

    # 4. Recommendations
    for rec in result_json.get('recommendations', []):
        db.execute(text("""
            INSERT INTO recommendation (run_id, action, priority, params)
            VALUES (:rid, :act, :prio, :par)
        """), {
            "rid": run_id, "act": rec.get('action'), "prio": rec.get('priority'),
            "par": json.dumps(rec.get('params'))
        })
        
    db.commit()
    return run_id

# --- MAIN TASK ---

@app.task(bind=True)
def analyze_media_task(self, file_path: str, filename: str, api_key: str):
    files_cleanup = []
    compressed_path = None
    
    try:
        # Настройка
        genai.configure(api_key=api_key)
        MODEL_NAME = "gemini-2.5-flash" 

        # Обработка медиа
        self.update_state(state='PROGRESS', meta={'status': 'Сжатие и анализ аудио...'})
        compressed_path = compress_audio_ffmpeg(file_path)
        target_file = compressed_path if compressed_path else file_path
        mime_type = "audio/mp4"

        # Shazam
        shazam_text = ""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            res = loop.run_until_complete(recognize_music(target_file))
            loop.close()
            if res: shazam_text = f"SHAZAM IDENTIFICATION: {res}"
        except: pass

        # Загрузка
        self.update_state(state='PROGRESS', meta={'status': 'Загрузка в Gemini...'})
        media_f = upload_to_gemini(target_file, mime_type)
        if not media_f: return {"error": "Upload failed"}
        files_cleanup.append(media_f)

        # Контекст из базы
        db = SessionLocal()
        policies, taxonomy, examples = get_rag_context(db)
        
        prompt = SYSTEM_PROMPT_TEMPLATE.format(
            policies_text=policies,
            taxonomy_text=taxonomy,
            human_examples=examples
        )
        
        content = [prompt, f"Файл: {filename}. {shazam_text}", media_f]

        # ГЕНЕРАЦИЯ С ОТКЛЮЧЕННЫМИ ФИЛЬТРАМИ
        self.update_state(state='PROGRESS', meta={'status': 'AI думает (Deep Analysis)...'})
        
        model = genai.GenerativeModel(MODEL_NAME)
        
        # Добавляем safety_settings
        response = model.generate_content(
            content,
            generation_config={"response_mime_type": "application/json"},
            safety_settings=SAFETY_SETTINGS
        )
        
        # Проверка на блокировку
        if not response.text:
            print(f"DEBUG: Response blocked? {response.prompt_feedback}")
            return {"error": "AI отказался отвечать из-за Safety Filters (хотя мы просили отключить). Попробуйте позже."}

        # Парсинг
        result_data = json.loads(clean_json_text(response.text))
        
        # Сохранение
        init_db()
        asset_res = db.execute(text("INSERT INTO media_asset (filename, duration_ms) VALUES (:fn, 0) RETURNING id"), {"fn": filename}).fetchone()
        asset_id = asset_res.id
        
        save_results_to_db(db, asset_id, result_data)
        
        db.close()
        
        # Добавляем ID для фронтенда
        result_data['_asset_id'] = str(asset_id)
        return result_data

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        return {"error": str(e)}
    finally:
        for f in files_cleanup: 
            try: f.delete() 
            except: pass
        if compressed_path and os.path.exists(compressed_path): 
            os.remove(compressed_path)