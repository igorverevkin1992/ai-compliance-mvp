import streamlit as st
import pandas as pd
import requests
import time
import os
import xml.etree.ElementTree as ET
from xml.dom import minidom

# --- КОНФИГУРАЦИЯ ---
st.set_page_config(
    page_title="AI-Lawyer Enterprise",
    page_icon="⚖️",
    layout="wide"
)

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

# --- ИНИЦИАЛИЗАЦИЯ ПАМЯТИ (SESSION STATE) ---
# Это нужно, чтобы результаты не исчезали при кликах
if 'analysis_result' not in st.session_state:
    st.session_state.analysis_result = None
if 'record_id' not in st.session_state:
    st.session_state.record_id = None
if 'filename' not in st.session_state:
    st.session_state.filename = None

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def generate_premiere_xml(df, filename):
    root = ET.Element("xmeml", version="4")
    sequence = ET.SubElement(root, "sequence")
    ET.SubElement(sequence, "name").text = f"Analyzed_{filename}"
    rate = ET.SubElement(sequence, "rate")
    ET.SubElement(rate, "timebase").text = "25"

    for _, row in df.iterrows():
        if row.get('risk_level') in ['GREEN', 'SAFE']: continue
        marker = ET.SubElement(sequence, "marker")
        try:
            h, m, s = map(int, str(row['start']).split(':'))
            start_frame = (h * 3600 + m * 60 + s) * 25
        except: start_frame = 0
            
        ET.SubElement(marker, "name").text = f"[{row['risk_level']}] {row['category']}"
        ET.SubElement(marker, "comment").text = f"{row['description']} ({row['quote']})"
        ET.SubElement(marker, "in").text = str(start_frame)
        ET.SubElement(marker, "out").text = str(start_frame + 125) 
    return minidom.parseString(ET.tostring(root)).toprettyxml(indent="   ")

def color_rows(row):
    colors = {
        "RED": "#ffcccc", "ORANGE": "#ffe5cc", "YELLOW": "#ffffcc", 
        "PURPLE": "#e6ccff", "GREEN": "#ccffcc", "SAFE": "#ccffcc"
    }
    return [f'background-color: {colors.get(row.get("risk_level"), "white")}; color: black'] * len(row)

# --- ИНТЕРФЕЙС ---
st.title("⚖️ AI-Lawyer Enterprise v5.4 (Stable)")

with st.sidebar:
    st.header("Настройки")
    api_key = st.text_input("Gemini API Key", type="password")
    st.markdown("---")
    st.markdown("**Легенда:** 🔴 RED, 🟠 ORANGE, 🟣 PURPLE, 🟡 YELLOW, 🟢 GREEN")

# 1. ЗАГРУЗКА
st.subheader("1. Загрузка контента")
uploaded_file = st.file_uploader("Выберите файл", type=['mp4', 'mov', 'mp3', 'wav', 'txt', 'docx', 'pdf'])

# Логика запуска анализа
if uploaded_file and api_key:
    if st.button("🚀 Запустить анализ"):
        with st.spinner("Обработка..."):
            try:
                # Сброс старых результатов перед новым запуском
                st.session_state.analysis_result = None
                st.session_state.record_id = None
                
                # Подготовка
                ext = uploaded_file.name.split('.')[-1]
                safe_filename = f"input_file.{ext}"
                files = {"file": (safe_filename, uploaded_file, uploaded_file.type)}
                data = {"original_filename": uploaded_file.name}
                headers = {"X-API-Key": api_key}
                
                # Старт задачи
                res = requests.post(f"{BACKEND_URL}/analyze", files=files, data=data, headers=headers, timeout=600)
                
                if res.status_code == 200:
                    task_id = res.json()['task_id']
                    st.info(f"Задача ID: {task_id}. Ожидание...")
                    
                    # Polling
                    while True:
                        time.sleep(3)
                        status_res = requests.get(f"{BACKEND_URL}/status/{task_id}")
                        status_data = status_res.json()
                        state = status_data.get("state")
                        
                        if state == 'SUCCESS':
                            # !!! СОХРАНЯЕМ В ПАМЯТЬ СЕССИИ !!!
                            st.session_state.analysis_result = status_data.get("result", [])
                            st.session_state.filename = uploaded_file.name
                            
                            # Пытаемся достать ID записи базы данных сразу
                            res_data = st.session_state.analysis_result
                            if isinstance(res_data, list) and len(res_data) > 0 and '_db_id' in res_data[0]:
                                st.session_state.record_id = res_data[0]['_db_id']
                            elif isinstance(res_data, dict) and '_db_id' in res_data:
                                st.session_state.record_id = res_data['_db_id']
                            
                            st.rerun() # Перезагружаем страницу, чтобы отобразить результаты
                            break
                        elif state == 'FAILURE':
                            st.error(f"Ошибка: {status_data.get('error')}")
                            st.stop()
                else:
                    st.error(f"Ошибка запуска: {res.text}")
            except Exception as e:
                st.error(f"Ошибка: {e}")

