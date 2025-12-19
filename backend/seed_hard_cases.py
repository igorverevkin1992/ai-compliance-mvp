import os
import json
import time
from sqlalchemy import create_engine, text
import google.generativeai as genai

# Импортируем нашу схему базы данных, чтобы создать таблицы
from database import Base, engine as db_engine

# --- НАСТРОЙКИ ---
DATABASE_URL = os.getenv("DATABASE_URL") 
GEMINI_API_KEY = "AIzaSyCV0BkgxRfEAR6D2c7extMk7F3eUSCMip8" # Замени на реальный ключ

genai.configure(api_key=GEMINI_API_KEY)
engine = create_engine(DATABASE_URL)

def get_vector(text_to_embed):
    try:
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text_to_embed,
            task_type="retrieval_document"
        )
        return result['embedding']
    except Exception as e:
        print(f"⚠️ Ошибка эмбеддинга: {e}")
        return None

# Твои 10 кейсов (те же самые)
hard_cases = [
    {
        "title": "Фейк о ВС РФ в ток-шоу",
        "description": "Гость заявляет: 'Российская армия намеренно бомбит гражданских ежедневно'. Утверждение подано как факт без опровержения.",
        "risk": "CRITICAL",
        "json": {
            "overall": {"risk_level": "CRITICAL", "confidence": 1.0, "age_rating": "18+", "summary": "Публичное распространение заведомо ложной информации о ВС РФ (ст. 207.3 УК РФ)."},
            "labels": [{"code": "EXTREMISM_PROMOTION", "severity": 3, "confidence": 1.0, "rationale": "Утверждение о преднамеренных ударах по гражданским лицам без официальных подтверждений классифицируется как военный фейк."}],
            "recommendations": [{"action": "CUT", "priority": "P0", "expected_effect": "Полное удаление высказывания во избежание уголовного преследования канала."}]
        }
    },
    {
        "title": "Дискредитация армии (Визуальный плакат)",
        "description": "В прямом эфире музыкального стрима артист показывает антивоенный плакат с надписью 'Нет войне'.",
        "risk": "CRITICAL",
        "json": {
            "overall": {"risk_level": "CRITICAL", "confidence": 1.0, "age_rating": "18+", "summary": "Нарушение ст. 280.3 УК РФ (дискредитация ВС РФ)."},
            "labels": [{"code": "EXTREMISM_PROMOTION", "severity": 3, "confidence": 1.0, "rationale": "Лозунг 'Нет войне' признается дискредитацией армии."}],
            "recommendations": [{"action": "CUT", "priority": "P0", "expected_effect": "Исключение эпизода из записи."}]
        }
    },
    {
        "title": "Призывы к экстремизму под видом шутки",
        "description": "Блогер говорит: 'А давайте-ка... вы знаете... кое-что взорвем'.",
        "risk": "CRITICAL",
        "json": {
            "overall": {"risk_level": "CRITICAL", "confidence": 1.0, "age_rating": "18+", "summary": "Призывы к терроризму (ст. 280 УК РФ)."},
            "labels": [{"code": "EXTREMISM_CALLS", "severity": 3, "confidence": 1.0, "rationale": "Явный призыв к взрывам."}],
            "recommendations": [{"action": "CUT", "priority": "P0", "expected_effect": "Запрет к публикации."}]
        }
    },
    {
        "title": "ЛГБТ-пропаганда в сериале",
        "description": "Сцены поцелуев однополых партнеров.",
        "risk": "CRITICAL",
        "json": {
            "overall": {"risk_level": "CRITICAL", "confidence": 1.0, "age_rating": "18+", "summary": "Нарушение ст. 6.21 КоАП РФ."},
            "labels": [{"code": "LGBT_PROPAGANDA_PROHIBITED", "severity": 3, "confidence": 1.0, "rationale": "Пропаганда нетрадиционных отношений."}],
            "recommendations": [{"action": "CUT", "priority": "P0", "expected_effect": "Удаление сцен."}]
        }
    },
    {
        "title": "Отсутствие маркировки Иноагента",
        "description": "Интервью с иноагентом без плашки.",
        "risk": "HIGH",
        "json": {
            "overall": {"risk_level": "HIGH", "confidence": 1.0, "age_rating": "18+", "summary": "Нарушение ФЗ-255."},
            "labels": [{"code": "FOREIGN_AGENT_LABEL_REQUIRED", "severity": 2, "confidence": 1.0, "rationale": "Нет маркировки."}],
            "recommendations": [{"action": "OVERLAY", "priority": "P1", "params": {"text": "ДАННОЕ СООБЩЕНИЕ..."}, "expected_effect": "Соблюдение закона."}]
        }
    },
    {
        "title": "Мат в интернет-стриме",
        "description": "Ведущий использует мат в эфире 18+.",
        "risk": "MEDIUM",
        "json": {
            "overall": {"risk_level": "MEDIUM", "confidence": 0.9, "age_rating": "18+", "summary": "Мат в интернете."},
            "labels": [{"code": "PROFANITY", "severity": 1, "confidence": 1.0, "rationale": "Мат допустим под 18+."}],
            "recommendations": [{"action": "AGE_GATE", "priority": "P2", "expected_effect": "Метка 18+."}]
        }
    },
    {
        "title": "Пропаганда Childfree",
        "description": "Блогер агрессивно призывает отказываться от детей.",
        "risk": "HIGH",
        "json": {
            "overall": {"risk_level": "HIGH", "confidence": 0.9, "age_rating": "18+", "summary": "Пропаганда чайлдфри."},
            "labels": [{"code": "LGBT_PROPAGANDA_PROHIBITED", "severity": 2, "confidence": 0.9, "rationale": "Навязывание отказа от детей."}],
            "recommendations": [{"action": "LEGAL_REVIEW", "priority": "P1", "expected_effect": "Анализ юриста."}]
        }
    },
    {
        "title": "Оскорбление чувств верующих",
        "description": "Актер пародирует молитву и гасит свечу жестом в храме.",
        "risk": "HIGH",
        "json": {
            "overall": {"risk_level": "HIGH", "confidence": 1.0, "age_rating": "18+", "summary": "Нарушение ст. 148 УК РФ."},
            "labels": [{"code": "HATE_SPEECH", "severity": 3, "confidence": 1.0, "rationale": "Осквернение обрядов."}],
            "recommendations": [{"action": "CUT", "priority": "P0", "expected_effect": "Удаление фрагмента."}]
        }
    },
    {
        "title": "Способы употребления наркотиков",
        "description": "Демонстрация приготовления смеси.",
        "risk": "CRITICAL",
        "json": {
            "overall": {"risk_level": "CRITICAL", "confidence": 1.0, "age_rating": "18+", "summary": "Пропаганда наркотиков (ст. 6.13 КоАП)."},
            "labels": [{"code": "DRUGS_PROMOTION", "severity": 3, "confidence": 1.0, "rationale": "Показ приготовления."}],
            "recommendations": [{"action": "BLUR", "priority": "P0", "expected_effect": "Скрытие процесса."}]
        }
    },
    {
        "title": "Жестокое обращение с животными",
        "description": "Пранк с имитацией утопления кота.",
        "risk": "CRITICAL",
        "json": {
            "overall": {"risk_level": "CRITICAL", "confidence": 1.0, "age_rating": "18+", "summary": "Нарушение ст. 245 УК РФ."},
            "labels": [{"code": "VIOLENCE", "severity": 3, "confidence": 1.0, "rationale": "Истязание животного."}],
            "recommendations": [{"action": "LEGAL_REVIEW", "priority": "P0", "expected_effect": "Снятие с публикации."}]
        }
    }
]

