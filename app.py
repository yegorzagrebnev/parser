import streamlit as st
from core import (
    fetch_and_store_single,
    simulate_admission,
    export_to_excel,
    lookup_reg_number,
    get_connection,
    ID_LIST
)
import pandas as pd
import os
import sqlite3
from datetime import datetime


st.set_page_config(page_title="Магистерский калькулятор", layout="wide")
st.title("🎓 Магистерский калькулятор: оцени свои шансы на поступление")

st.markdown("""
Это приложение позволяет:
- Загрузить актуальные рейтинги поступающих в магистратуру с сайта ЮУрГУ
- Смоделировать зачисление на бюджет по приоритету и баллам

**Шаги:**
1. Нажмите «🔄 Загрузить свежие данные» (при необходимости)
2. После загрузки — «✅ Смоделировать зачисление»
3. Скачайте Excel-файл или воспользуйтесь поиском абитуриента по его СНИЛС
            
⚠ ВАЖНО: Приложение ориентируется исключительно на списки поступающих на бюджет.
Учёт бакалавров, аспирантов и контрактников появится позже.
            
**Автор:** [Егор](https://t.me/yetanothercreativeusername)
            
**Поблагодарить рублём:** [Тинькофф](https://www.tinkoff.ru/rm/r_omVCvObggH.qSLGCbPrSM/S2bsI15773)
""")

if "data_loaded" not in st.session_state:
    try:
        conn = sqlite3.connect("abit.db")
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)")
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'applicants_%'")
        has_tables = bool(cur.fetchall())
        cur.execute("SELECT value FROM metadata WHERE key = 'last_updated'")
        row = cur.fetchone()
        conn.close()

        st.session_state.data_loaded = has_tables
        st.session_state.last_updated = row[0] if row else None
    except Exception:
        st.session_state.data_loaded = False
        st.session_state.last_updated = None

if "last_excel_path" not in st.session_state:
    st.session_state.last_excel_path = None

def load_cached_data():
    conn = get_connection()
    places = {}
    names = {}
    times = {}

    cur = conn.cursor()

    for direction_id in ID_LIST:
        table = f"applicants_{direction_id}"
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            if cur.fetchone()[0] == 0:
                continue

            cur.execute("SELECT value FROM metadata WHERE key = ?", (f"name_{direction_id}",))
            raw = cur.fetchone()
            names[direction_id] = raw[0] if raw else f"Направление {direction_id}"

            cur.execute("SELECT value FROM metadata WHERE key = ?", (f"time_{direction_id}",))
            raw = cur.fetchone()
            times[direction_id] = raw[0] if raw else "неизвестно"

            cur.execute("SELECT value FROM metadata WHERE key = ?", (f"places_{direction_id}",))
            raw = cur.fetchone()
            places[direction_id] = int(raw[0]) if raw else 10

        except:
            continue

    conn.close()
    return places, names, times

if st.session_state.data_loaded:
    if "places" not in st.session_state:
        places, names, times = load_cached_data()
        st.session_state.places = places
        st.session_state.names = names
        st.session_state.times = times
        st.session_state.failures = []
    st.info(f"✅ Используются локальные данные. Последнее обновление: {st.session_state.last_updated}")
else:
    st.warning("⚠ Данные ещё не загружены. Пожалуйста, нажмите кнопку ниже.")

if st.session_state.data_loaded:
    if st.button("🗑 Очистить локальные данные"):
        try:
            os.remove("abit.db")
            st.session_state.data_loaded = False
            st.session_state.last_updated = None
            st.success("База данных очищена.")
        except Exception as e:
            st.error(f"Не удалось удалить базу данных: {e}")

tab1, tab2 = st.tabs(["📥 Загрузка данных и симуляция зачисления", "🔍 Поиск абитуриента по СНИЛС"])

with tab1:
    st.subheader("📥 Загрузка рейтингов и симуляция зачисления")

    if st.button("🔄 Загрузить свежие данные"):
        with st.spinner("Загружаем данные по направлениям..."):
            progress_text = st.empty()
            progress_bar = st.progress(0)

            total = len(ID_LIST)
            places = {}
            names = {}
            times = {}
            failures = []

            for i, direction_id in enumerate(ID_LIST):
                progress_text.text(f"🔄 Загрузка направления ID {direction_id} ({i + 1}/{total})")
                result = fetch_and_store_single(direction_id)
                if result:
                    p, n, t = result
                    places[direction_id] = p
                    names[direction_id] = n
                    times[direction_id] = t
                else:
                    failures.append(direction_id)
                progress_bar.progress((i + 1) / total)

            st.session_state.places = places
            st.session_state.names = names
            st.session_state.times = times
            st.session_state.failures = failures
            st.session_state.data_loaded = True
            st.session_state.last_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            try:
                conn = sqlite3.connect("abit.db")
                cur = conn.cursor()
                cur.execute("REPLACE INTO metadata (key, value) VALUES (?, ?)", ("last_updated", st.session_state.last_updated))
                for direction_id in ID_LIST:
                    cur.execute("REPLACE INTO metadata (key, value) VALUES (?, ?)", (f"places_{direction_id}", str(places.get(direction_id, 10))))
                conn.commit()
                conn.close()
            except Exception as e:
                st.error(f"Ошибка при сохранении даты обновления: {e}")

        st.success("✅ Данные успешно загружены")
        if failures:
            st.warning(f"⚠ Не удалось загрузить направления: {failures}")

    if st.session_state.data_loaded and st.button("✅ Смоделировать зачисление"):
        with st.spinner("Симулируем зачисление..."):
            admitted = simulate_admission(st.session_state.places)
            excel_path = export_to_excel(admitted, st.session_state.names, st.session_state.times)
            st.session_state.last_excel_path = excel_path
            st.success("🎉 Симуляция завершена. Результаты сохранены.")

            if os.path.exists(excel_path):
                with open(excel_path, "rb") as f:
                    st.download_button(
                        "📥 Скачать Excel-файл с результатами",
                        f,
                        file_name=os.path.basename(excel_path),
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

            for direction_id, entries in admitted.items():
                st.subheader(f"{direction_id} — {st.session_state.names.get(direction_id)}")
                df = pd.DataFrame(entries, columns=["Регистрационный номер", "Баллы", "Приоритет"])
                df.index += 1
                df.index.name = "Место"
                st.dataframe(df, use_container_width=True)

with tab2:
    st.subheader("🔍 Поиск по СНИЛС")

    reg_input = st.text_input("Укажите СНИЛС:")

    if st.button("🔎 Найти"):
        if not st.session_state.get("data_loaded"):
            st.warning("⚠ Сначала загрузите рейтинги на первой вкладке.")
        elif not reg_input.strip():
            st.error("Введите корректный СНИЛС.")
        else:
            with st.spinner("Ищем..."):
                results = lookup_reg_number(reg_input.strip())
                if results:
                    df = pd.DataFrame(results)
                    df = df.rename(columns={
                        "direction_id": "ID направления",
                        "position": "Позиция",
                        "reg_number": "Рег. номер",
                        "total_score": "Баллы (общие)",
                        "individual_achievements": "Баллы (ИД)",
                        "has_originals": "Оригинал",
                        "priority": "Приоритет"
                    })
                    df.index += 1
                    df.index.name = "Найдено"
                    st.success(f"✅ Найдено направлений: {len(df)}")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("Ничего не найдено по данному номеру.")
