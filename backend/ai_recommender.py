import os
import io
import json
import logging
import urllib.request
import ssl
from pypdf import PdfReader
from backend.database import get_db_connection

logger = logging.getLogger(__name__)

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

def extract_text_from_pdf_bytes(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    extracted = []
    for page in reader.pages:
        txt = page.extract_text()
        if txt:
            extracted.append(txt)
    return "\n".join(extracted)

def call_ai_chat_completion(
    provider: str,
    api_key: str,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    base_url: str = None
) -> str:
    """
    Multi-Provider AI Gateway:
    - openai / deepseek / groq / openrouter / custom: uses OpenAI-compatible standard chat completions endpoint
    - anthropic: uses Anthropic Messages API
    - gemini: uses Google Gemini API (or OpenAI compatible v1beta endpoint)
    """
    provider = (provider or "anthropic").lower().strip()
    
    # 1. ANTHROPIC CLAUDE
    if provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        model = model_name or "claude-3-5-sonnet-20241022"
        res = client.messages.create(
            model=model,
            max_tokens=1500,
            temperature=0.2,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )
        return res.content[0].text.strip()

    # Determine Base URL & Default Model for OpenAI-compatible providers
    endpoint_url = base_url
    default_model = model_name

    if provider == "openai":
        endpoint_url = endpoint_url or "https://api.openai.com/v1/chat/completions"
        default_model = default_model or "gpt-4o-mini"
    elif provider == "deepseek":
        endpoint_url = endpoint_url or "https://api.deepseek.com/chat/completions"
        default_model = default_model or "deepseek-chat"
    elif provider == "groq":
        endpoint_url = endpoint_url or "https://api.groq.com/openai/v1/chat/completions"
        default_model = default_model or "llama-3.3-70b-versatile"
    elif provider == "openrouter":
        endpoint_url = endpoint_url or "https://openrouter.ai/api/v1/chat/completions"
        default_model = default_model or "meta-llama/llama-3.3-70b-instruct"
    elif provider in ["gemini", "google"]:
        # Gemini provides OpenAI compatibility endpoint
        endpoint_url = endpoint_url or "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        default_model = default_model or "gemini-1.5-flash"
    else:
        # Custom provider / self-hosted
        if not endpoint_url:
            raise ValueError(f"Base URL / Endpoint wajib diisi untuk custom provider '{provider}'")
        default_model = default_model or "default"

    # Make standard HTTP request to OpenAI-compatible endpoint
    payload = {
        "model": default_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.2
    }

    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(endpoint_url, data=req_data, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "MagangHubTracker/1.0"
    })

    try:
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=40) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Error calling AI Provider {provider} ({endpoint_url}): {e}")
        raise RuntimeError(f"Gagal memanggil API {provider}: {str(e)}")

def parse_json_from_ai(text: str):
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        for p in parts:
            p = p.strip()
            if p.startswith("json"):
                p = p[4:].strip()
            if (p.startswith("{") and p.endswith("}")) or (p.startswith("[") and p.endswith("]")):
                text = p
                break
    return json.loads(text)

def analyze_cv_with_ai(
    cv_text: str,
    provider: str = "anthropic",
    api_key: str = "",
    model_name: str = "",
    base_url: str = None
) -> dict:
    system_prompt = """
    Kamu adalah asisten analisis karir dan resume. Tugasmu adalah menganalisis teks resume/CV mahasiswa/fresh graduate
    lalu mengekstrak poin kunci dalam format JSON murni tanpa markdown pembuka/penutup.
    
    Format JSON:
    {
        "study_programs": ["jurusan atau bidang studi, misal Teknik Informatika, Sistem Informasi, Manajemen, dll"],
        "education_level": "jenjang pendidikan misal 'Sarjana', 'Diploma', 'SMK / SMA'",
        "skills": ["daftar skill teknis & soft skills utama"],
        "career_interests": ["bidang minat magang, misal Data Analyst, Software Engineer, HR, Marketing"],
        "summary": "ringkasan 2 kalimat tentang profil pelamar"
    }
    """

    user_prompt = f"Berikut adalah teks resume/CV:\n\n{cv_text[:6000]}\n\nEkstrak data sesuai format JSON."

    resp_text = call_ai_chat_completion(
        provider=provider,
        api_key=api_key,
        model_name=model_name,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        base_url=base_url
    )
    return parse_json_from_ai(resp_text)

def calculate_real_opportunity_score(approved_qty: int, total_apps: int) -> float:
    """
    Perhitungan Peluang Diterima Realistis:
    - approved_qty: kuota posisi
    - total_apps: pelamar saat ini
    - remaining_slots = max(0, approved_qty - total_apps)
    - Jika kuota belum penuh: peluang = 100 * (kuota / (pelamar + 1)) ditutup max 100%
    - Jika sudah penuh atau over: peluang melorot proporsional kuota/pelamar
    """
    qty = max(1, approved_qty or 1)
    apps = max(0, total_apps or 0)
    
    if apps == 0:
        # Belum ada pelamar sama sekali: peluang emas
        return 98.0
    
    # Rasio kuota terhadap pelamar
    ratio = qty / apps
    if ratio >= 1.0:
        # Masih ada sisa kuota atau imbang
        remaining = max(0, qty - apps)
        # Probabilitas logistik halus
        score = 50.0 + (remaining / qty) * 45.0
        return round(min(98.0, max(50.0, score)), 1)
    else:
        # Pelamar sudah melebihi kuota
        # Semakin padat persaingan, persentase peluang semakin turun
        score = (qty / apps) * 50.0
        return round(max(5.0, min(49.0, score)), 1)

