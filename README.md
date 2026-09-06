# 🇮🇩 MagangHub Tracker

> **Mirror Cepat & Cerdas Lowongan Program Magang Nasional Kemnaker RI**

Aplikasi web pencarian lowongan Program Magang Nasional Kemnaker dengan performa kilat, multi-select filter, estimasi acuan UMK wilayah 2026, peta interaktif penempatan, serta pencocokan rekomendasi cerdas dari CV menggunakan berbagai provider AI (Anthropic Claude, OpenAI, Google Gemini, DeepSeek, Groq, dll).

---

## ✨ Fitur Utama

- ⚡ **Pencarian Kilat (Full-Text Search FTS5)**: Pencarian instan pada posisi, tugas, dan nama perusahaan.
- 🎯 **Kalkulasi Peluang Realistis**: Menghitung persentase peluang diterima berdasarkan kuota posisi vs pelamar aktif.
- 🎛️ **Multi-Select Filter Lengkap**:
  - Filter banyak provinsi & banyak kota/kabupaten sekaligus.
  - Jenjang pendidikan (Diploma, Sarjana, Magister, SMK/SMA).
  - Jenis instansi (Perusahaan / Swasta / BUMN vs Kementerian / Lembaga Pemerintah).
  - Program studi fleksibel (multi-jurusan).
  - Slider minimal kuota & filter kecamatan (hasil ekstraksi otomatis alamat).
- 💰 **Estimasi Acuan UMK Daerah 2026**:
  - Menampilkan referensi Upah Minimum Kota/Kabupaten & UMP tahun 2026 sebagai acuan biaya hidup (disertai disclaimer uang saku magang).
- 🗺️ **Peta Penempatan (Leaflet.js)**: Visualisasi lokasi kantor/penempatan interaktif jika koordinat tersedia.
- 🤖 **Rekomendasi AI CV (Multi-Provider)**:
  - Drag-and-drop file resume PDF.
  - Bebas memilih provider AI: Anthropic Claude, OpenAI (GPT-4o), Google Gemini, DeepSeek, Groq, OpenRouter, atau server lokal (Custom OpenAI-Compatible).
  - Parsing PDF in-memory (file langsung dihapus demi privasi).
  - Tersedia Offline Matcher fallback tanpa API Key.
- 🔄 **Sinkronisasi Otomatis**: Background periodic sync harian dari endpoint terbuka Kemnaker (`maganghab.my.id`).

---

## 🛠️ Menjalankan Aplikasi

### 1. Prasyarat
- Python 3.10+
- Dependensi: `fastapi`, `uvicorn`, `python-multipart`, `pypdf`, `anthropic`

### 2. Instalasi Dependensi
```bash
pip install fastapi uvicorn python-multipart pypdf anthropic
```

### 3. Jalankan Server
```bash
python run.py
```
Aplikasi akan aktif di:
- **Dashboard Utama**: `http://127.0.0.1:8000`
- **Rekomendasi AI CV**: `http://127.0.0.1:8000/cv-matcher`

---

## ⚖️ Atribusi & Etika
Data lowongan bersumber dari **Program Magang Nasional Kementerian Ketenagakerjaan RI**, dimediasi melalui penyedia data terbuka *maganghab.my.id*. Setiap lowongan dilengkapi link rujukan ke portal resmi Kemnaker.
