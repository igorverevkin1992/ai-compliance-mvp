import os
from sqlalchemy import create_engine, text
import uuid

# Вставь свою ссылку Supabase
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

def seed_koap_6_21():
    with engine.connect() as conn:
        print("Загрузка ст. 6.21 КоАП (ЛГБТ, Чайлдфри, Смена пола)...")
        
        # 1. Генерируем ID в Python
        doc_id = uuid.uuid4()
        
        # 2. Передаем его в запрос
        conn.execute(text("""
            INSERT INTO legal_doc (id, publisher, title, version) 
            VALUES (:id, 'РФ', 'Название...', 'версия...')
        """), {"id": doc_id})
        
        requirements = [
            {
                "code": "RF_KOAP_LGBT_PROPAGANDA",
                "type": "PROHIBITED",
                "risk": "CRITICAL",
                "summary": "Пропаганда нетрадиционных сексуальных отношений.",
                "text": "Статья 6.21 ч.1: Запрещена пропаганда нетрадиционных сексуальных отношений и (или) предпочтений, выразившаяся в распространении информации, направленной на формирование нетрадиционных сексуальных установок или привлекательности таких отношений."
            },
            {
                "code": "RF_KOAP_GENDER_CHANGE",
                "type": "PROHIBITED",
                "risk": "CRITICAL",
                "summary": "Пропаганда смены пола.",
                "text": "Статья 6.21 ч.1: Запрещена пропаганда смены пола, выразившаяся в навязывании информации, вызывающей интерес к смене пола."
            },
            {
                "code": "RF_KOAP_CHILDFREE",
                "type": "PROHIBITED",
                "risk": "HIGH",
                "summary": "Пропаганда отказа от деторождения (Чайлдфри).",
                "text": "Статья 6.21 ч.1 (ред. 2024): Запрещена пропаганда отказа от деторождения, направленная на формирование искаженного представления о социальной равноценности рождения детей и отказа от деторождения. ИСКЛЮЧЕНИЕ: Информация о монашестве и обете безбрачия."
            },
            {
                "code": "RF_KOAP_LGBT_MINORS",
                "type": "PROHIBITED",
                "risk": "CRITICAL",
                "summary": "Пропаганда среди несовершеннолетних (Отягчающее).",
                "text": "Статья 6.21 ч.2: Те же действия, совершенные среди несовершеннолетних, влекут повышенные штрафы (до 2 млн руб. или приостановление деятельности)."
            },
            {
                "code": "RF_KOAP_LGBT_MEDIA",
                "type": "PROHIBITED",
                "risk": "CRITICAL",
                "summary": "Пропаганда в СМИ и Интернете (Отягчающее).",
                "text": "Статья 6.21 ч.3: Использование СМИ или Интернета для пропаганды влечет штраф для юрлиц до 4 млн рублей или приостановление деятельности на 90 суток."
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
        print("✅ КоАП 6.21 успешно оцифрован.")

if __name__ == "__main__":
    seed_koap_6_21()