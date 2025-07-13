import streamlit as st
import sqlite3
import pandas as pd
import os
from datetime import datetime
from core import (
    fetch_and_store_single,
    simulate_admission,
    simulate_contract,
    export_to_excel,
    lookup_reg_number,
    ID_LIST,
    CONTRACT_ID_LIST
)

DB_PATH = "abit.db"

def load_budget_data():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    places, names, times = {}, {}, {}
    for did in ID_LIST:
        try:
            cur.execute("SELECT value FROM metadata WHERE key = ?", (f"places_{did}",))
            places[did] = int(cur.fetchone()[0])
            cur.execute("SELECT value FROM metadata WHERE key = ?", (f"name_{did}",))
            names[did] = cur.fetchone()[0]
            cur.execute("SELECT value FROM metadata WHERE key = ?", (f"time_{did}",))
            times[did] = cur.fetchone()[0]
        except:
            continue
    conn.close()
    return places, names, times

def load_contract_data():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    places, names, times = {}, {}, {}
    for did in CONTRACT_ID_LIST:
        try:
            cur.execute("SELECT value FROM metadata WHERE key = ?", (f"contract_places_{did}",))
            places[did] = int(cur.fetchone()[0])
            cur.execute("SELECT value FROM metadata WHERE key = ?", (f"contract_name_{did}",))
            names[did] = cur.fetchone()[0]
            cur.execute("SELECT value FROM metadata WHERE key = ?", (f"contract_time_{did}",))
            times[did] = cur.fetchone()[0]
        except:
            continue
    conn.close()
    return places, names, times

if "budget_loaded" not in st.session_state:
    if os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'applicants_%'")
        if cur.fetchall():
            pl, nm, tm = load_budget_data()
            st.session_state.budget_places = pl
            st.session_state.budget_names = nm
            st.session_state.budget_times = tm
            st.session_state.budget_loaded = True
        else:
            st.session_state.budget_loaded = False
        conn.close()
    else:
        st.session_state.budget_loaded = False

if "contract_loaded" not in st.session_state:
    if os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'contract_applicants_%'")
        if cur.fetchall():
            pl, nm, tm = load_contract_data()
            st.session_state.contract_places = pl
            st.session_state.contract_names = nm
            st.session_state.contract_times = tm
            st.session_state.contract_loaded = True
        else:
            st.session_state.contract_loaded = False
        conn.close()
    else:
        st.session_state.contract_loaded = False

st.set_page_config(page_title="Магистерский калькулятор", layout="wide")
st.title("🎓 Магистерский калькулятор")

tabs = st.tabs(["📥 Бюджет", "📥 Контракт", "🔍 Поиск абитуриента по СНИЛС"])

with tabs[0]:
    st.subheader("Загрузка и симуляция поступления на бюджет")
    if st.session_state.budget_loaded:
        st.info("Данные поступающих на бюджет уже загружены")
    if st.button("🔄 Загрузить данные (бюджет)"):
        with st.spinner("Загружаем списки поступающих на бюджет..."):
            prog = st.progress(0)
            places, names, times, fails = {}, {}, {}, []
            for i, did in enumerate(ID_LIST):
                res = fetch_and_store_single(did, contract=False)
                if res:
                    p, n, t = res
                    places[did], names[did], times[did] = p, n, t
                else:
                    fails.append(did)
                prog.progress((i+1)/len(ID_LIST))
            st.session_state.budget_places = places
            st.session_state.budget_names = names
            st.session_state.budget_times = times
            st.session_state.budget_loaded = True
        if fails:
            st.warning(f"Не удалось загрузить списки: {fails}")
    if st.button("🗑 Очистить данные (бюджет)"):
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        st.session_state.budget_loaded = False
        st.success("Списки поступающих на бюджет очищены")
    if st.session_state.budget_loaded and st.button("✅ Симулировать (бюджет)"):
        adm = simulate_admission(st.session_state.budget_places)
        path = export_to_excel(adm, st.session_state.budget_names, st.session_state.budget_times)
        st.success("Симуляция поступления на бюджет завершена")
        with open(path, "rb") as f:
            st.download_button("📥 Скачать Excel (бюджет)", f, file_name=os.path.basename(path))
        for did, lst in adm.items():
            st.subheader(f"{did} — {st.session_state.budget_names[did]}")
            df = pd.DataFrame(lst, columns=["Регистрационный номер (СНИЛС)", "Баллы", "Приоритет"])
            df.index += 1; df.index.name = "Место"
            st.dataframe(df, use_container_width=True)

with tabs[1]:
    st.subheader("Загрузка и симуляция поступления на контракт")
    if st.session_state.contract_loaded:
        st.info("Данные поступающих на контракт уже загружены")
    if st.button("🔄 Загрузить данные (контракт)"):
        if not st.session_state.budget_loaded:
            st.warning("Сначала загрузите списки поступающих на бюджет")
        else:
            with st.spinner("Загружаем списки поступающих на контракт..."):
                prog = st.progress(0)
                c_places, c_names, c_times, fails = {}, {}, {}, []
                for i, did in enumerate(CONTRACT_ID_LIST):
                    res = fetch_and_store_single(did, contract=True)
                    if res:
                        p, n, t = res
                        c_places[did], c_names[did], c_times[did] = p, n, t
                    else:
                        fails.append(did)
                    prog.progress((i+1)/len(CONTRACT_ID_LIST))
                st.session_state.contract_places = c_places
                st.session_state.contract_names = c_names
                st.session_state.contract_times = c_times
                st.session_state.contract_loaded = True
            if fails:
                st.warning(f"Не удалось загрузить списки: {fails}")
    if st.button("🗑 Очистить данные (контракт)"):
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        st.session_state.contract_loaded = False
        st.success("Данные поступающих на контракт очищены")
    if st.session_state.contract_loaded and st.session_state.budget_loaded and st.button("✅ Симулировать (контракт)"):
        budget_adm = simulate_admission(st.session_state.budget_places)
        adm_c = simulate_contract(budget_adm, st.session_state.contract_places)
        path = export_to_excel(adm_c, st.session_state.contract_names, st.session_state.contract_times)
        st.success("Симуляция поступления на контракт завершена")
        with open(path, "rb") as f:
            st.download_button("📥 Скачать Excel (контракт)", f, file_name=os.path.basename(path))
        for did, lst in adm_c.items():
            st.subheader(f"{did} — {st.session_state.contract_names[did]}")
            df = pd.DataFrame(lst, columns=["Регистрационный номер (СНИЛС)", "Баллы", "Приоритет"])
            df.index += 1; df.index.name = "Место"
            st.dataframe(df, use_container_width=True)

with tabs[2]:
    st.subheader("Поиск абитуриента по его СНИЛС")
    reg = st.text_input("Укажите СНИЛС:")
    if st.button("🔎 Найти"):
        if not reg.strip():
            st.error("Укажите корректный СНИЛС.")
        else:
            res = lookup_reg_number(reg.strip())
            if res:
                df = pd.DataFrame(res)
                df.index += 1; df.index.name = "№"
                st.dataframe(df, use_container_width=True)
            else:
                st.info("Ничего не найдено.")
