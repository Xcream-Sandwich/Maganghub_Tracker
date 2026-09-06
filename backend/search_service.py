import json
from typing import List, Optional, Union
from backend.database import get_db_connection

def calculate_real_opportunity(approved_qty: int, total_apps: int) -> float:
    qty = max(1, approved_qty or 1)
    apps = max(0, total_apps or 0)
    if apps == 0:
        return 98.0
    ratio = qty / apps
    if ratio >= 1.0:
        remaining = max(0, qty - apps)
        score = 50.0 + (remaining / qty) * 45.0
        return round(min(98.0, max(50.0, score)), 1)
    else:
        score = (qty / apps) * 50.0
        return round(max(5.0, min(49.0, score)), 1)

def search_vacancies(
    keyword: Optional[str] = None,
    province_ids: Optional[Union[List[str], str]] = None,
    city_names: Optional[Union[List[str], str]] = None,
    district_names: Optional[Union[List[str], str]] = None,
    study_programs: Optional[Union[List[str], str]] = None,
    education_levels: Optional[Union[List[str], str]] = None,
    organizer_types: Optional[Union[List[str], str]] = None,
    organizer_name: Optional[str] = None,
    min_quota: Optional[int] = None,
    sort_by: str = "terbaru",
    page: int = 1,
    limit: int = 18
):
    conn = get_db_connection()
    cursor = conn.cursor()

    conditions = []
    params = []

    # 1. Keyword search
    if keyword and keyword.strip():
        kw = keyword.strip()
        cleaned = "".join([c if c.isalnum() or c.isspace() else " " for c in kw]).strip()
        tokens = cleaned.split() if cleaned else []
        if tokens:
            fts_query = " ".join([f'"{tok}"*' for tok in tokens])
            conditions.append("v.id IN (SELECT id FROM vacancies_fts WHERE vacancies_fts MATCH ?)")
            params.append(fts_query)
        else:
            conditions.append("(v.position_name LIKE ? OR v.task_description LIKE ? OR v.organizer_name LIKE ?)")
            pat = f"%{kw}%"
            params.extend([pat, pat, pat])

    # Helper for multi-value filters
    def ensure_list(val):
        if not val:
            return []
        if isinstance(val, list):
            # Also handle comma separated inside list items
            res = []
            for item in val:
                for sub in str(item).split(","):
                    if sub.strip():
                        res.append(sub.strip())
            return res
        return [s.strip() for s in str(val).split(",") if s.strip()]

    # 2. Provinces (Multi-select)
    p_ids = ensure_list(province_ids)
    if p_ids:
        placeholders = ",".join(["?"] * len(p_ids))
        conditions.append(f"v.province_id IN ({placeholders})")
        params.extend(p_ids)

    # 3. Cities (Multi-select)
    c_names = ensure_list(city_names)
    if c_names:
        placeholders = ",".join(["?"] * len(c_names))
        conditions.append(f"v.city_name IN ({placeholders})")
        params.extend(c_names)

    # 4. Districts (Multi-select / Search)
    d_names = ensure_list(district_names)
    if d_names:
        d_or = []
        for d in d_names:
            d_or.append("v.district_name LIKE ?")
            params.append(f"%{d}%")
        conditions.append("(" + " OR ".join(d_or) + ")")

    # 5. Study Programs (Multi-select)
    sp_list = ensure_list(study_programs)
    if sp_list:
        sp_or = []
        for sp in sp_list:
            sp_or.append("(v.study_program_names LIKE ? OR v.study_programs LIKE ?)")
            params.append(f"%{sp.lower()}%")
            params.append(f"%{sp}%")
        conditions.append("(" + " OR ".join(sp_or) + ")")

    # 6. Education Levels (Multi-select)
    edu_list = ensure_list(education_levels)
    if edu_list:
        edu_or = []
        for edu in edu_list:
            edu_or.append("v.education_levels LIKE ?")
            params.append(f"%{edu}%")
        conditions.append("(" + " OR ".join(edu_or) + ")")

    # 7. Organizer Types (Multi-select)
    org_types = ensure_list(organizer_types)
    if org_types:
        placeholders = ",".join(["?"] * len(org_types))
        conditions.append(f"v.organizer_type IN ({placeholders})")
        params.extend(org_types)

    # 8. Organizer Name
    if organizer_name and organizer_name.strip():
        conditions.append("v.organizer_name LIKE ?")
        params.append(f"%{organizer_name.strip()}%")

    # 9. Minimum Quota
    if min_quota is not None and min_quota > 0:
        conditions.append("v.approved_quantity >= ?")
        params.append(min_quota)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    # Sorting
    # Catatan: Peluang Tertinggi menggunakan rumus realistis di SQL:
    # Peluang = (approved_quantity / max(1, total_applications)) desc
    sort_clause = "ORDER BY v.published_at DESC NULLS LAST"
    if sort_by == "kuota":
        sort_clause = "ORDER BY v.approved_quantity DESC, v.published_at DESC"
    elif sort_by == "peluang":
        sort_clause = "ORDER BY (CAST(v.approved_quantity AS REAL) / (CASE WHEN v.total_applications = 0 THEN 0.5 ELSE v.total_applications END)) DESC, v.approved_quantity DESC"
    elif sort_by == "kompetisi":
        sort_clause = "ORDER BY v.total_applications ASC, v.approved_quantity DESC"

    # Count total
    count_sql = f"SELECT COUNT(*) FROM vacancies v {where_clause}"
    cursor.execute(count_sql, params)
    total_count = cursor.fetchone()[0]

    # Pagination
    offset = max(0, (page - 1) * limit)
    query_sql = f"""
    SELECT 
        v.id, v.position_name, v.title, v.task_description,
        v.quantity_needed, v.approved_quantity, v.total_applications,
        v.competitive_score, v.opportunity_score,
        v.education_levels, v.study_programs,
        v.organizer_id, v.organizer_name, v.organizer_type,
        v.city_id, v.city_name, v.province_id, v.province_name,
        v.district_name, v.address, v.latitude, v.longitude,
        v.working_days_per_week, v.days_off, v.interview_types,
        v.published_at, v.created_at, v.url, v.scraped_at,
        c.logo_url as company_logo
    FROM vacancies v
    LEFT JOIN companies c ON v.organizer_id = c.id
    {where_clause}
    {sort_clause}
    LIMIT ? OFFSET ?
    """
    
    query_params = list(params) + [limit, offset]
    cursor.execute(query_sql, query_params)
    rows = cursor.fetchall()

    results = []
    for r in rows:
        d = dict(r)
        # Calculate real opportunity percentage
        d["opportunity_score"] = calculate_real_opportunity(
            d.get("approved_quantity", 1),
            d.get("total_applications", 0)
        )
        try:
            d["education_levels"] = json.loads(d["education_levels"]) if d["education_levels"] else []
        except:
            d["education_levels"] = []
        try:
            d["study_programs"] = json.loads(d["study_programs"]) if d["study_programs"] else []
        except:
            d["study_programs"] = []
        try:
            d["days_off"] = json.loads(d["days_off"]) if d["days_off"] else []
        except:
            d["days_off"] = []
        try:
            d["interview_types"] = json.loads(d["interview_types"]) if d["interview_types"] else []
        except:
            d["interview_types"] = []
        results.append(d)

    conn.close()

    total_pages = (total_count + limit - 1) // limit if limit > 0 else 1

    return {
        "items": results,
        "total": total_count,
        "page": page,
        "limit": limit,
        "total_pages": total_pages
    }

