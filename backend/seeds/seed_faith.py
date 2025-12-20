import os
from sqlalchemy import create_engine, text
import uuid

# Вставь свою ссылку Supabase
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

def seed_uk_148():
    with engine.connect() as conn:
        print("⛪ Загрузка ст. 148 УК РФ (Чувства верующих) в базу...")
        
        # 1. Генерируем ID в Python
        doc_id = uuid.uuid4()
        
        # 2. Передаем его в запрос
        conn.execute(text("""
            INSERT INTO legal_doc (id, publisher, title, version) 
            VALUES (:id, 'РФ', 'Название...', 'версия...')
        """), {"id": doc_id})
        
        requirements = [
            {
                "code": "RF_UK_148_PUBLIC_INSULT",
                "type": "PROHIBITED",
                "risk": "HIGH",
                "summary": "Публичные действия, выражающие неуважение и оскорбляющие чувства верующих.",
                "text": "Статья 148 ч.1: Публичные действия, выражающие явное неуважение к обществу и совершенные в целях оскорбления религиозных чувств верующих. Наказываются лишением свободы до 1 года."
            },
            {
                "code": "RF_UK_148_SACRED_PLACE",
                "type": "PROHIBITED",
                "risk": "CRITICAL",
                "summary": "Оскорбление чувств верующих в местах богослужения (храмах, мечетях и др.).",
                "text": "Статья 148 ч.2: Деяния, совершенные в местах, специально предназначенных для проведения богослужений, других религиозных обрядов и церемоний. Наказываются лишением свободы до 3 лет. (Пример: танцы, перформансы, оголение в храме)."
            },
            {
                "code": "RF_UK_148_OBSTRUCTION",
                "type": "PROHIBITED",
                "risk": "MEDIUM",
                "summary": "Воспрепятствование деятельности религиозных организаций.",
                "text": "Статья 148 ч.3: Незаконное воспрепятствование деятельности религиозных организаций или проведению богослужений, других религиозных обрядов и церемоний."
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
        print("✅ Статья 148 УК РФ успешно добавлена. Агент будет следить за религиозным контекстом.")

if __name__ == "__main__":
    seed_uk_148()