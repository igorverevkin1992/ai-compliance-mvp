import os
from sqlalchemy import create_engine, text
import uuid

# Вставь ссылку Supabase
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

def seed_rutube_rules():
    with engine.connect() as conn:
        print("▶️ Загрузка Правил RUTUBE в базу...")
        
        # 1. Генерируем ID в Python
        doc_id = uuid.uuid4()
        
        # 2. Передаем его в запрос
        conn.execute(text("""
            INSERT INTO legal_doc (id, publisher, title, version) 
            VALUES (:id, 'РФ', 'Название...', 'версия...')
        """), {"id": doc_id})
        
        requirements = [
            {
                "code": "RUTUBE_TOXIC_CONTENT",
                "type": "PROHIBITED",
                "risk": "HIGH",
                "summary": "Запрет на токсичный и разобщающий контент.",
                "text": "Пункт 29: Администрация вправе отказать в публикации контента, который носит токсично провокационный и разоблачающий характер в деструктивной форме, может быть воспринят как пропаганда определенных взглядов и стать причиной недружественного разобщения сообщества."
            },
            {
                "code": "RUTUBE_ILLEGAL_LIST",
                "type": "PROHIBITED",
                "risk": "CRITICAL",
                "summary": "Общий запрет на противоправный контент (экстремизм, фейки, нежелательные организации).",
                "text": "Пункт 29: Запрещен контент, содержащий: призывы к массовым беспорядкам; недостоверную общественно значимую информацию (фейки); материалы нежелательных организаций; оскорбление госсимволов и Конституции РФ."
            },
            {
                "code": "RUTUBE_COPYRIGHT",
                "type": "MANDATORY",
                "risk": "HIGH",
                "summary": "Гарантия авторских прав.",
                "text": "Пункт 7: Пользователь гарантирует, что обладает всеми правами на контент. В случае сомнений Администрация вправе заблокировать контент или запросить документы."
            },
            {
                "code": "RUTUBE_AGE_MARKER",
                "type": "MANDATORY",
                "risk": "MEDIUM",
                "summary": "Обязательная возрастная маркировка.",
                "text": "Пункт 19: Пользователь обязан сопроводить контент отметкой о возрастных ограничениях (0+, 12+, 18+) любым доступным способом."
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
        print("✅ Правила RUTUBE успешно загружены.")

if __name__ == "__main__":
    seed_rutube_rules()