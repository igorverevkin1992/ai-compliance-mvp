import os
import json
import re
import subprocess
import asyncio
import google.generativeai as genai
from database import SessionLocal, AnalysisRecord, init_db

# Библиотеки для текста
import docx
from pypdf import PdfReader

# Наши модули
from celery_app import app
from prompts.instructions import SYSTEM_PROMPT_TEMPLATE
from shazam_helper import recognize_music

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---


def clean_json_text(text: str) -> str:
    text = re.sub(r"^```json\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^```\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"```$", "", text, flags=re.MULTILINE)
    return text.strip()


def read_text_file(file_path: str, filename: str) -> str:
    ext = filename.split(".")[-1].lower()
    text = ""
    try:
        if ext == "txt":
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        elif ext == "docx":
            doc = docx.Document(file_path)
            text = "\n".join([para.text for para in doc.paragraphs])
        elif ext == "pdf":
            reader = PdfReader(file_path)
            for page in reader.pages:
                text += (page.extract_text() or "") + "\n"
    except Exception as e:
        print(f"Error reading text: {e}")
    return text


def compress_audio_ffmpeg(input_path: str) -> str:
    output_path = f"{os.path.splitext(input_path)[0]}_compressed.m4a"
    # Сжимаем в моно 16kHz
    command = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "aac",
        output_path,
    ]
    try:
        subprocess.run(
            command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        if os.path.exists(output_path):
            return output_path
    except Exception as e:
        print(f"FFmpeg Error: {e}")
    return None


def upload_to_gemini(path: str, mime_type: str):
    return genai.upload_file(path, mime_type=mime_type)


def get_files_in_dir(directory, ext):
    if os.path.exists(directory):
        return [
            os.path.join(directory, f) for f in os.listdir(directory) if f.endswith(ext)
        ]
    return []


# --- ОСНОВНАЯ ЗАДАЧА (TASK) ---


@app.task(bind=True)
def analyze_media_task(self, file_path: str, filename: str, api_key: str):
    """
    Эта функция выполняется в отдельном контейнере (Worker).
    """
    files_cleanup = []  # Файлы для удаления из облака
    compressed_path = None

    # Путь к сжатому файлу (рядом с оригиналом)

    try:
        # 1. Настройка Gemini
        genai.configure(api_key=api_key)
        MODEL_NAME = "gemini-2.5-flash"

        # 2. Определение типа
        file_ext = filename.split(".")[-1].lower()
        is_text = file_ext in ["txt", "docx", "pdf"]

        main_content_part = None

        if is_text:
            # === ТЕКСТ ===
            text_data = read_text_file(file_path, filename)
            if not text_data:
                return {"error": "Failed to read text file"}
            main_content_part = f"ПРОАНАЛИЗИРУЙ ТЕКСТ:\n\n{text_data}"

        else:
            # === МЕДИА ===
            self.update_state(
                state="PROGRESS", meta={"status": "Compressing Video/Audio..."}
            )

            # Сжатие
            compressed_path = compress_audio_ffmpeg(file_path)
            target_file = compressed_path if compressed_path else file_path
            mime_type = (
                "audio/mp4" if target_file == compressed_path else "video/mp4"
            )  # Упрощено

            # Shazam (запускаем асинхронную функцию в синхронном коде)
            self.update_state(
                state="PROGRESS", meta={"status": "Running Shazam Identification..."}
            )
            shazam_info = ""
            try:
                # Внимание: Celery уже имеет свой event loop, но asyncio.run создает новый.
                # Для простых задач это ок.
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                res = loop.run_until_complete(recognize_music(target_file))
                loop.close()

                if res:
                    shazam_info = f"\n\nSHAZAM DATA: {res}"
            except Exception as e:
                print(f"Shazam failed inside task: {e}")

            # Загрузка в Gemini
            self.update_state(
                state="PROGRESS", meta={"status": "Uploading to Gemini..."}
            )
            media_f = upload_to_gemini(target_file, mime_type)
            files_cleanup.append(media_f)

            # Формируем контент
            main_content_part = [shazam_info, media_f] if shazam_info else media_f

        # 3. Сборка промпта
        self.update_state(
            state="PROGRESS", meta={"status": "AI Analysis in progress..."}
        )

        request_content = [SYSTEM_PROMPT_TEMPLATE]

        # Реестры и Законы
        for p in get_files_in_dir("registries", ".json"):
            f = upload_to_gemini(p, "text/plain")
            request_content.append(f)
            files_cleanup.append(f)

        for p in get_files_in_dir("laws", ".pdf"):
            f = upload_to_gemini(p, "application/pdf")
            request_content.append(f)
            files_cleanup.append(f)

        request_content.append("ВАЖНО: Ниже приведен контент для анализа.")
        if isinstance(main_content_part, list):
            request_content.extend(main_content_part)
        else:
            request_content.append(main_content_part)

        # 4. Генерация
        model = genai.GenerativeModel(
            MODEL_NAME, generation_config={"response_mime_type": "application/json"}
        )
        response = model.generate_content(request_content)

        # 5. Результат
        cleaned_json = clean_json_text(response.text)
        result_data = json.loads(cleaned_json)

        # 6. Сохранение в БД
        try:
            # Создаем таблицы, если их нет (лучше делать это при старте приложения, но для MVP сойдет тут)
            init_db()

            db = SessionLocal()
            record = AnalysisRecord(
                filename=filename,
                file_type="text" if is_text else "media",
                ai_result_json=result_data,
                is_verified=False,
            )
            db.add(record)
            db.commit()
            db.refresh(record)  # Получаем ID записи

            # Добавляем ID записи в ответ, чтобы Фронтенд знал, что обновлять
            record_id = record.id
            if isinstance(result_data, list):
                if len(result_data) > 0:
                    result_data[0]["_db_id"] = record_id
                else:
                    # Если список пуст, придется вернуть спец объект
                    result_data.append({"_db_id": record_id, "info": "Empty result"})
            elif isinstance(result_data, dict):
                result_data["_db_id"] = record_id

            db.close()
            print(f"✅ Saved to DB with ID: {record_id}")

        except Exception as db_e:
            print(f"⚠️ Database Error: {db_e}")
            # Не роняем задачу, если база недоступна, просто идем дальше
        # --- СОХРАНЕНИЕ В БАЗУ ДАННЫХ (End) ---

        return result_data

    except Exception as e:
        return {"error": str(e)}

    finally:
        # Очистка облака
        for f in files_cleanup:
            try:
                f.delete()
            except:
                pass
        # Локальные файлы (оригинал и сжатый) удалит тот, кто их создал,
        # или можно удалять тут, если они больше не нужны.
        # Пока оставим оригиналы, удалим только сжатый.
        if compressed_path and os.path.exists(compressed_path):
            os.remove(compressed_path)
