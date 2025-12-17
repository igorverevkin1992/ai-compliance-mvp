# backend/seed_policies.py
import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres.naxfhbmdvxxejgmpfqeh:IgorV199205161992@aws-1-eu-central-2.pooler.supabase.com:6543/postgres")
engine = create_engine(DATABASE_URL)

ntv_policies = [
    {
        "code": "NTV_AGE18_001",
        "summary": "Контент 18+ (наркотики, насилие, смена пола) разрешен только с 23:00 до 04:00.",
        "type": "RESTRICTED",
        "risk": "HIGH",
        "text": "Информация, запрещенная для детей (наркотики, жестокость, ЛГБТ, смена пола), может распространяться только с 23:00 до 04:00 с маркировкой 18+."
    },
    {
        "code": "NTV_AGE16_001",
        "summary": "Контент 16+ (бранные слова, ненасильственная смерть) разрешен только с 21:00 до 07:00.",
        "type": "RESTRICTED",
        "risk": "MEDIUM",
        "text": "Информация 16+ (отдельные бранные слова, описание половых отношений) распространяется с 21:00 до 07:00."
    },
    {
        "code": "NTV_BAN_OBSCENE_001",
        "summary": "Полный запрет на нецензурную брань (мат).",
        "type": "PROHIBITED",
        "risk": "CRITICAL",
        "text": "Запрещается распространение информации, содержащей нецензурную брань (4 слова и производные). Требуется полное 'запикивание' или удаление."
    },
    {
        "code": "NTV_META_001",
        "summary": "Запрет демонстрации логотипов Meta, Facebook, Instagram.",
        "type": "PROHIBITED",
        "risk": "HIGH",
        "text": "Запрещается распространение логотипов Meta Platforms Inc и ее соцсетей. В записи требуется удаление/блюр. В прямом эфире - устное предупреждение."
    },
    {
        "code": "NTV_FOREIGNAGENT_LABEL_001",
        "summary": "Обязательная маркировка иноагентов (15 секунд, 20% экрана).",
        "type": "MANDATORY",
        "risk": "HIGH",
        "text": "При упоминании иноагента или показе его материалов обязательна плашка: 'ДАННОЕ СООБЩЕНИЕ...' (текст по ФЗ). Текст должен занимать не менее 20% площади и быть контрастным."
    }
]

with engine.connect() as conn:
    print("Seeding NTV Policies...")
    
    # 1. Создаем документ
    doc_id = conn.execute(text("""
        INSERT INTO legal_doc (publisher, title, version) 
        VALUES ('НТВ', 'Требования к содержанию программ', 'ред. 23.01.2024')
        RETURNING id
    """)).scalar()
    
    # 2. Вставляем требования
    for p in ntv_policies:
        sql = text("""
            INSERT INTO legal_requirement (doc_id, req_code, requirement_type, risk_floor, summary, full_text)
            VALUES (:doc_id, :code, :type, :risk, :summ, :text)
            ON CONFLICT (req_code) DO NOTHING;
        """)
        conn.execute(sql, {
            "doc_id": doc_id,
            "code": p["code"],
            "type": p["type"],
            "risk": p["risk"],
            "summ": p["summary"],
            "text": p["text"]
        })
        conn.commit()
    print("Done!")