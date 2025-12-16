import os
import json
import re
import subprocess
import asyncio
import google.generativeai as genai
from sqlalchemy import desc

# Библиотеки для текста
import docx
from pypdf import PdfReader

# Наши модули
from celery_app import app
from prompts.instructions import SYSTEM_PROMPT_TEMPLATE
from shazam_helper import recognize_music
from database import SessionLocal, AnalysisRecord, init_db

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def clean_json_text(text: str) -> str:
    text = re.sub(r"^```json\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^```\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"```$", "", text, flags=re.MULTILINE)
    return text.strip()

def read_text_file(file_path: str, filename: str) -> str:
    ext = filename.split('.')[-1].lower()
    text = ""
    try:
        if ext == 'txt':
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
        elif ext == 'docx':
            doc = docx.Document(file_path)
            text = "\n".join([para.text for para in doc.paragraphs])
        elif ext == 'pdf':
            reader = PdfReader(file_path)
            for page in reader.pages:
                text += (page.extract_text() or "") + "\n"
    except Exception as e:
        print(f"Error reading text: {e}")
    return text

def compress_audio_ffmpeg(input_path: str) -> str:
    output_path = f"{os.path.splitext(input_path)[0]}_compressed.m4a"
    command = ["ffmpeg", "-y", "-i", input_path, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "aac", output_path]
    try:
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(output_path):
            return output_path
    except Exception as e:
        print(f"FFmpeg Error: {e}")
    return None

def upload_to_gemini(path: str, mime_type: str):
    try:
        return genai.upload_file(path, mime_type=mime_type)
    except Exception as e:
        print(f"⚠️ Failed to upload {path} to Gemini: {e}")
        return None

def get_files_in_dir(directory, ext):
    if os.path.exists(directory):
        return [os.path.join(directory, f) for f in os.listdir(directory) if f.endswith(ext)]
    return []

# --- ОСНОВНАЯ ЗАДАЧА (TASK) ---

@app.task(bind=True)
def analyze_media_task(self, file_path: str, filename: str, api_key: str):
    """
    Эта функция выполняется в отдельном контейнере (Worker).
    """
    files_cleanup = [] 
    compressed_path = None
    
    try:
        # 1. Настройка Gemini
        genai.configure(api_key=api_key)
        # Ты просил использовать именно эту версию, но если будет ошибка Model Not Found, 
        MODEL_NAME = "gemini-2.5-flash"

        # 2. Определение типа
        file_ext = filename.split('.')[-1].lower()
        is_text = file_ext in ['txt', 'docx', 'pdf']
        
        main_content_part = None

        if is_text:
            # === ТЕКСТ ===
            text_data = read_text_file(file_path, filename)
            if not text_data:
                return {"error": "Failed to read text file"}
            main_content_part = f"ПРОАНАЛИЗИРУЙ ТЕКСТ:\n\n{text_data}"
        
        else:
            # === МЕДИА ===
            self.update_state(state='PROGRESS', meta={'status': 'Compressing Video/Audio...'})
            
            # Сжатие
            compressed_path = compress_audio_ffmpeg(file_path)
            target_file = compressed_path if compressed_path else file_path
            mime_type = "audio/mp4" if target_file == compressed_path else "video/mp4"

            # Shazam
            self.update_state(state='PROGRESS', meta={'status': 'Running Shazam Identification...'})
            shazam_info = ""
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                res = loop.run_until_complete(recognize_music(target_file))
                loop.close()
                
                if res:
                    shazam_info = f"\n\nSHAZAM DATA: {res}"
            except Exception as e:
                print(f"Shazam failed: {e}")

            # Загрузка в Gemini
            self.update_state(state='PROGRESS', meta={'status': 'Uploading to Gemini...'})
            media_f = upload_to_gemini(target_file, mime_type)
            if media_f:
                files_cleanup.append(media_f)
                # Формируем контент: Текст + Файл
                main_content_part = [shazam_info, media_f] if shazam_info else media_f
            else:
                return {"error": "Failed to upload media file to Google Cloud"}

        # --- RAG: ПОЛУЧЕНИЕ ЧЕЛОВЕЧЕСКОГО ОПЫТА ---
        human_examples_text = "Примеров пока нет."
        try:
            db = SessionLocal()
            verified_records = db.query(AnalysisRecord)\
                .filter(AnalysisRecord.is_verified == True)\
                .order_by(desc(AnalysisRecord.id))\
                .limit(10)\
                .all()
            
            if verified_records:
                examples_list = []
                for rec in verified_records:
                    if rec.verified_result_json:
                        for item in rec.verified_result_json:
                             example_str = f"- Ситуация: {item.get('description')}\n  Вердикт человека: {item.get('risk_level')}"
                             examples_list.append(example_str)
                
                if examples_list:
                    human_examples_text = "\n".join(examples_list)
                    print(f"\n📢 [RAG] Using {len(examples_list)} examples from DB.\n")
            
            db.close()
        except Exception as e:
            print(f"RAG Error: {e}")

        # 3. Сборка промпта
        self.update_state(state='PROGRESS', meta={'status': 'AI Analysis in progress...'})
        
        # Используем replace для вставки RAG, чтобы не ломать JSON-скобки
        final_prompt_text = SYSTEM_PROMPT_TEMPLATE.replace("{human_examples}", human_examples_text)
        
        request_content = [final_prompt_text]
        
        # Реестры и Законы
        for p in get_files_in_dir("registries", ".json"):
            f = upload_to_gemini(p, "text/plain")
            request_content.append(f)
            if f: files_cleanup.append(f)
            
        for p in get_files_in_dir("laws", ".pdf"):
            f = upload_to_gemini(p, "application/pdf")
            request_content.append(f)
            if f: files_cleanup.append(f)

        request_content.append("ВАЖНО: Ниже приведен контент для анализа.")
        
        # Добавляем основной контент (список или объект)
        if isinstance(main_content_part, list):
            request_content.extend(main_content_part)
        else:
            request_content.append(main_content_part)

        # !!! ВАЖНЕЙШЕЕ ИСПРАВЛЕНИЕ: Фильтруем None !!!
        # Если какой-то файл не загрузился, в списке может быть None. Gemini этого не любит.
        request_content = [item for item in request_content if item is not None]

        # 4. Генерация
        model = genai.GenerativeModel(
            MODEL_NAME, generation_config={"response_mime_type": "application/json"}
        )
        response = model.generate_content(request_content)
        
        # 5. Результат и Сохранение
        cleaned_json = clean_json_text(response.text)
        result_data = json.loads(cleaned_json)
        
        # Сохранение в базу
        try:
            init_db()
            db = SessionLocal()
            record = AnalysisRecord(
                filename=filename,
                file_type="text" if is_text else "media",
                ai_result_json=result_data,
                is_verified=False
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            
            record_id = record.id
            if isinstance(result_data, list):
                if len(result_data) > 0:
                    result_data[0]['_db_id'] = record_id
                else:
                    result_data.append({'_db_id': record_id, 'info': 'Empty result'})
            elif isinstance(result_data, dict):
                result_data['_db_id'] = record_id
                
            db.close()
        except Exception as db_e:
            print(f"Database Error: {db_e}")
        
        return result_data

    except Exception as e:
        # Логируем ошибку в консоль
        print(f"CRITICAL TASK ERROR: {e}")
        return {"error": str(e)}

    finally:
        for f in files_cleanup:
            try: f.delete()
            except: pass
        if compressed_path and os.path.exists(compressed_path):
            os.remove(compressed_path)