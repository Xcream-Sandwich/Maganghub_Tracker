import sqlite3
import os
import json

DB_PATH = os.environ.get("MAGANGHUB_DB_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "maganghub.db"))

def get_db_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA cache_size = -64000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Metadata sync
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sync_meta (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Provinces reference
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS provinces (
        id TEXT PRIMARY KEY,
        code TEXT,
        name TEXT,
        latitude REAL,
        longitude REAL
    )
    """)

    # Companies / Organizers (deduplicated)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS companies (
        id TEXT PRIMARY KEY,
        name TEXT,
        type TEXT,
        email TEXT,
        phone TEXT,
        address TEXT,
        logo_url TEXT,
        city_id TEXT,
        city_name TEXT,
        province_id TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_companies_name ON companies(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_companies_type ON companies(type)")

    # Vacancies
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vacancies (
        id TEXT PRIMARY KEY,
        position_name TEXT,
        title TEXT,
        task_description TEXT,
        quantity_needed INTEGER,
        approved_quantity INTEGER,
        total_applications INTEGER,
        competitive_score REAL,
        opportunity_score REAL,
        education_levels TEXT,  -- JSON array
        study_programs TEXT,    -- JSON array
        study_program_names TEXT, -- Space-separated lowercase string for easy LIKE search
        organizer_id TEXT,
        organizer_name TEXT,
        organizer_type TEXT,
        city_id TEXT,
        city_name TEXT,
        province_id TEXT,
        province_name TEXT,
        district_name TEXT,     -- Extracted kecamatan
        address TEXT,
        latitude REAL,
        longitude REAL,
        working_days_per_week INTEGER,
        days_off TEXT,          -- JSON array
        interview_types TEXT,   -- JSON array
        published_at TEXT,
        created_at TEXT,
        updated_at TEXT,
        url TEXT,
        scraped_at TEXT,
        FOREIGN KEY (organizer_id) REFERENCES companies(id)
    )
    """)

    # Performance indices
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vacancies_pub ON vacancies(published_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vacancies_opp ON vacancies(opportunity_score DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vacancies_qty ON vacancies(approved_quantity DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vacancies_prov ON vacancies(province_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vacancies_city ON vacancies(city_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vacancies_district ON vacancies(district_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vacancies_org_type ON vacancies(organizer_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vacancies_org_id ON vacancies(organizer_id)")

    # Full text search table
    cursor.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS vacancies_fts USING fts5(
        id UNINDEXED,
        position_name,
        task_description,
        organizer_name,
        study_program_names,
        city_name,
        province_name,
        tokenize='unicode61 remove_diacritics 2'
    )
    """)

    # UMK Reference table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS umk_reference (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        area_name TEXT UNIQUE,
        area_type TEXT, -- 'city' or 'province'
        umk_value INTEGER,
        year INTEGER DEFAULT 2024,
        source TEXT DEFAULT 'Kepmenaker / SK Gubernur'
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_umk_area ON umk_reference(area_name)")

    # Seed UMK data if empty
    cursor.execute("SELECT COUNT(*) FROM umk_reference")
    if cursor.fetchone()[0] == 0:
        from backend.umk_data import UMK_DATA, UMP_PROVINCE
        rows = []
        for city, val in UMK_DATA.items():
            rows.append((city, 'city', val, 2024, 'Surat Keputusan Gubernur / Kemnaker'))
        for prov, val in UMP_PROVINCE.items():
            rows.append((prov, 'province', val, 2024, 'UMP Provinsi Kemnaker'))
        cursor.executemany(
            "INSERT OR IGNORE INTO umk_reference (area_name, area_type, umk_value, year, source) VALUES (?, ?, ?, ?, ?)",
            rows
        )

    conn.commit()
    conn.close()
    print("Database initialized successfully at", DB_PATH)

if __name__ == "__main__":
    init_db()
