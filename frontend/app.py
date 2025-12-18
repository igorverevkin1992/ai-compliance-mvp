import streamlit as st
import pandas as pd
import requests
import time
import os
import json
import xml.etree.ElementTree as ET
from xml.dom import minidom

# --- КОНФИГУРАЦИЯ ---
st.set_page_config(
    page_title="AI-Lawyer Enterprise",
    page_icon="⚖️",
    layout="wide"
)

# Адрес бэкенда
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

# --- СТИЛИ CSS ---
st.markdown("""
    <style>
    .risk-high { color: #ff4b4b; font-weight: bold; }
    .risk-medium { color: #ffa726; font-weight: bold; }
    .risk-safe { color: #00c853; font-weight: bold; }
    .stButton button { width: 100%; }
    /* Делаем таблицу более компактной */
    div[data-testid="stDataFrame"] { width: 100%; }
    </style>
""", unsafe_allow_html=True)

# --- ИНИЦИАЛИЗАЦИЯ ПАМЯТИ ---
if 'analysis_result' not in st.session_state: st.session_state.analysis_result = None
if 'asset_id' not in st.session_state: st.session_state.asset_id = None
if 'available_models' not in st.session_state: st.session_state.available_models = []
if 'valid_key' not in st.session_state: st.session_state.valid_key = False
if 'filename' not in st.session_state: st.session_state.filename = None

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def flatten_report_for_editor(report):
    """Превращает сложный вложенный JSON в плоскую таблицу для редактора"""
    flat_rows = []
    
    # Создаем словарь доказательств для быстрого поиска: id -> {start, end, quote}
    evidence_map = {e['id']: e for e in report.get('evidence', [])}
    
    labels = report.get('labels', [])
    if not labels:
        return pd.DataFrame(columns=["start", "end", "severity", "code", "rationale", "quote"])

    for lbl in labels:
        # Ищем связанные доказательства (таймкоды)
        evidence_ids = lbl.get('evidence_ids', [])
        
        # Если доказательств нет, создаем строку без времени
        if not evidence_ids:
            flat_rows.append({
                "start": "00:00:00",
                "end": "00:00:00",
                "severity": lbl.get('severity', 0),
                "code": lbl.get('code', 'UNKNOWN'),
                "rationale": lbl.get('rationale', ''),
                "quote": ""
            })
            continue

        # Если есть доказательства, создаем строку для каждого куска
        for eid in evidence_ids:
            ev = evidence_map.get(eid, {})
            # Форматируем время
            s_ms = ev.get('start_ms', 0) or 0
            e_ms = ev.get('end_ms', 0) or 0
            
            start_fmt = time.strftime('%H:%M:%S', time.gmtime(s_ms / 1000))
            end_fmt = time.strftime('%H:%M:%S', time.gmtime(e_ms / 1000))
            
            flat_rows.append({
                "start": start_fmt,
                "end": end_fmt,
                "severity": lbl.get('severity', 0),
                "code": lbl.get('code', 'UNKNOWN'),
                "rationale": lbl.get('rationale', ''),
                "quote": ev.get('text_quote', '') or ev.get('notes', '')
            })
            
    return pd.DataFrame(flat_rows)

def generate_premiere_xml(df, filename):
    """Генерация XML из DataFrame"""
    root = ET.Element("xmeml", version="4")
    sequence = ET.SubElement(root, "sequence")
    ET.SubElement(sequence, "name").text = f"Analyzed_{filename}"
    rate = ET.SubElement(sequence, "rate")
    ET.SubElement(rate, "timebase").text = "25"

    for _, row in df.iterrows():
        # Игнорируем зеленые/безопасные строки при экспорте в монтажку
        # (предполагаем, что severity 0 - это безопасно)
        if row.get('severity') == 0: continue
        
        marker = ET.SubElement(sequence, "marker")
        try:
            # Парсим HH:MM:SS обратно в кадры
            parts = str(row['start']).split(':')
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            total_seconds = h*3600 + m*60 + s
            start_frame = total_seconds * 25
        except:
            start_frame = 0
            
        ET.SubElement(marker, "name").text = f"[{row.get('severity')}] {row.get('code')}"
        ET.SubElement(marker, "comment").text = str(row.get('rationale'))
        ET.SubElement(marker, "in").text = str(start_frame)
        ET.SubElement(marker, "out").text = str(start_frame + 125) 

    return minidom.parseString(ET.tostring(root)).toprettyxml(indent="   ")