def get_vacancy_detail(v_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT 
        v.*,
        c.logo_url as company_logo,
        c.email as company_email,
        c.phone as company_phone,
        c.address as company_address
    FROM vacancies v
    LEFT JOIN companies c ON v.organizer_id = c.id
    WHERE v.id = ?
    """, (v_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    detail = dict(row)
    # Calculate real opportunity score
    detail["opportunity_score"] = calculate_real_opportunity(
        detail.get("approved_quantity", 1),
        detail.get("total_applications", 0)
    )

    for json_col in ["education_levels", "study_programs", "days_off", "interview_types"]:
        try:
            detail[json_col] = json.loads(detail[json_col]) if detail[json_col] else []
        except:
            detail[json_col] = []

    # Get UMK estimation
    city_name = detail.get("city_name")
    prov_name = detail.get("province_name")
    
    umk_info = None
    if city_name:
        cursor.execute("SELECT area_name, umk_value, year, source FROM umk_reference WHERE area_name = ? AND area_type = 'city'", (city_name,))
        u_row = cursor.fetchone()
        if u_row:
            umk_info = {
                "area_name": u_row["area_name"],
                "type": "UMK Kota/Kabupaten",
                "value": u_row["umk_value"],
                "year": u_row["year"],
                "source": u_row["source"]
            }
    
    if not umk_info and prov_name:
        cursor.execute("SELECT area_name, umk_value, year, source FROM umk_reference WHERE area_name = ? AND area_type = 'province'", (prov_name,))
        u_row = cursor.fetchone()
        if u_row:
            umk_info = {
                "area_name": u_row["area_name"],
                "type": "UMP Provinsi (Acuan Umum)",
                "value": u_row["umk_value"],
                "year": u_row["year"],
                "source": u_row["source"]
            }

    detail["umk_estimation"] = umk_info
    conn.close()
    return detail

def get_filter_options():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Provinces
    cursor.execute("""
    SELECT DISTINCT p.id, p.name 
    FROM provinces p 
    JOIN vacancies v ON p.id = v.province_id 
    ORDER BY p.name ASC
    """)
    provinces = [{"id": r["id"], "name": r["name"]} for r in cursor.fetchall()]

    # Cities
    cursor.execute("""
    SELECT DISTINCT province_id, city_name 
    FROM vacancies 
    WHERE city_name IS NOT NULL AND city_name != ''
    ORDER BY city_name ASC
    """)
    cities = [{"province_id": r["province_id"], "city_name": r["city_name"]} for r in cursor.fetchall()]

    # Organizer types
    cursor.execute("""
    SELECT DISTINCT organizer_type 
    FROM vacancies 
    WHERE organizer_type IS NOT NULL AND organizer_type != ''
    ORDER BY organizer_type ASC
    """)
    org_types = [r["organizer_type"] for r in cursor.fetchall()]

    # Education levels
    edu_levels = ["Diploma", "Sarjana", "Magister", "Doktor", "SMK / SMA"]

    conn.close()
    return {
        "provinces": provinces,
        "cities": cities,
        "organizer_types": org_types,
        "education_levels": edu_levels
    }
