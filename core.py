import requests
import sqlite3
from bs4 import BeautifulSoup
import re
import time
import pandas as pd
from requests.exceptions import RequestException
import os
from datetime import datetime

DB_PATH = "abit.db"
BASE_URL = "https://abit.susu.ru"
HEADERS = {"User-Agent": "Mozilla/5.0"}
ID_LIST = [2, 7, 8, 9, 11, 12, 13, 45, 48, 59, 60, 61, 62, 64, 65, 66, 67, 68, 69, 70,
           82, 83, 84, 85, 86, 87, 88, 93, 94, 97, 101, 104, 105, 106, 107, 109, 111,
           112, 114, 116, 118, 136, 147, 149, 172, 179, 180, 183, 184, 189, 212, 213,
           218, 226, 227, 241, 242, 243, 244, 246, 247, 248, 256, 257, 259, 324]
CONTRACT_ID_LIST = [2, 6, 7, 8, 9, 10, 11, 12, 13, 44, 45, 47, 48, 58, 59, 60, 61, 62,
                    63, 64, 65, 66, 67, 68, 69, 70, 71, 82, 83, 84, 85, 86, 87, 88,
                    93, 94, 97, 101, 105, 109, 111, 112, 125, 126, 127, 132, 133, 134,
                    135, 136, 139, 144, 145, 147, 149, 150, 152, 153, 160, 164, 167,
                    172, 179, 180, 183, 184, 189, 190, 218, 225, 226, 227, 228, 229,
                    230, 245, 246, 247, 248, 249, 252, 256, 257, 258, 259, 260, 284,
                    324, 325, 326]

def safe_get(url, headers, retries=5, delay=1):
    for _ in range(retries):
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            return resp
        except RequestException:
            time.sleep(delay)
    raise RuntimeError(f"Не удалось получить {url}")

def get_connection():
    return sqlite3.connect(DB_PATH)

