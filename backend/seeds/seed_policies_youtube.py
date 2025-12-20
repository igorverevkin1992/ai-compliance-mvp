import os
from sqlalchemy import create_engine, text
import uuid

# Вставь свою ссылку Supabase (или из env)
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

yt_policies = [
    {
        "code": "YT_AD_PROFANITY",
        "summary": "YouTube: Ненормативная лексика (Правила монетизации).",
        "type": "RESTRICTED",
        "risk": "MEDIUM",
        "text": "Для сохранения монетизации избегайте грубой лексики в первые 30 секунд видео. В остальной части видео лексика допустима, но частое использование может привести к ограничению рекламы ('Желтый доллар')."
    },
    {
        "code": "YT_HATE_SPEECH",
        "summary": "YouTube: Дискриминационные высказывания (Strike).",
        "type": "PROHIBITED",
        "risk": "CRITICAL",
        "text": "Запрещен контент, поощряющий насилие или ненависть к людям по признаку расы, этнической принадлежности, религии, инвалидности, пола, возраста, статуса ветерана, сексуальной ориентации или гендерной идентичности. Приводит к 'Страйку' и удалению канала."
    },
    {
        "code": "YT_HARASSMENT",
        "summary": "YouTube: Оскорбления и угрозы.",
        "type": "PROHIBITED",
        "risk": "HIGH",
        "text": "Запрещены контент и комментарии, содержащие длительные оскорбления, злонамеренные нападки на основе личных признаков, а также угрозы. Включает 'прожарку' без согласия."
    },
    {
        "code": "YT_DANGEROUS",
        "summary": "YouTube: Опасный контент и челленджи.",
        "type": "PROHIBITED",
        "risk": "HIGH",
        "text": "Запрещен контент, поощряющий опасные действия, которые могут привести к серьезным травмам (например, удушение, поедание капсул для стирки). Пранки, вызывающие у жертв панику, также запрещены."
    },
    {
        "code": "RF_INTERNET_LAW",
        "summary": "Законы РФ для Интернета (ФЗ-436, Иноагенты).",
        "type": "MANDATORY",
        "risk": "HIGH",
        "text": "Обязательная маркировка иноагентов (текстом в описании или на видео). Запрет на пропаганду наркотиков и ЛГБТ. В отличие от ТВ, допускается контент 18+ с соответствующей маркировкой платформы, но без пропаганды."
    }
]

def seed_youtube():
    with engine.connect() as conn:
        print("▶️ Загрузка Политик YouTube...")
        
        # 1. Генерируем ID для документа
        doc_id = uuid.uuid4()
        
        conn.execute(text("""
            INSERT INTO legal_doc (id, publisher, title, version) 
            VALUES (:id, 'YouTube/Internet', 'Правила Сообщества и Рекламодателей', '2025')
        """), {"id": doc_id})
        
        # 2. Вставляем требования
        for p in yt_policies:
            req_id = uuid.uuid4() # <--- Генерируем ID для каждого правила
            
            conn.execute(text("""
                INSERT INTO legal_requirement (id, doc_id, req_code, requirement_type, risk_floor, summary, full_text)
                VALUES (:id, :doc_id, :code, :type, :risk, :summ, :text)
                ON CONFLICT (req_code) DO NOTHING;
            """), {
                "id": req_id, # <--- Передаем ID
                "doc_id": doc_id,
                "code": p["code"],
                "type": p["type"],
                "risk": p["risk"],
                "summ": p["summary"],
                "text": p["text"]
            })
        conn.commit()
    print("✅ YouTube policies added.")

if __name__ == "__main__":
    seed_youtube()