def color_rows(row):
    """Раскраска таблицы"""
    sev = row.get('severity', 0)
    color = 'white'
    if sev == 3: color = '#ffcccc' # RED
    elif sev == 2: color = '#ffe5cc' # ORANGE
    elif sev == 1: color = '#ffffcc' # YELLOW
    elif sev == 0: color = '#ccffcc' # GREEN
    return [f'background-color: {color}; color: black'] * len(row)

# --- ИНТЕРФЕЙС (UI) ---

st.title("⚖️ AI-Lawyer Enterprise v6.2 (Full Suite)")

# --- БОКОВАЯ ПАНЕЛЬ ---
with st.sidebar:
    st.header("Профиль проверки")
    profile = st.selectbox(
        "Стандарт:", 
        ["ntv", "youtube"],
        format_func=lambda x: "📺 НТВ (ТВ-вещание)" if x == "ntv" else "▶️ YouTube / Блогеры"
    )
    api_key = st.text_input("Gemini API Key", type="password")
    
    if api_key:
        if st.button("🔄 Проверить ключ и найти модели"):
            with st.spinner("Проверка..."):
                try:
                    res = requests.post(f"{BACKEND_URL}/list-models", json={"api_key": api_key})
                    if res.status_code == 200:
                        models = res.json().get("models", [])
                        st.session_state.available_models = models
                        st.session_state.valid_key = True
                        st.success(f"Доступно: {len(models)}")
                    else:
                        st.error("Ключ не подходит")
                        st.session_state.valid_key = False
                except Exception as e:
                    st.error(f"Ошибка сети: {e}")

    # Выбор модели
    model_opts = st.session_state.available_models
    default_idx = 0
    # Пытаемся найти 1.5 flash как дефолт
    for i, m in enumerate(model_opts):
        if "1.5-flash" in m: default_idx = i; break
            
    selected_model = "gemini-1.5-flash"
    if st.session_state.valid_key and model_opts:
        selected_model = st.selectbox("Модель:", model_opts, index=default_idx)
    
    st.markdown("---")
    st.caption("🔴 Severity 3: CRITICAL")
    st.caption("🟠 Severity 2: MEDIUM")
    st.caption("🟡 Severity 1: LOW")
    st.caption("🟢 Severity 0: SAFE")

# --- ЗАГРУЗКА ---
st.subheader("1. Загрузка материала")
uploaded_file = st.file_uploader("Файл", type=['mp4', 'mov', 'mp3', 'wav', 'ogg', 'docx', 'pdf'])

