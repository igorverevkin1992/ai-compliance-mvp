import os
import json
import re
import subprocess
import asyncio
import time
import random
import google.generativeai as genai
from sqlalchemy import text

from celery_app import app
from prompts.instructions import SYSTEM_PROMPT_TEMPLATE
from shazam_helper import recognize_music
from database import SessionLocal, init_db

# --- НАСТРОЙКИ ---
SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

def clean_json_text(text: str) -> str:
    text = re.sub(r"^```json\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^```\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"```$", "", text, flags=re.MULTILINE)
    return text.strip()

def compress_media(input_path: str) -> tuple[str, str]:
    """
    Возвращает (путь_к_сжатому_файлу, mime_type)
    Если это видео - сжимает размер кадра, но ОСТАВЛЯЕТ ВИДЕО.
    Если аудио - конвертирует в легкий AAC.
    """
    # Определяем, видео это или аудио, с помощью ffprobe (или по расширению)
    ext = input_path.split('.')[-1].lower()
    is_video = ext in ['mp4', 'mov', 'avi', 'mkv', 'webm']
    
    output_filename = f"{os.path.splitext(input_path)[0]}_compressed"
    
    if is_video:
        # Сжимаем ВИДЕО:
        # -vf scale=640:-2 : Уменьшаем ширину до 640px (высота авто), чтобы Gemini видел картинку, но файл был легким
        # -crf 28 : Среднее качество (чем выше число, тем хуже качество и меньше вес)
        # -r 24 : 24 кадра в секунду
        output_path = f"{output_filename}.mp4"
        command = [
            "ffmpeg", "-y", "-i", input_path,
            "-vf", "scale=640:-2", 
            "-c:v", "libx264", "-crf", "28", "-preset", "faster", "-r", "24",
            "-c:a", "aac", "-ac", "1", "-ar", "16000", # Звук тоже сжимаем
            output_path
        ]
        mime = "video/mp4"
    else:
        # Сжимаем АУДИО (как раньше):
        output_path = f"{output_filename}.m4a"
        command = [
            "ffmpeg", "-y", "-i", input_path,
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "aac", 
            output_path
        ]
        mime = "audio/mp4"

    try:
        print(f"🎬 Starting Compression ({mime}) for {input_path}...")
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"✅ Compression success: {output_path} ({size_mb:.2f} MB)")
            return output_path, mime
    except Exception as e:
        print(f"⚠️ FFmpeg Error: {e}")
        # Если сжатие не вышло, вернем оригинал
        return input_path, ("video/mp4" if is_video else "audio/mp3")
    
    return input_path, "application/octet-stream"

def upload_to_gemini(path: str, mime_type: str):
    """Загрузка с жестким ожиданием статуса ACTIVE"""
    print(f"☁️ Загрузка: {path} (Mime: {mime_type})")
    if not os.path.exists(path): return None
    
    try:
        file = genai.upload_file(path, mime_type=mime_type)
        print(f"   Загрузка завершена. Статус: {file.state.name}")
        
        # ЦИКЛ ОЖИДАНИЯ ОБРАБОТКИ
        # Мы должны постоянно опрашивать сервер: "Готово? Готово?"
        start_time = time.time()
        while file.state.name == "PROCESSING":
            print(f"⏳ Обработка ({int(time.time() - start_time)}s)", end="\r")
            time.sleep(2)
            # ВАЖНО: Обновляем объект файла с сервера
            file = genai.get_file(file.name)
            
            # Таймаут 5 минут
            if time.time() - start_time > 300:
                raise Exception("Тайм аут обработки (5 мин).")

        if file.state.name != "ACTIVE":
            raise Exception(f"Ошибка обработка. Статус: {file.state.name}")

        print(f"✅ Файл готов: {file.name}")
        return file
    except Exception as e:
        print(f"❌ Ошибка загрузки: {e}")
        return None

def get_rag_context(db, profile="ntv"):
    try:
        # 1. Определяем фильтр (НТВ или YouTube)
        if profile == "youtube":
            pub_query = "YouTube%"
        else:
            pub_query = "НТВ%"

        # 2. Политики
        sql = text("""
            SELECT r.req_code, r.summary, r.full_text 
            FROM legal_requirement r
            JOIN legal_doc d ON r.doc_id = d.id
            WHERE d.publisher LIKE :pub
        """)
        
        policies = db.execute(sql, {"pub": pub_query}).fetchall()
        
        # Защита: если политик нет, ставим заглушку
        if policies:
            policies_text = "\n".join([f"- [{p.req_code}] {p.summary}: {p.full_text[:300]}..." for p in policies])
        else:
            policies_text = "Нет специфических политик для этого профиля. Используй общие законы РФ."

        # 3. Таксономия (Коды ошибок)
        taxonomy = db.execute(text("SELECT code, title FROM taxonomy_label")).fetchall()
        if taxonomy:
            taxonomy_text = "\n".join([f"- {t.code}: {t.title}" for t in taxonomy])
        else:
            taxonomy_text = "Коды нарушений не загружены в базу."

        # 4. Примеры (RAG)
        reviews = db.execute(text("""
            SELECT notes FROM human_review 
            WHERE verified_json IS NOT NULL 
            ORDER BY created_at DESC LIMIT 5
        """)).fetchall()
        
        human_examples = "Нет примеров."
        if reviews:
            # Фильтруем пустые заметки, чтобы не было ошибок
            valid_notes = [f"СИТУАЦИЯ: {r.notes}" for r in reviews if r.notes]
            if valid_notes:
                human_examples = "\n\n".join(valid_notes)

        # УСПЕХ: Возвращаем 3 значения
        return policies_text, taxonomy_text, human_examples

    except Exception as e:
        print(f"⚠️ RAG Context Error: {e}")
        # ОШИБКА: Возвращаем 3 пустые строки, чтобы программа НЕ УПАЛА
        return "", "", ""

def save_results_to_db(db, asset_id, result_json, model_name):
    try:
        risk = result_json.get('overall', {}).get('risk_level', 'UNKNOWN')
        conf = result_json.get('overall', {}).get('confidence', 0.0)
        
        run_res = db.execute(text("""
            INSERT INTO agent_run (asset_id, model, output_json, overall_risk, overall_confidence)
            VALUES (:aid, :model_name, :json, :risk, :conf)
            RETURNING id
        """), {
            "aid": asset_id,
            "model_name": model_name,  # <--- ВОТ ЭТОГО НЕ ХВАТАЛО
            "json": json.dumps(result_json),
            "risk": risk,
            "conf": conf
        }).fetchone()
        run_id = run_res.id

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

        for lbl in result_json.get('labels', []):
            db_ev_ids = [evidence_map[eid] for eid in lbl.get('evidence_ids', []) if eid in evidence_map]
            db.execute(text("""
                INSERT INTO label_detection (run_id, label_code, severity, confidence, rationale, evidence_ids)
                VALUES (:rid, :code, :sev, :conf, :rat, :evs)
            """), {
                "rid": run_id, "code": lbl.get('code'), "sev": lbl.get('severity'),
                "conf": lbl.get('confidence'), "rat": lbl.get('rationale'),
                "evs": db_ev_ids
            })

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
    except Exception as e:
        print(f"⚠️ DB Save Error: {e}")
        return None

# --- MAIN TASK ---

@app.task(bind=True)
def analyze_media_task(self, file_path: str, filename: str, api_key: str, model_name: str, profile: str = "ntv"):
    # ^^^ ДОБАВИЛ model_name В АРГУМЕНТЫ ^^^
    
    files_cleanup = []
    compressed_path = None
    
    try:
        genai.configure(api_key=api_key)
        
        # ИСПОЛЬЗУЕМ ВЫБРАННУЮ МОДЕЛЬ
        print(f"🤖 Using Model: {model_name}")
        MODEL_NAME = model_name 

        # 1. ОБРАБОТКА (ТЕПЕРЬ С ВИДЕО!)
        self.update_state(state='PROGRESS', meta={'status': 'Сжатие видео/аудио...'})
        # Функция теперь возвращает путь И mime-type
        compressed_path, mime_type = compress_media(file_path)
        
        target_file = compressed_path if compressed_path else file_path

        # 2. Shazam
        shazam_text = ""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            res = loop.run_until_complete(recognize_music(target_file))
            loop.close()
            if res: shazam_text = f"SHAZAM IDENTIFICATION: {res}"
        except: pass

        # 3. Загрузка (С подробным дебагом)
        self.update_state(state='PROGRESS', meta={'status': 'Отправка в Google Cloud...'})
        media_f = upload_to_gemini(target_file, mime_type)
        
        if not media_f:
            # Возвращаем клиенту подробную ошибку (она будет в консоли воркера)
            return {"error": "Upload failed. Check Worker Logs for details."}
            
        files_cleanup.append(media_f)

        # 4. RAG
        db = SessionLocal()
        policies, taxonomy, examples = get_rag_context(db, profile)
        
        prompt = SYSTEM_PROMPT_TEMPLATE.format(
            policies_text=policies,
            taxonomy_text=taxonomy,
            human_examples=examples
        )
        
        visual_instruction = f"ПРОФИЛЬ ПРОВЕРКИ: {profile.upper()}. Анализируй контент строго по предоставленным политикам. ВАЖНО: Анализируй ВИДЕОРЯД. Обращай внимание на мимику, жесты и контекст происходящего (комедия, ссора, игра)."

        content = [prompt, visual_instruction, f"Файл: {filename}. {shazam_text}", media_f]
        content = [x for x in content if x is not None]

        # 5. Генерация
        self.update_state(state='PROGRESS', meta={'status': 'AI думает...'})
        model = genai.GenerativeModel(MODEL_NAME)
        
        response = None
        max_retries = 5
        base_wait = 15
        
        for attempt in range(max_retries):
            try:
                response = model.generate_content(
                    content,
                    generation_config={"response_mime_type": "application/json"},
                    safety_settings=SAFETY_SETTINGS
                )
                break
            except Exception as e:
                if "429" in str(e) or "Quota" in str(e):
                    wait = base_wait * (2 ** attempt) + random.uniform(1, 5)
                    self.update_state(state='PROGRESS', meta={'status': f'Лимит Google. Ждем {int(wait)}с...'})
                    time.sleep(wait)
                else: raise e

        if not response or not response.text: return {"error": "Empty response."}

        # 6. Финиш
        result_data = json.loads(clean_json_text(response.text))
        
        init_db()
        asset_res = db.execute(text("INSERT INTO media_asset (filename, duration_ms) VALUES (:fn, 0) RETURNING id"), {"fn": filename}).fetchone()
        asset_id = asset_res.id
        
        save_results_to_db(db, asset_id, result_data, MODEL_NAME)
        db.close()
        
        result_data['_asset_id'] = str(asset_id)
        return result_data

    except Exception as e:
        print(f"CRITICAL: {e}")
        return {"error": str(e)}
    finally:
        for f in files_cleanup: 
            try: f.delete() 
            except: pass
        if compressed_path and os.path.exists(compressed_path): 
            os.remove(compressed_path)