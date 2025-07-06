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
HEADERS = {
    "User-Agent": "Mozilla/5.0"
}
ID_LIST = [2, 7, 8, 9, 11, 12, 13, 45, 48, 60, 66, 67, 70, 82, 83, 85, 86, 87, 88, 93, 94, 97, 101, 104, 105, 106, 109, 111, 112, 116, 118, 136, 147, 149, 172, 179, 184, 189, 212, 213, 218, 226, 227, 241, 242, 243, 244, 246, 247, 248, 256, 257, 259]


def safe_get(url, headers, retries=9999, delay=1):
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response
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
    response = safe_get(url, headers)
    return BeautifulSoup(response.text, "html.parser")


def extract_budget_places(soup):
    for b in soup.find_all("b"):
        text = b.get_text(strip=True)
        if "Всего мест:" in text:
            match = re.search(r"Всего мест:\s*(\d+)", text)
            if match:
                return int(match.group(1))
    return 10


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
    table = soup.find("table")
    if not table or not table.tbody:
        raise ValueError("Не найдена таблица или tbody")
    return table.tbody


def parse_td_content(text):
    text = text.replace("\xad", "")
    match = re.match(r"(.+?):\s*(.+)", text)
    return (match.group(1).strip(), match.group(2).strip()) if match else (text.strip(), None)


def extract_data_from_table_body(table_body):
    result = []
    for tr in table_body.find_all("tr"):
        row = {}
        for td in tr.find_all("td"):
            key, value = parse_td_content(td.text)
            if value is not None:
                row[key] = value
        if row:
            result.append(row)
    return result


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


def fetch_and_store():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()

    failed_ids = []
    budget_places = {}
    direction_names = {}
    update_times = {}

    for direction_id in ID_LIST:
        table_name = f"applicants_{direction_id}"
        ensure_table_exists(conn, table_name)

        url = f"{BASE_URL}/rating/?type=yellow&id={direction_id}"
        try:
            soup = convert_page_to_soup(url, HEADERS)
            places = extract_budget_places(soup)
            name, update_time = extract_direction_metadata(soup)

            budget_places[direction_id] = places
            direction_names[direction_id] = name
            update_times[direction_id] = update_time

            tbody = extract_table_body_from_soup(soup)
            raw_rows = extract_data_from_table_body(tbody)
            rows = [transform_row(row) for row in raw_rows]

            cur.execute(f"DELETE FROM {table_name}")
            cur.executemany(f"""
                INSERT INTO {table_name} (
                    position, reg_number, place_type, total_score,
                    individual_achievements, has_originals, priority, exam_result
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", rows)

            cur.execute("REPLACE INTO metadata (key, value) VALUES (?, ?)", (f"name_{direction_id}", name))
            cur.execute("REPLACE INTO metadata (key, value) VALUES (?, ?)", (f"time_{direction_id}", update_time))
            cur.execute("REPLACE INTO metadata (key, value) VALUES (?, ?)", (f"places_{direction_id}", str(places)))

            conn.commit()
        except Exception as e:
            failed_ids.append(direction_id)

        time.sleep(1)

    cur.close()
    conn.close()
    return budget_places, direction_names, update_times, failed_ids


def simulate_admission(budget_places):
    conn = get_connection()
    cur = conn.cursor()

    applicants = []
    for direction_id in ID_LIST:
        table_name = f"applicants_{direction_id}"
        cur.execute(f"""
            SELECT reg_number, total_score, priority, {direction_id} as direction
            FROM {table_name}
        """)
        applicants.extend(cur.fetchall())

    applicants.sort(key=lambda x: (x[2], -x[1]))

    admitted = {}
    already_admitted = set()

    for reg_number, score, priority, direction in applicants:
        if reg_number in already_admitted:
            continue
        admitted.setdefault(direction, [])
        if len(admitted[direction]) < budget_places.get(direction, 10):
            admitted[direction].append((reg_number, score, priority))
            already_admitted.add(reg_number)

    cur.close()
    conn.close()
    return admitted


def lookup_reg_number(reg_number):
    conn = get_connection()
    results = []

    for direction_id in ID_LIST:
        table = f"applicants_{direction_id}"
        cur = conn.execute(f"SELECT * FROM {table} WHERE reg_number = ?", (reg_number,))
        rows = cur.fetchall()
        for row in rows:
            results.append({
                "direction_id": direction_id,
                "position": row[0],
                "reg_number": row[1],
                "total_score": row[3],
                "individual_achievements": row[4],
                "has_originals": bool(row[5]),
                "priority": row[6],
            })
    conn.close()
    return results


def fetch_and_store_single(direction_id):
    conn = get_connection()
    table_name = f"applicants_{direction_id}"
    ensure_table_exists(conn, table_name)

    url = f"{BASE_URL}/rating/?type=yellow&id={direction_id}"
    try:
        soup = convert_page_to_soup(url, HEADERS)
        places = extract_budget_places(soup)
        name, update_time = extract_direction_metadata(soup)

        tbody = extract_table_body_from_soup(soup)
        raw_rows = extract_data_from_table_body(tbody)
        rows = [transform_row(row) for row in raw_rows]

        cur = conn.cursor()
        cur.execute(f"DELETE FROM {table_name}")
        cur.executemany(f"""
            INSERT INTO {table_name} (
                position, reg_number, place_type, total_score,
                individual_achievements, has_originals, priority, exam_result
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", rows)

        cur.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)")
        cur.execute("REPLACE INTO metadata (key, value) VALUES (?, ?)", (f"name_{direction_id}", name))
        cur.execute("REPLACE INTO metadata (key, value) VALUES (?, ?)", (f"time_{direction_id}", update_time))
        cur.execute("REPLACE INTO metadata (key, value) VALUES (?, ?)", (f"places_{direction_id}", str(places)))

        conn.commit()
        cur.close()
        conn.close()

        return places, name, update_time

    except Exception:
        conn.close()
        return None


def export_to_excel(admitted, direction_names, update_times):
    os.makedirs("tmp", exist_ok=True)
    filename = f"admission_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    filepath = os.path.join("tmp", filename)

    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        for direction_id, entries in admitted.items():
            full_title = direction_names.get(direction_id, "Без названия")
            update_time = update_times.get(direction_id, "неизвестно")
            safe_title = re.sub(r'[\\/*?:[\]]', '_', full_title)[:30]
            sheet_name = f"{direction_id} - {safe_title}" if full_title else f"id{direction_id}"

            df = pd.DataFrame(entries, columns=["Регистрационный номер", "Баллы", "Приоритет"])
            df.index += 1
            df.index.name = "Место"

            meta = pd.DataFrame([
                [f"Название направления: {full_title}"],
                [f"Время обновления: {update_time}"],
                [""]
            ])
            data = df.reset_index()
            combined = pd.concat([meta, data], ignore_index=True)

            combined.to_excel(writer, sheet_name=sheet_name[:31], index=False)

    return filepath


__all__ = [
    "fetch_and_store",
    "simulate_admission",
    "export_to_excel",
    "get_connection",
    "ID_LIST"
]
