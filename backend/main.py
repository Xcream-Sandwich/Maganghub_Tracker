import os
import asyncio
from contextlib import asynccontextmanager
from typing import Optional, List
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from backend.database import init_db, get_db_connection
from backend.sync_service import sync_all
from backend.search_service import search_vacancies, get_vacancy_detail, get_filter_options
from backend.scheduler import start_periodic_sync
from backend.ai_recommender import extract_text_from_pdf_bytes, analyze_cv_with_ai, match_and_rank_vacancies

@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("VERCEL"):
        # In the Vercel read‑only environment we cannot write to the DB or spawn background tasks.
        # Assume the bundled DB is already initialized.
        yield
        return
    # Local/development environment – keep existing behaviour.
    init_db()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM vacancies")
    count = c.fetchone()[0]
    conn.close()

    if count == 0:
        asyncio.create_task(asyncio.to_thread(sync_all, force=True, max_chunks=8))

    scheduler_task = asyncio.create_task(start_periodic_sync(interval_hours=3))
    yield
    scheduler_task.cancel()

app = FastAPI(title="MagangHub Tracker", version="1.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health():
    return {"status": "ok", "app": "MagangHub Tracker"}

@app.get("/api/meta")
def get_metadata():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT key, value, updated_at FROM sync_meta")
        meta = {r["key"]: {"value": r["value"], "updated_at": r["updated_at"]} for r in c.fetchall()}
        c.execute("SELECT COUNT(*) FROM vacancies")
        total_vacancies = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM companies")
        total_companies = c.fetchone()[0]
        conn.close()
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"error": "Database tidak tersedia sementara, coba lagi.", "detail": str(e)}
        )
    return {
        "sync_meta": meta,
        "total_vacancies": total_vacancies,
        "total_companies": total_companies
    }

@app.post("/api/sync")
def trigger_sync(background_tasks: BackgroundTasks, force: bool = False):
    background_tasks.add_task(sync_all, force=force)
    return {"status": "started", "message": "Sinkronisasi data sedang berjalan di background."}

@app.get("/api/filters")
def filter_options():
    return get_filter_options()

@app.get("/api/vacancies")
def list_vacancies(
    keyword: Optional[str] = Query(None),
    province_id: Optional[List[str]] = Query(None),
    city_name: Optional[List[str]] = Query(None),
    district_name: Optional[str] = Query(None),
    study_program: Optional[List[str]] = Query(None),
    education_level: Optional[List[str]] = Query(None),
    organizer_type: Optional[List[str]] = Query(None),
    organizer_name: Optional[str] = Query(None),
    min_quota: Optional[int] = Query(None),
    sort_by: str = Query("terbaru", pattern="^(terbaru|kuota|peluang|kompetisi)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(18, ge=1, le=100)
):
    return search_vacancies(
        keyword=keyword,
        province_ids=province_id,
        city_names=city_name,
        district_names=[district_name] if district_name else None,
        study_programs=study_program,
        education_levels=education_level,
        organizer_types=organizer_type,
        organizer_name=organizer_name,
        min_quota=min_quota,
        sort_by=sort_by,
        page=page,
        limit=limit
    )

@app.get("/api/vacancies/{vacancy_id}")
def vacancy_detail(vacancy_id: str):
    detail = get_vacancy_detail(vacancy_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Lowongan tidak ditemukan.")
    return detail

@app.post("/api/ai/match-cv")
async def match_cv_endpoint(
    cv_file: UploadFile = File(...),
    provider: str = Form("anthropic"),
    api_key: Optional[str] = Form(None),
    model_name: Optional[str] = Form(None),
    base_url: Optional[str] = Form(None)
):
    if not cv_file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Format file harus PDF.")

    content = await cv_file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Ukuran file maksimal 10MB.")

    # 1. Parse PDF text
    try:
        cv_text = extract_text_from_pdf_bytes(content)
        if not cv_text.strip():
            raise HTTPException(status_code=400, detail="Tidak dapat mengekstrak teks dari PDF (dokumen mungkin scan gambar murni tanpa teks OCR).")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Gagal membaca PDF: {str(e)}")

    used_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")

    # 2. Extract profile with selected AI Provider
    profile = {}
    if used_key:
        try:
            profile = analyze_cv_with_ai(
                cv_text=cv_text,
                provider=provider,
                api_key=used_key,
                model_name=model_name,
                base_url=base_url
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Gagal memproses via AI Provider ({provider}): {str(e)}")
    else:
        # Offline rule-based fallback
        profile = {
            "study_programs": ["Teknik Informatika", "Sistem Informasi", "Manajemen", "Akuntansi"],
            "education_level": "Sarjana",
            "skills": ["Analisis Data", "Komunikasi", "Problem Solving"],
            "career_interests": ["Teknologi", "Administrasi", "Bisnis"],
            "summary": "Profil diekstrak dengan mode offline (masukkan API Key AI untuk analisis dinamis dan akurat)."
        }

    # 3. Two-stage matching & ranking
    recommendations = match_and_rank_vacancies(
        cv_profile=profile,
        provider=provider,
        api_key=used_key,
        model_name=model_name,
        base_url=base_url,
        top_k=12
    )

    return {
        "profile": profile,
        "recommendations": recommendations,
        "has_ai_key": bool(used_key),
        "provider": provider,
        "model": model_name or "default"
    }

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.get("/cv-matcher")
def cv_matcher_page():
    return FileResponse(os.path.join(STATIC_DIR, "cv_matcher.html"))
