import os
from sqlalchemy import create_engine, text
import uuid

# Вставь свою ссылку Supabase
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

def seed_gk_1274():
    with engine.connect() as conn:
        print("⚖️ Загрузка ст. 1274 ГК РФ (Fair Use / Цитирование)...")
        
        # 1. Генерируем ID в Python
        doc_id = uuid.uuid4()
        
        # 2. Передаем его в запрос
        conn.execute(text("""
            INSERT INTO legal_doc (id, publisher, title, version) 
            VALUES (:id, 'РФ', 'Название...', 'версия...')
        """), {"id": doc_id})
        
        requirements = [
            {
                "code": "RF_GK_1274_CITATION",
                "type": "PERMITTED",
                "risk": "SAFE",
                "summary": "Свободное цитирование в информационных/полемических целях.",
                "text": "Статья 1274 п.1 пп.1: Допускается цитирование правомерно обнародованных произведений в оригинале и переводе в научных, полемических, критических или информационных целях в объеме, оправданном целью цитирования. ОБЯЗАТЕЛЬНО указание автора и источника заимствования."
            },
            {
                "code": "RF_GK_1274_ILLUSTRATION",
                "type": "PERMITTED",
                "risk": "SAFE",
                "summary": "Использование как иллюстрации в учебных целях.",
                "text": "Статья 1274 п.1 пп.2: Допускается использование произведений и отрывков из них в качестве иллюстраций в изданиях, радио- и телепередачах, звуко- и видеозаписях учебного характера."
            },
            {
                "code": "RF_GK_1274_CURRENT_EVENTS",
                "type": "PERMITTED",
                "risk": "SAFE",
                "summary": "Показ произведений, увиденных в ходе текущих событий (репортаж).",
                "text": "Статья 1274 п.1 пп.5: Допускается показ произведений (картин, музыки), которые становятся увиденными или услышанными в ходе текущих событий (например, в новостном репортаже с выставки), в объеме, оправданном информационной целью."
            },
            {
                "code": "RF_GK_1274_PARODY",
                "type": "PERMITTED",
                "risk": "SAFE",
                "summary": "Свободное создание пародий и карикатур.",
                "text": "Статья 1274 п.4: Создание произведения в жанре литературной, музыкальной или иной пародии либо карикатуры на основе другого произведения и использование этой пародии допускаются БЕЗ согласия автора оригинального произведения."
            }
        ]
        
        for req in requirements:
            # Генерируем ID для требования
            req_id = uuid.uuid4()

            conn.execute(text("""
                INSERT INTO legal_requirement (id, doc_id, req_code, requirement_type, risk_floor, summary, full_text)
                VALUES (:id, :doc_id, :code, :type, :risk, :summ, :text)
                ON CONFLICT (req_code) DO UPDATE SET full_text = EXCLUDED.full_text
            """), {
                "id": req_id,       # <--- ДОБАВЛЕНО
                "doc_id": doc_id,
                "code": req["code"],
                "type": req["type"],
                "risk": req["risk"],
                "summ": req["summary"],
                "text": req["text"]
            })
        
        conn.commit()
        print("✅ Статья 1274 ГК РФ успешно добавлена. Агент знает, что такое 'Fair Use'.")

if __name__ == "__main__":
    seed_gk_1274()