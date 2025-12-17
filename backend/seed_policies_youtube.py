import os
from sqlalchemy import create_engine, text

# Вставь свою ссылку Supabase
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres.naxfhbmdvxxejgmpfqeh:IgorV199205161992@aws-1-eu-central-2.pooler.supabase.com:6543/postgres")
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

with engine.connect() as conn:
    print("Seeding YouTube Policies...")
    
    # 1. Создаем документ
    doc_id = conn.execute(text("""
        INSERT INTO legal_doc (publisher, title, version) 
        VALUES ('YouTube/Internet', 'Правила Сообщества и Рекламодателей', '2025')
        RETURNING id
    """)).scalar()
    
    # 2. Вставляем требования
    for p in yt_policies:
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
    print("Done! YouTube policies added.")