# 2. ОТОБРАЖЕНИЕ РЕЗУЛЬТАТОВ (Берем из памяти)
if st.session_state.analysis_result is not None:
    st.divider()
    st.subheader("2. Результаты анализа")
    
    result_data = st.session_state.analysis_result
    
    if isinstance(result_data, dict) and "error" in result_data:
        st.error(result_data['error'])
    else:
        # Нормализация данных
        if isinstance(result_data, dict): result_data = [result_data]
        
        # Проверка на пустой результат (Empty Result)
        is_empty = (len(result_data) == 1 and result_data[0].get('info') == 'Empty result')
        if is_empty:
            st.success("✅ Нарушений не найдено!")
            # Создаем пустой датафрейм для ручного добавления
            df = pd.DataFrame(columns=["start", "end", "risk_level", "category", "description", "quote"])
        else:
            df = pd.DataFrame(result_data)
            
        # Фильтрация колонок
        wanted_cols = ["start", "end", "risk_level", "category", "description", "quote"]
        cols = [c for c in wanted_cols if c in df.columns]
        if not cols: cols = df.columns.tolist() # Fallback
        
        # === РЕДАКТОР ===
        st.info("💡 Редактируйте таблицу ниже. Нажмите '+', чтобы добавить строку.")
        edited_df = st.data_editor(
            df[cols],
            use_container_width=True,
            num_rows="dynamic", # Разрешаем добавление строк
            key="main_editor"   # Уникальный ключ
        )
        
        # КНОПКА СОХРАНЕНИЯ (Используем ID из памяти)
        if st.session_state.record_id:
            if st.button("💾 Сохранить правки (Обучить AI)", type="primary"):
                verified_json = edited_df.to_dict(orient='records')
                payload = {
                    "record_id": st.session_state.record_id, 
                    "verified_json": verified_json, 
                    "rating": 5
                }
                try:
                    ver_res = requests.put(f"{BACKEND_URL}/verify", json=payload)
                    if ver_res.status_code == 200:
                        st.success("Сохранено в базу данных!")
                    else:
                        st.error(f"Ошибка сохранения: {ver_res.text}")
                except Exception as e:
                    st.error(f"Ошибка: {e}")

        # ЭКСПОРТ
        st.subheader("3. Экспорт")
        col1, col2 = st.columns(2)
        with col1:
            st.download_button("📥 Скачать CSV", edited_df.to_csv(index=False).encode('utf-8'), "report.csv", "text/csv")
        
        # XML показываем только если есть данные и это медиа
        current_file = st.session_state.filename or "file"
        is_media = current_file.split('.')[-1].lower() not in ['txt', 'docx', 'pdf']
        
        if is_media and not edited_df.empty and 'risk_level' in edited_df.columns:
            with col2:
                try:
                    xml_data = generate_premiere_xml(edited_df, current_file)
                    st.download_button("🎬 Скачать XML", xml_data, "markers.xml", "text/xml")
                except: pass