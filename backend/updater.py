import requests
import json
import os

REGISTRIES_FOLDER = "registries"
os.makedirs(REGISTRIES_FOLDER, exist_ok=True)

# Ссылки на зеркала открытых данных (Open Data)
URL_FOREIGN_AGENTS = "https://raw.githubusercontent.com/official-open-data/foreign-agents/main/json/agents.json"
# Зеркало Федерального списка экстремистских материалов (обновляется сообществом)
URL_EXTREMIST_MATERIALS = "https://raw.githubusercontent.com/official-open-data/extremist-materials/main/json/materials.json"


def download_json(url, filename, key_filter=None):
    """
    Скачивает JSON. Если указан key_filter, сохраняет только это поле,
    чтобы уменьшить размер файла (актуально для списка материалов).
    """
    print(f"⬇️ Скачивание {filename}...")
    try:
        response = requests.get(url, timeout=30)  # Таймаут побольше, файлы большие
        response.raise_for_status()

        raw_data = response.json()

        final_data = []
        if key_filter:
            # Оптимизация: берем только текст описания
            print(f"⚙️ Оптимизация {filename}...")
            for item in raw_data:
                # В разных версиях JSON поле может называться 'name' или 'text'
                val = item.get(key_filter) or item.get("name") or item.get("text")
                if val:
                    final_data.append(val)
        else:
            final_data = raw_data

        save_path = os.path.join(REGISTRIES_FOLDER, filename)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(final_data, f, ensure_ascii=False, indent=2)

        print(f"✅ Успешно! Записей: {len(final_data)}")
        return len(final_data)

    except Exception as e:
        print(f"❌ Ошибка скачивания {filename}: {e}")
        # Если не скачалось, создаем пустой файл, чтобы сервер не падал
        if not os.path.exists(os.path.join(REGISTRIES_FOLDER, filename)):
            with open(os.path.join(REGISTRIES_FOLDER, filename), "w") as f:
                json.dump([], f)
        return 0


def update_foreign_agents():
    # Полный список иноагентов
    return download_json(URL_FOREIGN_AGENTS, "foreign_agents.json")


def update_extremist_materials():
    # Федеральный список экстремистских материалов (Книги, Песни, Лозунги)
    # Фильтруем, оставляем только само описание ('text'), чтобы нейросети было проще читать
    return download_json(
        URL_EXTREMIST_MATERIALS, "extremist_materials.json", key_filter="text"
    )


def update_rosfin_terrorists():
    """
    Перечень террористов и экстремистов (Организации).
    Официальный список Росфинмониторинга закрыт.
    Здесь мы используем 'Hardcoded Seed' самых известных запрещенных организаций.
    В Enterprise-версии здесь должен быть API-запрос к платному провайдеру (Kontur/Spark).
    """
    filename = "rosfin_terrorists.json"
    print(f"🔄 Обновление {filename} (Базовый перечень)...")

    base_data = [
        {"name": "Meta Platforms Inc.", "status": "Экстремистская"},
        {"name": "Facebook", "status": "Экстремистская соцсеть"},
        {"name": "Instagram", "status": "Экстремистская соцсеть"},
        {"name": "Штабы Навального", "status": "Экстремистская"},
        {"name": "ФБК (Фонд борьбы с коррупцией)", "status": "Экстремистская"},
        {"name": "Азов", "status": "Террористическая"},
        {"name": "ЛГБТ", "status": "Экстремистское движение"},
        {"name": "ИГИЛ (Исламское государство)", "status": "Террористическая"},
        {"name": "Джебхат ан-Нусра", "status": "Террористическая"},
        {"name": "Аль-Каида", "status": "Террористическая"},
        {"name": "Талибан", "status": "Террористическая"},
        {"name": "Колумбайн", "status": "Террористическая"},
        {"name": "АУЕ", "status": "Экстремистская"},
        {"name": "Правый сектор", "status": "Экстремистская"},
        {"name": "Свидетели Иеговы", "status": "Экстремистская"},
    ]

    save_path = os.path.join(REGISTRIES_FOLDER, filename)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(base_data, f, ensure_ascii=False, indent=2)

    print(f"✅ Базовый список террористов обновлен.")
    return len(base_data)


def run_global_update():
    c1 = update_foreign_agents()
    c2 = update_rosfin_terrorists()
    c3 = update_extremist_materials()
    return {
        "status": "success",
        "updated_agents": c1,
        "updated_terrorists": c2,
        "updated_materials": c3,
    }


if __name__ == "__main__":
    run_global_update()
