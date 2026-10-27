import streamlit as st
import requests
import base64
import pymupdf

# Konfigurasi Halaman
st.set_page_config(page_title="Tender Checker - Deep Audit Pro", layout="wide")
st.title("Tender Checker: Deep Audit HSSE Plan (Mode Gemini Pro)")

# Mengambil API Key
try:
    API_KEY = st.secrets["GEMINI_API_KEY"].strip()
except Exception:
    st.error("Kunci API gagal diakses. Pastikan pengaturan rahasia (Secrets) di Streamlit sudah benar.")
    API_KEY = None

# Fungsi Otomatis Mencari & Memprioritaskan Model GEMINI PRO
@st.cache_data(ttl=3600)
def get_pro_models(api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    response = requests.get(url)
    if response.status_code == 200:
        models_data = response.json().get("models", [])
        pro_models = []
        other_models = []
        for m in models_data:
            methods = m.get("supportedGenerationMethods", [])
            name = m.get("name", "")
            if "generateContent" in methods and "gemini" in name.lower():
                # Pisahkan model kelas PRO agar selalu di urutan teratas
                if "pro" in name.lower() and "vision" not in name.lower():
                    pro_models.append(name)
                else:
                    other_models.append(name)
        pro_models.sort(reverse=True)
        other_models.sort(reverse=True)
        return pro_models + other_models
    return []

# Fungsi Mengubah PDF Menjadi Paket Visual Native (Membaca Tabel, Gambar & Scan) + Teks Berhalaman
def prepare_pdf_parts(pdf_files, label_kategori):
    parts = [{"text": f"\n\n=== AWAL DOKUMEN: {label_kategori} ==="}]
    for pdf_file in pdf_files:
        pdf_file.seek(0)
        raw_bytes = pdf_file.read()
        b64_data = base64.b64encode(raw_bytes).decode("utf-8")
        
        # 1. Kirim file PDF secara visual (Native Multimodal) agar tabel & gambar terbaca 100%
        parts.append({"text": f"\n[File PDF Visual: {pdf_file.name}]"})
        parts.append({
            "inline_data": {
                "mime_type": "application/pdf",
                "data": b64_data
            }
        })
        
        # 2. Kirim indeks teks per halaman untuk memastikan akurasi nomor halaman
        doc = pymupdf.open(stream=raw_bytes, filetype="pdf")
        page_texts = f"\n[Indeks Teks Per Halaman untuk {pdf_file.name}]:\n"
        for idx, page in enumerate(doc):
            page_texts += f"\n--- HALAMAN {idx + 1} ({pdf_file.name}) ---\n{page.get_text()}"
        parts.append({"text": page_texts})
        
    parts.append({"text": f"\n=== AKHIR DOKUMEN: {label_kategori} ===\n"})
    return parts

# Pemilihan Model AI (Prioritas GEMINI PRO)
selected_model = None
available_models = []
if API_KEY:
    available_models = get_pro_models(API_KEY)
    if available_models:
        # Otomatis pilih model PRO generasi terbaru yang tidak diblokir untuk akun baru
        default_idx = 0
        for i, m in enumerate(available_models):
            if "pro" in m.lower() and "2.5" not in m.lower() and "1.5" not in m.lower():
                default_idx = i
                break
        
        selected_model = st.selectbox(
            "Pilih Model AI (Disarankan menggunakan model berlabel 'pro' untuk akurasi tinggi):",
            available_models,
            index=default_idx
        )
    else:
        st.error("Gagal memuat daftar model dari server Google.")

# Antarmuka Unggah Dokumen
col1, col2 = st.columns(2)
with col1:
    st.subheader("1. Dokumen Instruksi Tender (Ground Truth)")
    tor_files = st.file_uploader(
        "Unggah PDF TOR, IKPP & Lampiran D Elnusa", 
        type=["pdf"], 
        accept_multiple_files=True
    )
with col2:
    st.subheader("2. Dokumen HSSE Plan Vendor (Objek Audit)")
    hsse_files = st.file_uploader(
        "Unggah PDF HSSE Plan Vendor", 
        type=["pdf"], 
        accept_multiple_files=True
    )

# Instruksi Audit Mendalam (Strict Checklist)
SYSTEM_PROMPT = """
Anda adalah Lead Auditor HSSE Senior PT Elnusa Tbk.
Tugas Anda adalah melakukan audit kepatuhan secara menyeluruh, halaman demi halaman, dengan membandingkan DOKUMEN HSSE PLAN VENDOR terhadap DOKUMEN INSTRUKSI TENDER (TOR/IKPP/Lampiran D).

ATURAN KETAT AUDIT (ANTI-HALUSINASI):
1. DILARANG KERAS menebak atau mengasumsikan pelanggaran yang tidak tertulis di dokumen.
2. Setiap temuan WAJIB menyertakan kutipan teks asli dan NOMOR HALAMAN spesifik baik dari dokumen TOR/IKPP maupun dari dokumen HSSE Plan.
3. Periksa seluruh teks di dalam GAMBAR/BAGAN (seperti gambar Struktur Organisasi, kop surat, tanda tangan) dan baca setiap baris-kolom TABEL dengan teliti.

LAKUKAN PEMERIKSAAN MENYELURUH PADA 10 AREA WAJIB BERIKUT:
1. Identitas Perusahaan, Klien & Nama Proyek: Apakah ada salah ketik nama perusahaan (misal: Bersama vs Berjaya), salah nama klien pada bagan gambar (misal: tertulis PT Pertamina EP padahal tender PT Elnusa Tbk), atau salah nama lokasi/proyek akibat copy-paste?
2. Ruang Lingkup Pekerjaan (Scope Creep/Copy-Paste): Jika dokumen ini adalah khusus TOPOGRAFI, apakah di dalamnya terselip pembahasan lingkup pekerjaan lain seperti Workshop Pemboran (Drilling) atau Perekaman (Recording)? (Cek khususnya Bab 4.4.1 Logistik dan tabel lainnya).
3. Elemen 1 (Komitmen Manajemen & Program Proaktif): Bandingkan frekuensi MWT, Inspeksi Field Camp/Flying Camp, Inspeksi Aktivitas Kru, HOC/PEKA, dan Safety Meeting di Bab 1.2 & Tabel Leading Indicator dengan syarat minimum Lampiran D.1 Elnusa.
4. Elemen 2 (Kebijakan & Sasaran Strategis HSSE): Periksa konsistensi angka Lagging Indicator (jumlah pekerja, hari kerja, jam kerja selamat, KM driven) dan target frekuensi/jumlah pada tabel Leading Indicator (MCU, Induksi, Training, Inspeksi Air Bersih, DCU, dll).
5. Elemen 3 (Organisasi, Kompetensi & Pelatihan): Periksa gambar Struktur Organisasi (jabatan, nama personel, catatan kaki, pengesahan) serta kelengkapan posisi wajib sesuai Lampiran D.2.
6. Elemen 4.1 - 4.3 (HIRADC, Kesehatan & Keselamatan): Periksa kesesuaian program MCU, DCU harian, pengelolaan B3/MSDS, dan persetujuan sumber air bersih.
7. Elemen 4.4 (Logistik & Transportasi): Periksa batas usia maksimal kendaraan roda 4 dan roda >4 (bandingkan angka tahun di HSSE Plan dengan syarat TOR/Lampiran D), spesifikasi rollbar, pre-trip inspection, dan DDT.
8. Elemen 4.5 - 4.7 (Lingkungan, Keamanan & Sosial): Periksa pengelolaan sampah/limbah (warna tempat sampah, limbah B3, grey/black water, aturan larangan pembakaran/zero burning, reklamasi).
9. Elemen 4.8 (Matriks APD & Perlengkapan Kerja): Periksa tabel Matrix APD baris demi baris (warna helm, warna coverall, sepatu, shin-guard, survival kit, P3K, APAR, dll) apakah sudah sesuai dengan standar Lampiran D.3.
10. Elemen 5, 6, 7 & 8 (Prosedur, ERP/Medevac, Pelaporan Insiden & Tinjauan Manajemen): Periksa skenario tanggap darurat, batas waktu pelaporan insiden, penomoran sub-bab yang duplikat/salah, dan kelengkapan lampiran.

FORMAT OUTPUT WAJIB:
Bagian A: Ringkasan Eksekutif & Skor Kepatuhan
Bagian B: Tabel Matriks Temuan Ketidaksesuaian (Hanya yang Melanggar / Tidak Konsisten / Copy-Paste)
Gunakan kolom tabel: | No | Elemen / Halaman HSSE Plan | Persyaratan Dokumen Tender (TOR/IKPP) | Fakta Tertulis di HSSE Plan (Kutip Teks/Gambar) | Kategori Temuan (Fatal / Mayor / Minor) | Rekomendasi Perbaikan |
Bagian C: Daftar Elemen yang Sudah Sesuai (Compliant)
"""

# Eksekusi Audit
if st.button("Jalankan Deep Audit (Gemini Pro)") and tor_files and hsse_files and selected_model:
    with st.spinner(f"Melakukan pemindaian visual & teks halaman demi halaman dengan {selected_model}... (Memakan waktu 1-3 menit)"):
        try:
            # Merakit paket dokumen visual + teks
            contents_parts = [{"text": SYSTEM_PROMPT}]
            contents_parts.extend(prepare_pdf_parts(tor_files, "INSTRUKSI TENDER ELNUSA (TOR/IKPP)"))
            contents_parts.extend(prepare_pdf_parts(hsse_files, "HSSE PLAN VENDOR"))
            
            headers = {'Content-Type': 'application/json'}
            payload = {
                "contents": [{"parts": contents_parts}],
                "generationConfig": {
                    "temperature": 0.0,
                    "topP": 0.95,
                    "maxOutputTokens": 8192
                }
            }
            
            # Antrean model: Utamakan model yang dipilih, lalu fallback ke model Pro/Flash lain yang aktif
            models_to_try = [selected_model] + [
                m for m in available_models 
                if m != selected_model and "2.5" not in m and "1.5" not in m
            ]
            
            berhasil = False
            last_error = ""
            
            for model_name in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={API_KEY}"
                response = requests.post(url, headers=headers, json=payload, timeout=240)
                
                if response.status_code == 200:
                    result_json = response.json()
                    jawaban_ai = result_json['candidates'][0]['content']['parts'][0]['text']
                    st.success(f"Deep Audit Selesai! Dianalisis menggunakan: {model_name} (Mode Visual PDF + Temperature 0.0)")
                    st.markdown(jawaban_ai)
                    berhasil = True
                    break
                else:
                    last_error = f"({response.status_code}) pada {model_name}: {response.text}"
            
            if not berhasil:
                st.error(f"Gagal mengeksekusi model: {last_error}")
                
        except Exception as e:
            st.error(f"Sistem mendeteksi kendala operasional: {e}")
