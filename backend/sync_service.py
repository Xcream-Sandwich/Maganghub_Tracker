import urllib.request
import json
import re
import ssl
import logging
from datetime import datetime
from backend.database import get_db_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

_sync_lock = False

INDEX_URL = "https://maganghab.my.id/data/batch-2/lowongan-index.json"
CHUNK_BASE_URL = "https://maganghab.my.id/data/batch-2/"
PROVINCES_URL = "https://api.kemnaker.go.id/maganghub/onboarding/v2/provinces"

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

def fetch_json_url(url, timeout=35):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    })
    with urllib.request.urlopen(req, context=ssl_ctx, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def sync_provinces(conn):
    logger.info("Syncing provinces from Kemnaker API...")
    try:
        data = fetch_json_url(PROVINCES_URL, timeout=15)
        prov_list = data.get("data", [])
        cursor = conn.cursor()
        for p in prov_list:
            cursor.execute("""
            INSERT INTO provinces (id, code, name, latitude, longitude)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                code=excluded.code,
                name=excluded.name,
                latitude=excluded.latitude,
                longitude=excluded.longitude
            """, (p.get("id"), p.get("code"), p.get("name"), p.get("latitude"), p.get("longitude")))
        conn.commit()
        logger.info(f"Provinces synced: {len(prov_list)} records.")
    except Exception as e:
        logger.warning(f"Warning: Failed to sync provinces directly: {e}. Checking local cache...")

def get_province_lookup(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM provinces")
    return {row["id"]: row["name"] for row in cursor.fetchall()}

# Regex to extract kecamatan
RE_KEC = re.compile(
    r'(?:kec(?:amatan)?\.?\s+)([a-zA-Z\s\.\-]+?)(?:,|\.|kel|kab|kota|\d{5}|$)',
    re.IGNORECASE
)

def extract_district(address):
    if not address:
        return None
    match = RE_KEC.search(address)
    if match:
        name = match.group(1).strip()
        name = re.sub(r'^(?:desa|kelurahan)\s+', '', name, flags=re.IGNORECASE).strip()
        # Clean trailing noise
        name = re.sub(r'\s+(?:rt|rw|no|jl|kel).*$', '', name, flags=re.IGNORECASE).strip()
        if len(name) >= 3 and len(name) <= 35:
            return name.title()
    return None

def sync_all(force=False, max_chunks=None):
    global _sync_lock
    if _sync_lock:
        logger.info("Sinkronisasi sudah sedang berjalan, lewati trigger baru.")
        return {"status": "in_progress", "message": "Sinkronisasi sedang berjalan."}
    _sync_lock = True
    try:
        return _do_sync_all(force=force, max_chunks=max_chunks)
    finally:
        _sync_lock = False

def _do_sync_all(force=False, max_chunks=None):
    conn = get_db_connection()
    cursor = conn.cursor()

    sync_provinces(conn)
    prov_map = get_province_lookup(conn)

    logger.info("Checking remote index for update...")
    try:
        index_data = fetch_json_url(INDEX_URL)
    except Exception as e:
        logger.error(f"Failed to fetch index: {e}")
        conn.close()
        return {"status": "error", "message": f"Failed to fetch index: {e}"}

    remote_gen = index_data.get("generated_at")
    total_remote = index_data.get("total", 0)
    chunks = index_data.get("chunks", [])

    cursor.execute("SELECT value FROM sync_meta WHERE key='generated_at'")
    saved_gen_row = cursor.fetchone()
    saved_gen = saved_gen_row["value"] if saved_gen_row else None

    if not force and saved_gen == remote_gen:
        logger.info("Local data is already up-to-date with remote generated_at.")
        conn.close()
        return {
            "status": "up-to-date",
            "generated_at": remote_gen,
            "total": total_remote,
            "message": "Data sudah paling baru."
        }

    logger.info(f"Starting sync. Remote generated_at: {remote_gen}, Total items: {total_remote}, Chunks: {len(chunks)}")
    
    if max_chunks:
        chunks = chunks[:max_chunks]
        logger.info(f"Limiting to first {max_chunks} chunks for rapid initial setup.")

    total_vacancies_upserted = 0
    total_companies_upserted = 0

    for idx, ch_info in enumerate(chunks):
        ch_file = ch_info["file"] if isinstance(ch_info, dict) else ch_info
        chunk_url = f"{CHUNK_BASE_URL}{ch_file}"
        logger.info(f"Processing chunk [{idx+1}/{len(chunks)}]: {ch_file}")
        try:
            items = fetch_json_url(chunk_url)
            if isinstance(items, dict) and "data" in items:
                items = items["data"]
            
            # Batch upsert
            comp_rows = []
            vac_rows = []
            fts_rows = []

            for item in items:
                v_id = item.get("id")
                if not v_id:
                    continue

                # Organizer
                org = item.get("organizer") or {}
                org_id = org.get("id")
                org_name = org.get("name") or "Perusahaan / Instansi"
                org_type = org.get("type") or "Perusahaan"
                org_city = org.get("city") or {}

                if org_id:
                    comp_rows.append((
                        org_id,
                        org_name,
                        org_type,
                        org.get("email"),
                        org.get("phone"),
                        org.get("address"),
                        org.get("logo_url"),
                        org_city.get("id"),
                        org_city.get("name"),
                        org_city.get("province_id")
                    ))

                # Location & District
                loc = item.get("location") or {}
                addr = loc.get("address") or ""
                district = extract_district(addr)
                p_id = loc.get("province_id") or org_city.get("province_id")
                p_name = prov_map.get(p_id)

                # Study programs
                s_progs = item.get("study_programs") or []
                s_prog_names = " ".join([p.get("name", "") for p in s_progs if isinstance(p, dict)]).lower()
                
                # Edu levels
                edu_levels = item.get("education_levels") or []

                pos_name = item.get("position_name") or item.get("title") or ""
                desc = item.get("task_description") or ""
                city_name = loc.get("city_name") or org_city.get("name") or ""

                vac_rows.append((
                    v_id,
                    pos_name,
                    item.get("title") or pos_name,
                    desc,
                    item.get("quantity_needed") or 0,
                    item.get("approved_quantity") or 0,
                    item.get("total_applications") or 0,
                    item.get("competitive_score") or 0.0,
                    item.get("opportunity_score") or 0.0,
                    json.dumps(edu_levels),
                    json.dumps(s_progs),
                    s_prog_names,
                    org_id,
                    org_name,
                    org_type,
                    loc.get("city_id"),
                    city_name,
                    p_id,
                    p_name,
                    district,
                    addr,
                    loc.get("latitude"),
                    loc.get("longitude"),
                    item.get("working_days_per_week"),
                    json.dumps(item.get("days_off") or []),
                    json.dumps(item.get("interview_types") or []),
                    item.get("published_at"),
                    item.get("created_at"),
                    item.get("updated_at"),
                    item.get("url"),
                    item.get("scraped_at")
                ))

                fts_rows.append((
                    v_id,
                    pos_name,
                    desc,
                    org_name,
                    s_prog_names,
                    city_name,
                    p_name or ""
                ))

            # Execute batch inserts
            if comp_rows:
                cursor.executemany("""
                INSERT INTO companies (
                    id, name, type, email, phone, address, logo_url, city_id, city_name, province_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    type=excluded.type,
                    email=coalesce(excluded.email, companies.email),
                    phone=coalesce(excluded.phone, companies.phone),
                    address=coalesce(excluded.address, companies.address),
                    logo_url=coalesce(excluded.logo_url, companies.logo_url),
                    updated_at=CURRENT_TIMESTAMP
                """, comp_rows)
                total_companies_upserted += len(comp_rows)

            if vac_rows:
                cursor.executemany("""
                INSERT INTO vacancies (
                    id, position_name, title, task_description, quantity_needed,
                    approved_quantity, total_applications, competitive_score,
                    opportunity_score, education_levels, study_programs, study_program_names,
                    organizer_id, organizer_name, organizer_type, city_id, city_name,
                    province_id, province_name, district_name, address, latitude,
                    longitude, working_days_per_week, days_off, interview_types,
                    published_at, created_at, updated_at, url, scraped_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    position_name=excluded.position_name,
                    title=excluded.title,
                    task_description=excluded.task_description,
                    quantity_needed=excluded.quantity_needed,
                    approved_quantity=excluded.approved_quantity,
                    total_applications=excluded.total_applications,
                    competitive_score=excluded.competitive_score,
                    opportunity_score=excluded.opportunity_score,
                    education_levels=excluded.education_levels,
                    study_programs=excluded.study_programs,
                    study_program_names=excluded.study_program_names,
                    organizer_id=excluded.organizer_id,
                    organizer_name=excluded.organizer_name,
                    organizer_type=excluded.organizer_type,
                    city_id=excluded.city_id,
                    city_name=excluded.city_name,
                    province_id=excluded.province_id,
                    province_name=excluded.province_name,
                    district_name=excluded.district_name,
                    address=excluded.address,
                    latitude=excluded.latitude,
                    longitude=excluded.longitude,
                    working_days_per_week=excluded.working_days_per_week,
                    days_off=excluded.days_off,
                    interview_types=excluded.interview_types,
                    published_at=excluded.published_at,
                    updated_at=excluded.updated_at,
                    url=excluded.url,
                    scraped_at=excluded.scraped_at
                """, vac_rows)
                total_vacancies_upserted += len(vac_rows)

                # Update FTS5 (delete old then insert)
                v_ids = [r[0] for r in vac_rows]
                cursor.executemany("DELETE FROM vacancies_fts WHERE id = ?", [(vid,) for vid in v_ids])
                cursor.executemany("""
                INSERT INTO vacancies_fts (id, position_name, task_description, organizer_name, study_program_names, city_name, province_name)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, fts_rows)

            conn.commit()
        except Exception as e:
            logger.error(f"Error processing chunk {ch_file}: {e}")
            conn.rollback()

    # Save sync meta
    cursor.execute("""
    INSERT INTO sync_meta (key, value) VALUES ('generated_at', ?)
    ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP
    """, (remote_gen,))
    cursor.execute("""
    INSERT INTO sync_meta (key, value) VALUES ('last_sync_time', ?)
    ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP
    """, (datetime.utcnow().isoformat(),))
    conn.commit()
    conn.close()

    logger.info(f"Sync complete. Vacancies upserted: {total_vacancies_upserted}, Companies: {total_companies_upserted}")
    return {
        "status": "success",
        "generated_at": remote_gen,
        "vacancies_upserted": total_vacancies_upserted,
        "companies_upserted": total_companies_upserted
    }