def match_and_rank_vacancies(
    cv_profile: dict,
    provider: str = "anthropic",
    api_key: str = "",
    model_name: str = "",
    base_url: str = None,
    top_k: int = 12
):
    conn = get_db_connection()
    cursor = conn.cursor()

    progs = cv_profile.get("study_programs", [])
    edu = cv_profile.get("education_level")

    prog_conditions = []
    params = []
    for p in progs:
        prog_conditions.append("(study_program_names LIKE ? OR study_programs LIKE ?)")
        params.append(f"%{p.lower()}%")
        params.append(f"%{p}%")

    sql = """
    SELECT id, position_name, task_description, organizer_name, city_name, province_name,
           opportunity_score, approved_quantity, total_applications, education_levels, study_programs, url
    FROM vacancies
    """
    
    where = []
    if prog_conditions:
        where.append("(" + " OR ".join(prog_conditions) + ")")
    if edu:
        where.append("education_levels LIKE ?")
        params.append(f"%{edu}%")

    if where:
        sql += " WHERE " + " AND ".join(where)

    sql += " ORDER BY published_at DESC LIMIT 60"
    cursor.execute(sql, params)
    candidates = [dict(r) for r in cursor.fetchall()]

    if len(candidates) < 10:
        cursor.execute("""
        SELECT id, position_name, task_description, organizer_name, city_name, province_name,
               opportunity_score, approved_quantity, total_applications, education_levels, study_programs, url
        FROM vacancies
        ORDER BY published_at DESC LIMIT 40
        """)
        candidates.extend([dict(r) for r in cursor.fetchall()])

    conn.close()

    if not candidates:
        return []

    # Recalculate real opportunity score for all candidates
    for c in candidates:
        c["real_opportunity_score"] = calculate_real_opportunity_score(
            c.get("approved_quantity", 1),
            c.get("total_applications", 0)
        )

    if not api_key:
        # Offline fallback matching
        candidates.sort(key=lambda x: x["real_opportunity_score"], reverse=True)
        results = []
        for c in candidates[:top_k]:
            results.append({
                "vacancy": c,
                "score": int(c["real_opportunity_score"]),
                "reason": f"Sesuai kualifikasi jurusan {', '.join(progs) if progs else ''} dengan estimasi peluang diterima {c['real_opportunity_score']}%."
            })
        return results

    # AI Ranking with selected provider
    shortened_candidates = []
    for i, c in enumerate(candidates[:35]):
        desc_snippet = (c.get("task_description") or "")[:200].replace("\n", " ")
        shortened_candidates.append({
            "id": c["id"],
            "title": c["position_name"],
            "company": c["organizer_name"],
            "location": f"{c.get('city_name', '')}, {c.get('province_name', '')}",
            "description": desc_snippet,
            "opportunity": f"{c['real_opportunity_score']}%"
        })

    eval_prompt = f"""
    Pelamar:
    - Jurusan: {', '.join(cv_profile.get('study_programs', []))}
    - Minat Karir: {', '.join(cv_profile.get('career_interests', []))}
    - Skills: {', '.join(cv_profile.get('skills', []))}
    - Ringkasan: {cv_profile.get('summary', '')}

    Daftar Kandidat Lowongan:
    {json.dumps(shortened_candidates, ensure_ascii=False, indent=2)}

    Tugas:
    Pilih top {top_k} lowongan paling relevan untuk pelamar ini.
    Berikan skor kesesuaian profil (0-100) dan alasan spesifik 1-2 kalimat mengapa posisi ini cocok.

    Keluarkan HANYA JSON array format:
    [
        {{
            "id": "UUID lowongan",
            "score": 95,
            "match_reason": "Alasan kecocokan..."
        }}
    ]
    """

    resp_text = call_ai_chat_completion(
        provider=provider,
        api_key=api_key,
        model_name=model_name,
        system_prompt="Kamu adalah career coach profesional. Jawab HANYA dengan format JSON murni.",
        user_prompt=eval_prompt,
        base_url=base_url
    )

    ranked_list = parse_json_from_ai(resp_text)
    cand_map = {c["id"]: c for c in candidates}
    final_output = []

    for item in ranked_list:
        v_id = item.get("id")
        if v_id in cand_map:
            final_output.append({
                "vacancy": cand_map[v_id],
                "score": item.get("score", 85),
                "reason": item.get("match_reason", "Relevan dengan keahlian dan minat kamu.")
            })

    return final_output