def seed():
    # 1. СОЗДАЕМ ТАБЛИЦЫ, ЕСЛИ ИХ НЕТ
    print("🛠 Инициализация таблиц базы данных...")
    Base.metadata.create_all(bind=db_engine)

    with engine.connect() as conn:
        print("🚀 Загрузка Золотых Кейсов...")
        
        # Проверка на наличие ассета
        asset_id = conn.execute(text("""
            INSERT INTO media_asset (filename, metadata) 
            VALUES ('Compliance_Bible_Expert_Guide', '{"type": "gold_dataset", "version": "1.1"}') 
            RETURNING id
        """)).scalar()

        for case in hard_cases:
            # 2. Сохраняем в human_review
            review_id = conn.execute(text("""
                INSERT INTO human_review (asset_id, final_risk, notes, verified_json, status)
                VALUES (:aid, :risk, :notes, :v_json, 'DONE')
                RETURNING id
            """), {
                "aid": asset_id, 
                "risk": case['risk'], 
                "notes": f"CASE: {case['title']}. DESC: {case['description']}",
                "v_json": json.dumps(case['json'])
            }).scalar()

            # 3. Вектор
            search_text = f"{case['title']} {case['description']}"
            vector = get_vector(search_text)
            
            if vector:
                conn.execute(text("""
                    INSERT INTO case_memory (review_id, memory_type, text, embedding, meta)
                    VALUES (:rid, 'EXPERT_GOLD_CASE', :txt, :vec, :meta)
                """), {
                    "rid": review_id,
                    "txt": f"КЕЙС: {case['description']} | ВЕРДИКТ: {case['risk']}",
                    "vec": str(vector),
                    "meta": json.dumps({"title": case['title'], "source": "Bible"})
                })
                print(f"✅ Готово: {case['title']}")
        
        conn.commit()
    print("\n✨ БАЗА ЗНАНИЙ ОБНОВЛЕНА.")

if __name__ == "__main__":
    seed()