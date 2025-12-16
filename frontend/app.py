import streamlit as st
import pandas as pd
import requests
import time
import os
import json

# --- КОНФИГУРАЦИЯ ---
st.set_page_config(page_title="AI-Lawyer Enterprise", page_icon="⚖️", layout="wide")
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

# --- СТИЛИ CSS ---
st.markdown("""
    <style>
    .risk-high { color: #ff4b4b; font-weight: bold; }
    .risk-medium { color: #ffa726; font-weight: bold; }
    .risk-safe { color: #00c853; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- ИНИЦИАЛИЗАЦИЯ ПАМЯТИ ---
if 'analysis_result' not in st.session_state:
    st.session_state.analysis_result = None
if 'asset_id' not in st.session_state:
    st.session_state.asset_id = None

# --- ИНТЕРФЕЙС ---
st.title("⚖️ AI-Lawyer Enterprise v6.0 (Compliance Dashboard)")

with st.sidebar:
    st.header("Настройки")
    api_key = st.text_input("Gemini API Key", type="password")
    st.info("Режим: Deep Compliance (NTV Policies)")

# 1. ЗАГРУЗКА
uploaded_file = st.file_uploader("Загрузить материал", type=['mp4', 'mov', 'mp3', 'wav', 'docx', 'pdf'])

if uploaded_file and api_key:
    if st.button("🚀 Запустить проверку", type="primary"):
        with st.spinner("Анализ контента, проверка политик и поиск прецедентов..."):
            try:
                # Очистка
                st.session_state.analysis_result = None
                
                # Подготовка
                ext = uploaded_file.name.split('.')[-1]
                safe_filename = f"input_file.{ext}"
                files = {"file": (safe_filename, uploaded_file, uploaded_file.type)}
                data = {"original_filename": uploaded_file.name}
                headers = {"X-API-Key": api_key}
                
                # Отправка
                res = requests.post(f"{BACKEND_URL}/analyze", files=files, data=data, headers=headers, timeout=600)
                
                if res.status_code == 200:
                    task_id = res.json()['task_id']
                    status_text = st.empty()
                    prog_bar = st.progress(0)
                    
                    while True:
                        time.sleep(3)
                        try:
                            status_res = requests.get(f"{BACKEND_URL}/status/{task_id}")
                            status_data = status_res.json()
                            state = status_data.get("state")
                            
                            if state == 'SUCCESS':
                                prog_bar.progress(100)
                                st.session_state.analysis_result = status_data.get("result", {})
                                st.session_state.asset_id = st.session_state.analysis_result.get('_asset_id')
                                st.rerun()
                                break
                            elif state == 'FAILURE':
                                st.error(f"Ошибка: {status_data.get('error')}")
                                st.stop()
                            elif state == 'PROGRESS':
                                msg = status_data.get("status", "Обработка...")
                                status_text.text(f"Статус: {msg}")
                        except Exception as e:
                            time.sleep(3)
                else:
                    st.error(f"Ошибка сервера: {res.text}")
            except Exception as e:
                st.error(f"Ошибка соединения: {e}")

# 2. ДАШБОРД РЕЗУЛЬТАТОВ
if st.session_state.analysis_result:
    res = st.session_state.analysis_result
    
    # Обработка ошибки, если AI вернул error внутри JSON
    if isinstance(res, dict) and "error" in res:
        st.error(f"AI Error: {res['error']}")
    else:
        # --- БЛОК 1: СВОДКА (HEADER) ---
        overall = res.get('overall', {})
        risk = overall.get('risk_level', 'UNKNOWN')
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Риск", risk)
        with col2:
            st.metric("Возрастной рейтинг", overall.get('age_rating', 'N/A'))
        with col3:
            conf = overall.get('confidence', 0)
            if conf:
                st.metric("Уверенность AI", f"{conf * 100:.1f}%")
            else:
                st.metric("Уверенность AI", "N/A")
        with col4:
            st.metric("Нарушений", len(res.get('labels', [])))

        st.info(f"📝 **Резюме:** {overall.get('summary', 'Нет описания')}")

        # --- ТАБЫ С ДЕТАЛЯМИ ---
        tab1, tab2, tab3, tab4 = st.tabs(["🚨 Нарушения", "📜 Политики НТВ", "✂️ Рекомендации", "🎓 Обучение"])

        # ТАБ 1: Нарушения (Labels + Evidence)
        with tab1:
            labels = res.get('labels', [])
            evidence = {e['id']: e for e in res.get('evidence', [])}
            
            if not labels:
                st.success("Нарушений не обнаружено.")
            else:
                for lbl in labels:
                    # Безопасное получение полей
                    severity = lbl.get('severity', 0)
                    code = lbl.get('code', 'UNKNOWN_CODE')
                    confidence = lbl.get('confidence', 0)
                    rationale = lbl.get('rationale', 'Нет объяснения')
                    
                    sev_icon = "🔴" if severity == 3 else "🟠" if severity == 2 else "🟡"
                    
                    with st.expander(f"{sev_icon} {code} (Уверенность: {confidence:.2f})"):
                        st.write(f"**Причина:** {rationale}")
                        st.markdown("**Доказательства:**")
                        
                        ev_ids = lbl.get('evidence_ids', [])
                        if not ev_ids:
                            st.write("_Нет привязанных доказательств_")
                        
                        for ref_id in ev_ids:
                            ev_item = evidence.get(ref_id)
                            if ev_item:
                                # Конвертация времени
                                start_s = ev_item.get('start_ms', 0) / 1000
                                end_s = ev_item.get('end_ms', 0) / 1000
                                start_fmt = time.strftime('%H:%M:%S', time.gmtime(start_s))
                                end_fmt = time.strftime('%H:%M:%S', time.gmtime(end_s))
                                
                                qt = ev_item.get('text_quote', 'Нет текста')
                                note = ev_item.get('notes', '')
                                
                                st.code(f"[{start_fmt} - {end_fmt}] {qt} ({note})")

        # ТАБ 2: Политики (Policy Hits)
        with tab2:
            policies = res.get('policy_hits', [])
            if not policies:
                st.info("Специфические политики канала не нарушены.")
            else:
                for p in policies:
                    req_code = p.get('req_code', 'UNKNOWN')
                    why = p.get('why', '')
                    prio = p.get('priority', 'P2')
                    st.error(f"**Нарушено требование:** {req_code}")
                    st.write(f"Причина: {why}")
                    st.caption(f"Приоритет: {prio}")
                    st.divider()

        # ТАБ 3: Рекомендации (Actions)
        with tab3:
            recs = res.get('recommendations', [])
            if not recs:
                st.success("Действий не требуется.")
            else:
                rec_data = []
                for r in recs:
                    rec_data.append({
                        "Действие": r.get('action'),
                        "Приоритет": r.get('priority'),
                        "Эффект": r.get('expected_effect'),
                        "Таймкоды": r.get('target_evidence_ids')
                    })
                st.dataframe(pd.DataFrame(rec_data), use_container_width=True)

        # ТАБ 4: Обучение (Feedback Loop)
        with tab4:
            st.write("### 🧑‍🏫 Панель учителя")
            st.write("Если AI ошибся в **общем вердикте**, исправьте это здесь. Это попадет в RAG.")
            
            col_teach1, col_teach2 = st.columns(2)
            with col_teach1:
                # Безопасный индекс для selectbox
                risk_options = ["SAFE", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
                try:
                    current_index = risk_options.index(risk)
                except ValueError:
                    current_index = 0
                    
                new_risk = st.selectbox("Скорректировать уровень риска:", risk_options, index=current_index)
            
            teacher_note = st.text_area(
                "Комментарий (Chain of Thought):",
                placeholder="Пример: Это ложное срабатывание, так как сцена является исторической реконструкцией..."
            )
            
            if st.button("Сохранить в Базу Знаний"):
                if st.session_state.asset_id:
                    st.info("Функция сохранения сложной структуры будет доступна в v6.1 (нужен апдейт Backend)")
                else:
                    st.error("Нет ID ассета.")

# Футер
st.markdown("---")
st.caption("AI-Lawyer Enterprise v6.0 | Powered by Gemini 2.5 Flash & Supabase Vector")