def ensure_table_exists(conn, table_name):
    cur = conn.cursor()
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            position INTEGER,
            reg_number TEXT,
            place_type TEXT,
            total_score INTEGER,
            individual_achievements INTEGER,
            has_originals BOOLEAN,
            priority INTEGER,
            exam_result TEXT
        )
    """)
    conn.commit()
    cur.close()

def convert_page_to_soup(url, headers):
    resp = safe_get(url, headers)
    return BeautifulSoup(resp.text, "html.parser")

def extract_budget_places(soup):
    for b in soup.find_all("b"):
        text = b.get_text(strip=True)
        if "Всего мест:" in text:
            m = re.search(r"Всего мест:\s*(\d+)", text)
            if m:
                return int(m.group(1))
    return 0

def extract_direction_metadata(soup):
    name = "Без названия"
    update_time = "неизвестно"
    info = soup.find("div", class_="rating_info")
    if info:
        for p in info.find_all("p"):
            if "Направление/Специальность" in p.text:
                b = p.find("b")
                if b:
                    name = b.get_text(strip=True)
    time_block = soup.find("div", class_="rating_time")
    if time_block:
        b = time_block.find("b")
        if b:
            update_time = b.get_text(strip=True)
    return name, update_time

def extract_table_body_from_soup(soup):
    tbl = soup.find("table")
    if not tbl or not tbl.tbody:
        raise ValueError("Не найдена таблица или tbody")
    return tbl.tbody

def parse_td_content(text):
    text = text.replace("\xad", "")
    m = re.match(r"(.+?):\s*(.+)", text)
    return (m.group(1).strip(), m.group(2).strip()) if m else (text.strip(), None)

def extract_data_from_table_body(table_body):
    rows = []
    for tr in table_body.find_all("tr"):
        row = {}
        for td in tr.find_all("td"):
            k, v = parse_td_content(td.text)
            if v is not None:
                row[k] = v
        if row:
            rows.append(row)
    return rows

def transform_row(row):
    return (
        int(row.get("Позиция в рейтинге", 0)),
        row.get("Регистрационный номер", ""),
        row.get("Тип места", ""),
        int(row.get("Сумма оценок", 0)),
        int(row.get("Индивидуальные достижения", 0)),
        row.get("Предоставлены оригиналы документов", "").lower() == "да",
        int(row.get("Приоритет", 0)),
        row.get("Вступительные испытания", "")
    )

def fetch_and_store_single(direction_id, contract=False):
    conn = get_connection()
    table = ("contract_applicants_" if contract else "applicants_") + str(direction_id)
    ensure_table_exists(conn, table)
    url = f"{BASE_URL}/rating/?type={'blue' if contract else 'yellow'}&id={direction_id}"
    try:
        soup = convert_page_to_soup(url, HEADERS)
        places = extract_budget_places(soup)
        name, update_time = extract_direction_metadata(soup)
        tbody = extract_table_body_from_soup(soup)
        raw = extract_data_from_table_body(tbody)
        rows = [transform_row(r) for r in raw]
        cur = conn.cursor()
        cur.execute(f"DELETE FROM {table}")
        cur.executemany(
            f"INSERT INTO {table} (position, reg_number, place_type, total_score, individual_achievements, has_originals, priority, exam_result) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows
        )
        cur.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)")
        meta = [
            (f"{'contract_' if contract else ''}name_{direction_id}", name),
            (f"{'contract_' if contract else ''}time_{direction_id}", update_time),
            (f"{'contract_' if contract else ''}places_{direction_id}", str(places))
        ]
        for k, v in meta:
            cur.execute("REPLACE INTO metadata (key, value) VALUES (?, ?)", (k, v))
        conn.commit()
        cur.close()
        conn.close()
        return places, name, update_time
    except:
        conn.close()
        return None

def simulate_admission(budget_places):
    conn = get_connection()
    cur = conn.cursor()
    applicants = []
    for did in ID_LIST:
        tbl = f"applicants_{did}"
        cur.execute(f"SELECT reg_number, total_score, priority FROM {tbl}")
        applicants += [(reg, score, pr, did) for reg, score, pr in cur.fetchall()]
    applicants.sort(key=lambda x: (x[2], -x[1]))
    admitted = {}
    seen = set()
    for reg, score, pr, did in applicants:
        if reg in seen:
            continue
        admitted.setdefault(did, [])
        if len(admitted[did]) < budget_places.get(did, 0):
            admitted[did].append((reg, score, pr))
            seen.add(reg)
    cur.close()
    conn.close()
    return admitted

def simulate_contract(budget_admitted, contract_places):
    banned = {reg for lst in budget_admitted.values() for reg, *_ in lst}
    conn = get_connection()
    cur = conn.cursor()
    admitted = {}
    for did in CONTRACT_ID_LIST:
        total = contract_places.get(did, 0)
        cur.execute(f"SELECT reg_number, total_score, priority, place_type FROM contract_applicants_{did}")
        rows = [(reg, score, pr, ptype) for reg, score, pr, ptype in cur.fetchall() if reg not in banned]
        signed = [(reg, score, pr) for reg, score, pr, ptype in rows if 'заключен договор' in ptype.lower()]
        applied = [(reg, score, pr) for reg, score, pr, ptype in rows if 'подано заявление' in ptype.lower()]
        admitted[did] = []
        for item in signed:
            admitted[did].append(item)
        free = max(total - len(signed), 0)
        if free > 0:
            applied.sort(key=lambda x: (x[2], -x[1]))
            for reg, score, pr in applied:
                if len(admitted[did]) < total:
                    admitted[did].append((reg, score, pr))
                else:
                    break
    cur.close()
    conn.close()
    return admitted

def export_to_excel(admitted, direction_names, update_times):
    os.makedirs("tmp", exist_ok=True)
    filename = f"admission_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    filepath = os.path.join("tmp", filename)
    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        for did, entries in admitted.items():
            title = direction_names.get(did, "Без названия")
            utime = update_times.get(did, "неизвестно")
            safe = re.sub(r'[\\/*?:[\]]', '_', title)[:30]
            sheet = f"{did}-{safe}"[:31]
            df = pd.DataFrame(entries, columns=["Регистрационный номер", "Баллы", "Приоритет"])
            df.index += 1
            df.index.name = "Место"
            meta = pd.DataFrame([[f"Название направления: {title}"],
                                 [f"Время обновления: {utime}"], [""]])
            combined = pd.concat([meta, df.reset_index()], ignore_index=True)
            combined.to_excel(writer, sheet_name=sheet, index=False)
    return filepath

def lookup_reg_number(reg_number):
    conn = get_connection()
    cur = conn.cursor()
    results = []
    for did in ID_LIST:
        tbl = f"applicants_{did}"
        cur.execute(
            "SELECT position, reg_number, total_score, individual_achievements, has_originals, priority "
            f"FROM {tbl} WHERE reg_number = ?", (reg_number,))
        rows = cur.fetchall()
        if rows:
            cur.execute("SELECT value FROM metadata WHERE key = ?", (f"name_{did}",))
            spec_row = cur.fetchone()
            spec = spec_row[0] if spec_row else ""
            for pos, reg, tot, ind, orig, pr in rows:
                results.append({
                    "ID": did,
                    "Специальность": spec,
                    "Форма": "бюджет",
                    "Позиция": pos,
                    "Регномер": reg,
                    "Баллы": tot,
                    "ИД": ind,
                    "Оригинал": bool(orig),
                    "Приоритет": pr
                })

    for did in CONTRACT_ID_LIST:
        tbl = f"contract_applicants_{did}"
        cur.execute(
            "SELECT position, reg_number, total_score, individual_achievements, has_originals, priority "
            f"FROM {tbl} WHERE reg_number = ?", (reg_number,))
        rows = cur.fetchall()
        if rows:
            cur.execute("SELECT value FROM metadata WHERE key = ?", (f"contract_name_{did}",))
            spec_row = cur.fetchone()
            spec = spec_row[0] if spec_row else ""
            for pos, reg, tot, ind, orig, pr in rows:
                results.append({
                    "ID": did,
                    "Специальность": spec,
                    "Форма": "контракт",
                    "Позиция": pos,
                    "Регномер": reg,
                    "Баллы": tot,
                    "ИД": ind,
                    "Оригинал": bool(orig),
                    "Приоритет": pr
                })
    conn.close()
    return results

__all__ = [
    "fetch_and_store_single", "simulate_admission", "simulate_contract",
    "export_to_excel", "lookup_reg_number",
    "ID_LIST", "CONTRACT_ID_LIST"
]
