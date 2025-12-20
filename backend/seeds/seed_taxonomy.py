import sys
import os
import uuid
from sqlalchemy import create_engine, text

# --- ИСПРАВЛЕНИЕ ПУТЕЙ (Чтобы видеть database.py) ---
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# ----------------------------------------------------

# Импортируем структуру БД
from database import Base, engine as db_engine

# Вставь ссылку из .env
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

taxonomy_data = [
    ('AGE_18_CONTENT', 'Age', 'Контент 18+', 2),
    ('AGE_16_CONTENT', 'Age', 'Контент 16+', 1),
    ('AGE_SIGN_REQUIRED', 'Age', 'Отсутствует плашка возраста', 2),
    
    ('OBSCENE_PROFANITY_BANNED', 'Prohibited', 'Нецензурная брань (мат)', 3),
    ('PORNOGRAPHY_BANNED', 'Prohibited', 'Порнография', 3),
    ('EXTREMISM_CALLS', 'Prohibited', 'Призывы к экстремизму', 3),
    
    ('PROFANITY_NON_OBSCENE_16PLUS', 'Language', 'Бранная лексика (грубая)', 1),
    
    ('LGBT_TOPIC_RESTRICTED', 'LGBT', 'ЛГБТ тематика (ограничение по времени)', 2),
    ('LGBT_PROPAGANDA_PROHIBITED', 'LGBT', 'Пропаганда ЛГБТ', 3),
    
    ('PERSONAL_DATA', 'Privacy', 'Персональные данные', 2),
    ('IMAGE_CONSENT_REQUIRED', 'Privacy', 'Изображение гражданина без согласия', 2),
    
    ('FOREIGN_AGENT_LABEL_REQUIRED', 'Legal', 'Иноагент без маркировки', 3),
    ('META_LOGO_BANNED', 'Legal', 'Логотип Meta/Instagram/FB', 3),
    
    ('TOBACCO_DISPLAY', 'Substances', 'Демонстрация табака', 1),
    ('DRUGS_PROMOTION', 'Substances', 'Пропаганда наркотиков', 3),
]

def seed_taxonomy():
    # 1. СОЗДАЕМ ТАБЛИЦЫ (Если их нет)
    print("🛠 Проверка и создание таблиц...")
    Base.metadata.create_all(bind=db_engine)

    with engine.connect() as conn:
        print("🏷️ Загрузка Таксономии...")
        for code, group, title, sev in taxonomy_data:
            tax_id = uuid.uuid4()
            
            conn.execute(text("""
                INSERT INTO taxonomy_label (id, code, group_name, title, default_severity)
                VALUES (:id, :code, :grp, :title, :sev)
                ON CONFLICT (code) DO UPDATE SET 
                title = EXCLUDED.title, default_severity = EXCLUDED.default_severity;
            """), {
                "id": tax_id,
                "code": code, 
                "grp": group, 
                "title": title, 
                "sev": sev
            })
        conn.commit()
    print("✅ Taxonomy added.")

if __name__ == "__main__":
    seed_taxonomy()