if uploaded_file and st.session_state.valid_key:
    if st.button("🚀 Запустить анализ", type="primary"):
        # 1. Сбрасываем старые результаты
        st.session_state.analysis_result = None
        st.session_state.asset_id = None
        st.session_state.last_profile = profile
        
        # 2. Создаем статус-бар (он не блокирует интерфейс как spinner)
        status_container = st.status("🚀 Инициализация...", expanded=True)
        
        try:
            # Подготовка данных
            ext = uploaded_file.name.split('.')[-1]
            safe_filename = f"input_file.{ext}"
            files = {"file": (safe_filename, uploaded_file, uploaded_file.type)}
            data = {"original_filename": uploaded_file.name, "model_name": selected_model, "profile":profile}
            headers = {"X-API-Key": api_key}
            
            status_container.write("📤 Загрузка файла на сервер...")
            
            # Отправка (таймаут 10 минут)
            res = requests.post(f"{BACKEND_URL}/analyze", files=files, data=data, headers=headers, timeout=600)
            
            if res.status_code == 200:
                task_id = res.json()['task_id']
                status_container.write(f"⚙️ Задача ID: {task_id}. Анализ начат...")
                
                # Цикл опроса (Polling)
                last_status_msg = ""  # <--- 1. Переменная для запоминания
                
                while True:
                    time.sleep(2)
                    try:
                        s_res = requests.get(f"{BACKEND_URL}/status/{task_id}")
                        s_data = s_res.json()
                        state = s_data.get("state")
                        
                        if state == 'SUCCESS':
                            status_container.update(label="✅ Анализ завершен!", state="complete", expanded=False)
                            
                            st.session_state.analysis_result = s_data.get("result", {})
                            st.session_state.asset_id = st.session_state.analysis_result.get('_asset_id')
                            st.session_state.filename = uploaded_file.name
                            
                            st.rerun()
                            break
                        
                        elif state == 'FAILURE':
                            status_container.update(label="❌ Ошибка", state="error")
                            st.error(f"Ошибка задачи: {s_data.get('error')}")
                            break
                            
                        elif state == 'PROGRESS':
                            msg = s_data.get("status", "Обработка...")
                            
                            # <--- 2. ПРОВЕРКА: Пишем только если статус изменился
                            if msg != last_status_msg:
                                status_container.write(f"🔄 {msg}")
                                last_status_msg = msg 
                            # ----------------------------------------------------
                            
                    except Exception:
                        pass
            else:
                status_container.update(label="❌ Ошибка сервера", state="error")
                st.error(f"Код {res.status_code}: {res.text}")
                
        except Exception as e:
            status_container.update(label="❌ Ошибка соединения", state="error")
            st.error(str(e))

elif uploaded_file and not st.session_state.valid_key:
    st.warning("⚠️ Пожалуйста, введите API Key и нажмите 'Проверить ключ' в меню слева.")

