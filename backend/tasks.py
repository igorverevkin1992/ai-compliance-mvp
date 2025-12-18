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

def get_embedding(text_to_embed: str, api_key: str):
    
    try:
        genai.configure(api_key=api_key)
        # Используем специальную легкую модель для векторов
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text_to_embed,
            task_type="retrieval_document"
        )
        return result['embedding']
    except Exception as e:
        print(f"⚠️ Embedding Error: {e}")
        return None

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
            "-vf", "scale=640:-2,format=yuv420p", # Принудительный формат пикселей yuv420p
            "-c:v", "libx264", 
            "-profile:v", "high", # Профиль совместимости
            "-level", "4.1",
            "-crf", "28", 
            "-preset", "faster", 
            "-r", "24",
            "-c:a", "aac", "-ac", "1", "-ar", "16000",
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
    """Загрузка с мгновенным отловом ошибок обработки"""
    print(f"☁️ Uploading to Gemini: {path}")
    try:
        file = genai.upload_file(path, mime_type=mime_type)
        
        # Ждем готовности
        start_time = time.time()
        while file.state.name == "PROCESSING":
            time.sleep(3)
            file = genai.get_file(file.name)
            # Если маленький файл обрабатывается дольше 40 секунд - это уже подозрительно
            if time.time() - start_time > 300:
                print("❌ Google застрял на обработке (возможно, несовместимый кодек).")
                return None

        if file.state.name == "FAILED":
            print(f"❌ Google не смог обработать файл. Состояние: {file.state.name}")
            return None

        print(f"✅ Файл ACTIVE за {int(time.time() - start_time)} сек.")
        return file
    except Exception as e:
        print(f"❌ Ошибка API Google при загрузке: {e}")
        return None

def get_rag_context(db, profile, query_text, api_key):
    """Ищет в базе 5 самых похожих исправленных кейсов через векторный поиск"""
    try:
        # 1. Загружаем Политики (как и раньше)
        pub_query = "YouTube%" if profile == "youtube" else "НТВ%"
        sql_pol = text("""
            SELECT r.req_code, r.summary, r.full_text 
            FROM legal_requirement r
            JOIN legal_doc d ON r.doc_id = d.id
            WHERE d.publisher LIKE :pub
        """)
        policies = db.execute(sql_pol, {"pub": pub_query}).fetchall()
        policies_text = "\n".join([f"- [{p.req_code}] {p.summary}" for p in policies])

        # 2. ВЕКТОРНЫЙ ПОИСК ПО ПАМЯТИ (Semantic RAG)
        vector = get_embedding(query_text, api_key)
        human_examples = "Похожих примеров не найдено."
        
        if vector:
            # Ищем в таблице case_memory через оператор <=> (косинусное сходство)
            sql_vector = text("""
                SELECT text, meta->>'final_risk' as risk
                FROM case_memory
                ORDER BY embedding <=> :vec_str
                LIMIT 5
            """)
            # Превращаем список чисел в строку, которую поймет Postgres
            similar_cases = db.execute(sql_vector, {"vec_str": str(vector)}).fetchall()
            
            if similar_cases:
                examples_list = [f"КЕЙС: {c.text} | ВЕРДИКТ: {c.risk}" for c in similar_cases]
                human_examples = "\n\n".join(examples_list)

        return policies_text, human_examples
    except Exception as e:
        print(f"⚠️ RAG Error: {e}")
        return "Ошибка политик", "Ошибка памяти"

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
        
        policies_text, human_examples = get_rag_context(db, profile, f"{filename} {shazam_text}", api_key)
        
        # Мы берем таксономию напрямую из базы, так как она статична
        taxonomy_res = db.execute(text("SELECT code, title FROM taxonomy_label")).fetchall()
        taxonomy_text = "\n".join([f"- {t.code}: {t.title}" for t in taxonomy_res])

        # Собираем финальный промпт через .replace (чтобы не сломать JSON-скобки)
        prompt = SYSTEM_PROMPT_TEMPLATE.replace("{policies_text}", policies_text)
        prompt = prompt.replace("{taxonomy_text}", taxonomy_text)
        prompt = prompt.replace("{human_examples}", human_examples)
        
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
        result_data['_retrieved_context'] = human_examples 

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