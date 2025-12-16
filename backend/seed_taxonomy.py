# backend/seed_taxonomy.py
import os
from sqlalchemy import create_engine, text

# Вставь ссылку из .env
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres.ВАШ_ПРОЕКТ:ПАРОЛЬ@aws-0-eu-central-1.pooler.supabase.com:6543/postgres")

engine = create_engine(DATABASE_URL)

taxonomy_data = [
    # A. Age / Time
    ('AGE_18_CONTENT', 'Age', 'Контент 18+', 2),
    ('AGE_16_CONTENT', 'Age', 'Контент 16+', 1),
    ('AGE_SIGN_REQUIRED', 'Age', 'Отсутствует плашка возраста', 2),
    
    # B. Prohibited
    ('OBSCENE_PROFANITY_BANNED', 'Prohibited', 'Нецензурная брань (мат)', 3),
    ('PORNOGRAPHY_BANNED', 'Prohibited', 'Порнография', 3),
    ('EXTREMISM_CALLS', 'Prohibited', 'Призывы к экстремизму', 3),
    
    # C. Language
    ('PROFANITY_NON_OBSCENE_16PLUS', 'Language', 'Бранная лексика (грубая)', 1),
    
    # D. LGBT
    ('LGBT_TOPIC_RESTRICTED', 'LGBT', 'ЛГБТ тематика (ограничение по времени)', 2),
    ('LGBT_PROPAGANDA_PROHIBITED', 'LGBT', 'Пропаганда ЛГБТ', 3),
    
    # F. Privacy / Image
    ('PERSONAL_DATA', 'Privacy', 'Персональные данные', 2),
    ('IMAGE_CONSENT_REQUIRED', 'Privacy', 'Изображение гражданина без согласия', 2),
    
    # I. Foreign Agents / Meta
    ('FOREIGN_AGENT_LABEL_REQUIRED', 'Legal', 'Иноагент без маркировки', 3),
    ('META_LOGO_BANNED', 'Legal', 'Логотип Meta/Instagram/FB', 3),
    
    # J. Tobacco
    ('TOBACCO_DISPLAY', 'Substances', 'Демонстрация табака', 1),
    ('DRUGS_PROMOTION', 'Substances', 'Пропаганда наркотиков', 3),
]

with engine.connect() as conn:
    print("Seeding Taxonomy...")
    for code, group, title, sev in taxonomy_data:
        sql = text("""
            INSERT INTO taxonomy_label (code, group_name, title, default_severity)
            VALUES (:code, :grp, :title, :sev)
            ON CONFLICT (code) DO UPDATE SET 
            title = EXCLUDED.title, default_severity = EXCLUDED.default_severity;
        """)
        conn.execute(sql, {"code": code, "grp": group, "title": title, "sev": sev})
        conn.commit()
    print("Done!")