# --- ДАШБОРД ---
if st.session_state.analysis_result:
    res = st.session_state.analysis_result
    
    if isinstance(res, dict) and "error" in res:
        st.error(f"AI вернул ошибку: {res['error']}")
    else:
        st.divider()
        st.subheader("2. Результаты анализа")
        
        # СВОДКА
        overall = res.get('overall', {})
        risk = overall.get('risk_level', 'UNKNOWN')
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Риск", risk)
        c2.metric("Возраст", overall.get('age_rating', 'N/A'))
        c3.metric("Доверие", f"{overall.get('confidence', 0)*100:.0f}%")
        c4.metric("Найдено", len(res.get('labels', [])))
        
        st.info(f"📝 {overall.get('summary', 'Нет резюме')}")

        retrieved_context = res.get('_retrieved_context', 'Нет данных')
        with st.expander("🔍 AI Context: На чем основано решение (RAG)"):
            st.write("**Найденные похожие случаи из вашей базы знаний:**")
            if "Похожих примеров не найдено" in retrieved_context or not retrieved_context:
                st.caption("База знаний пока пуста или нет подходящих случаев.")
            else:
                st.markdown(retrieved_context)
        
        policy_tab_name = "📜 Политики YouTube" if st.session_state.get('last_profile') == 'youtube' else "📜 Политики НТВ"

        # Создаем табы с переменной
        tab_list, tab_policy, tab_rec, tab_train = st.tabs([
            "📋 Детальная Таблица", 
            policy_tab_name,  # <--- Теперь здесь переменная
            "✂️ Рекомендации", 
            "🎓 Обучение (RAG)"
        ])
        
        # 1. ТАБЛИЦА (РЕДАКТОР)
        with tab_list:
            st.write("Вы можете редактировать таблицу: менять Severity на 0 (Безопасно), править описание.")
            
            # Превращаем сложный JSON в плоский DataFrame
            flat_df = flatten_report_for_editor(res)
            
            # Настройка колонок для редактора
            col_config = {
                "severity": st.column_config.NumberColumn("Степень (0-3)", min_value=0, max_value=3, help="0=Safe, 3=Critical"),
                "code": st.column_config.TextColumn("Код нарушения"),
                "rationale": st.column_config.TextColumn("Причина / Контекст", width="large"),
                "start": st.column_config.TextColumn("Начало"),
                "end": st.column_config.TextColumn("Конец"),
                "quote": st.column_config.TextColumn("Цитата/Деталь")
            }
            
            edited_df = st.data_editor(
                flat_df,
                use_container_width=True,
                num_rows="dynamic",
                column_config=col_config,
                key="editor_main"
            )
            
            # Скачивание CSV
            st.download_button(
                "📥 Скачать таблицу (CSV)",
                edited_df.to_csv(index=False).encode('utf-8'),
                "report.csv",
                "text/csv"
            )

        # 2. ПОЛИТИКИ
        with tab_policy:
            policies = res.get('policy_hits', [])
            if not policies: st.success("Нарушений политик НТВ не найдено.")
            for p in policies:
                st.error(f"**{p.get('req_code')}**: {p.get('why')}")
                st.caption(f"Приоритет: {p.get('priority')}")
                
        # 3. РЕКОМЕНДАЦИИ И XML
        with tab_rec:
            recs = res.get('recommendations', [])
            if recs:
                r_df = pd.DataFrame(recs)
                # Оставляем читаемые колонки
                if not r_df.empty:
                    st.dataframe(r_df[['action', 'priority', 'expected_effect']], use_container_width=True)
            else:
                st.info("Нет автоматических рекомендаций.")
            
            # Кнопка XML на основе ОТРЕДАКТИРОВАННОЙ таблицы
            st.write("---")
            current_file = st.session_state.filename or "video"
            if "mp4" in current_file or "mov" in current_file or "wav" in current_file:
                try:
                    xml_data = generate_premiere_xml(edited_df, current_file)
                    st.download_button("🎬 Скачать XML для Premiere Pro", xml_data, "markers.xml", "text/xml")
                except Exception as e:
                    st.warning(f"Не удалось создать XML: {e}")

        # 4. ПАНЕЛЬ УЧИТЕЛЯ (ОБУЧЕНИЕ)
        with tab_train:
            st.header("🧑‍🏫 Обучение Агента")
            st.write("Сохраните ваши правки в Базу Знаний. При следующем анализе Агент учтет этот опыт.")
            
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                risk_opts = ["SAFE", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
                # Пытаемся найти текущий индекс
                try: d_idx = risk_opts.index(risk)
                except: d_idx = 0
                new_risk = st.selectbox("Итоговый вердикт:", risk_opts, index=d_idx)
            
            user_note = st.text_area(
                "Комментарий учителя (Почему?):", 
                placeholder="Например: Это комедийная сцена, крики являются частью игры..."
            )
            
            if st.button("💾 Сохранить урок в Базу"):
                if st.session_state.asset_id:
                    # Собираем данные из РЕДАКТОРА
                    verified_data = edited_df.to_dict(orient='records')
                    
                    payload = {
                        "asset_id": str(st.session_state.asset_id),
                        "final_risk": new_risk,
                        "user_comment": user_note,
                        "verified_json": verified_data, # Отправляем исправленную таблицу!
                        "rating": 5
                    }
                    
                    try:
                        r = requests.put(f"{BACKEND_URL}/verify", json=payload)
                        if r.status_code == 200:
                            st.success("✅ Опыт сохранен! Агент стал умнее.")
                            st.balloons()
                        else:
                            st.error(f"Ошибка сохранения: {r.text}")
                    except Exception as e:
                        st.error(f"Связь: {e}")
                else:
                    st.error("Нет ID ассета. Перезапустите анализ.")