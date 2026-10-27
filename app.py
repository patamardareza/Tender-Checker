import streamlit as st
import requests
import base64
import io
import pymupdf
from PIL import Image, ImageEnhance, ImageOps

# Konfigurasi Halaman
st.set_page_config(page_title="Tender Checker - Deep Audit Pro", layout="wide")
st.title("Tender Checker: Deep Audit HSSE Plan (Mode Gemini Pro + HD Image Enhancer)")

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
                if "pro" in name.lower() and "vision" not in name.lower():
                    pro_models.append(name)
                else:
                    other_models.append(name)
        pro_models.sort(reverse=True)
        other_models.sort(reverse=True)
        return pro_models + other_models
    return []

# Fungsi Peningkatan Kualitas Gambar (Super-Resolution 3x + Sharpening + Contrast Boost)
def render_enhanced_page_image(page):
    # Render halaman pada resolusi tinggi (3x lipat dari ukuran normal / ~216-300 DPI)
    mat = pymupdf.Matrix(3.0, 3.0)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    
    # Perbaikan kontras otomatis agar tulisan pudar menjadi tegas
    img = ImageOps.autocontrast(img, cutoff=1)
    
    # Peningkatan ketajaman (Sharpness 2.5x) agar teks kecil di dalam bagan terbaca jelas
    enhancer_sharp = ImageEnhance.Sharpness(img)
    img = enhancer_sharp.enhance(2.5)
    
    # Peningkatan kontras tambahan (1.35x)
    enhancer_contrast = ImageEnhance.Contrast(img)
    img = enhancer_contrast.enhance(1.35)
    
    # Simpan ke format PNG berkualitas tinggi
    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

# Fungsi Menyiapkan Paket Dokumen (PDF Utuh + Gambar Halaman HD + Indeks Teks)
def prepare_pdf_parts(pdf_files, label_kategori, enhance_images=False):
    parts = [{"text": f"\n\n=== AWAL DOKUMEN: {label_kategori} ==="}]
    for pdf_file in pdf_files:
        pdf_file.seek(0)
        raw_bytes = pdf_file.read()
        b64_data = base64.b64encode(raw_bytes).decode("utf-8")
        
        # 1. Kirim file PDF secara visual (Native Multimodal)
        parts.append({"text": f"\n[File PDF Utuh: {pdf_file.name}]"})
        parts.append({
            "inline_data": {
                "mime_type": "application/pdf",
                "data": b64_data
            }
        })
        
        # 2. Ekstraksi teks per halaman & Peningkatan Kualitas Gambar (khusus halaman yang memiliki bagan/gambar)
        doc = pymupdf.open(stream=raw_bytes, filetype="pdf")
        for idx, page in enumerate(doc):
            page_num = idx + 1
            page_text = page.get_text()
            parts.append({"text": f"\n--- HALAMAN {page_num} ({pdf_file.name}) ---\n{page_text}"})
            
            # Jika halaman memiliki gambar/bagan (seperti Bagan Struktur Organisasi), lakukan peningkatan HD
            if enhance_images and len(page.get_images(full=True)) > 0:
                enhanced_b64 = render_enhanced_page_image(page)
                parts.append({
                    "text": f"\n[GAMBAR HD DIPERTAJAM - HALAMAN {page_num} ({pdf_file.name}): Baca seluruh teks kecil, nomor telepon (+62...), kode huruf [P]/[F], judul bagan, dan kotak CATATAN di dalam gambar ini dengan sangat teliti!]"
                })
                parts.append({
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": enhanced_b64
                    }
                })
                
    parts.append({"text": f"\n=== AKHIR DOKUMEN: {label_kategori} ===\n"})
    return parts

# Pemilihan Model AI (Prioritas GEMINI PRO)
selected_model = None
available_models = []
if API_KEY:
    available_models = get_pro_models(API_KEY)
    if available_models:
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

# Instruksi Audit Mendalam dengan Aturan Konteks Tender & Pembacaan Gambar HD
SYSTEM_PROMPT = """
Anda adalah Lead Auditor HSSE Senior PT Elnusa Tbk.
Tugas Anda adalah melakukan audit kepatuhan secara menyeluruh, halaman demi halaman, dengan membandingkan DOKUMEN HSSE PLAN VENDOR terhadap DOKUMEN INSTRUKSI TENDER (TOR/IKPP/Lampiran D).

ATURAN LOGIKA & KONTEKS TENDER WAJIB (PENTING AGAR TIDAK SALAH ANALISA):
1. PEMBEDAAN DURASI OPERASIONAL VS MASA BERLAKU KONTRAK:
   - Bedakan secara tegas antara "Durasi Target Pelaksanaan Pekerjaan Operasional Lapangan" (misal: 84 hari untuk Topografi pada TOR Lampiran A) dengan "Jangka Waktu Perjanjian / Masa Berlaku Kontrak Keseluruhan" (misal: 365 hari pada TOR Lampiran C).
   - Angka jangka waktu pekerjaan yang tertulis pada HSSE Plan (baik pada Pendahuluan B. Rencana Kegiatan di Halaman 7 maupun pada Tabel Lagging Indicator No. 1 di Halaman 10) adalah DURASI OPERASIONAL LAPANGAN.
   - Oleh karena itu, WAJIB bandingkan angka durasi di Halaman 7 dan Halaman 10 tersebut hanya terhadap Durasi Target Operasional di TOR Lampiran A (84 hari), JANGAN dibandingkan dengan masa kontrak payung 365 hari di Lampiran C! Gabungkan temuan durasi Halaman 7 dan Halaman 10 menjadi satu poin temuan yang utuh.
2. PEMBACAAN GAMBAR BAGAN STRUKTUR ORGANISASI (HALAMAN 13):
   - Sistem telah melampirkan [GAMBAR HD DIPERTAJAM] untuk halaman yang memuat gambar bagan struktur organisasi.
   - Baca dengan sangat teliti teks di dalam setiap kotak jabatan pada gambar tersebut: perhatikan adanya nomor telepon di dalam kurung `(+628...)` di samping/bawah nama personel, serta simbol huruf seperti `[P]` atau `[F]` di samping jabatan.
   - Baca kotak legenda `CATATAN` di pojok kiri bawah gambar bagan yang menjelaskan arti kode `[P]` (misal: "[P] semua posisi key personil lapangan yang ditunjuk merupakan pegawai tetap PT TUB").
   - DILARANG menyatakan bahwa nomor telepon atau keterangan status pegawai tetap tidak dicantumkan apabila pada gambar bagan sudah tertulis nomor `(+62...)` dan kode `[P]` beserta catatan legendanya! Laporkan hanya elemen yang benar-benar belum ada (misal: jika alamat email dipersyaratkan namun belum tertulis di bagan) atau jika terdapat kesalahan fatal penulisan nama klien pada judul bagan (misal: tertulis "PT PERTAMINA EP" padahal tender ini untuk PT Elnusa Tbk).
3. ANTI-HALUSINASI:
   - Setiap temuan WAJIB menyertakan kutipan teks asli dan NOMOR HALAMAN spesifik baik dari dokumen TOR/IKPP maupun dari dokumen HSSE Plan.

LAKUKAN PEMERIKSAAN MENYELURUH PADA 10 AREA WAJIB BERIKUT:
1. Identitas Perusahaan, Klien & Nama Proyek: Cek salah ketik nama perusahaan, salah nama klien pada judul gambar bagan Struktur Organisasi (misal: tertulis PT Pertamina EP), atau salah nama lokasi/proyek.
2. Ruang Lingkup Pekerjaan (Copy-Paste Lingkup Lain): Jika dokumen ini khusus TOPOGRAFI, cek apakah di dalamnya terselip pembahasan lingkup pekerjaan lain seperti Workshop Pemboran (Drilling) atau Perekaman (Recording) (cek khususnya Bab 4.4.1 Logistik di Halaman 18-19).
3. Elemen 1 (Komitmen Manajemen & Program Proaktif): Bandingkan frekuensi MWT, General TBM, Inspeksi Field Camp/Flying Camp, Inspeksi Aktivitas Kru, HOC/PEKA, dan Safety Meeting di Bab 1.2 & Tabel Leading Indicator dengan syarat minimum Lampiran D.1 Elnusa.
4. Elemen 2 (Kebijakan & Sasaran Strategis HSSE): Periksa konsistensi durasi operasional (Halaman 7 & 10 terhadap target operasional 84 hari di TOR Lampiran A), jumlah pekerja, jam kerja selamat, KM driven, dan target Leading Indicator.
5. Elemen 3 (Organisasi, Kompetensi & Pelatihan): Periksa gambar HD Struktur Organisasi (verifikasi keberadaan nomor telepon `(+62...)`, status pegawai tetap `[P]`, kelengkapan alamat email jika disyaratkan, dan kebenaran nama klien pada judul bagan).
6. Elemen 4.1 - 4.3 (HIRADC, Kesehatan & Keselamatan): Periksa kesesuaian program MCU, DCU harian, pengelolaan B3/MSDS, dan persetujuan sumber air bersih.
7. Elemen 4.4 (Logistik & Transportasi): Periksa batas usia maksimal kendaraan roda 4 dan roda >4 (bandingkan angka tahun di HSSE Plan Halaman 19 dengan syarat TOR Hal. 19), spesifikasi rollbar, pre-trip inspection, dan DDT.
8. Elemen 4.5 - 4.7 (Lingkungan, Keamanan & Sosial): Periksa pengelolaan sampah/limbah (warna tempat sampah, limbah B3, grey/black water, reklamasi).
9. Elemen 4.8 (Matriks APD & Perlengkapan Kerja): Periksa tabel Matrix APD baris demi baris terhadap standar Lampiran D.3.
10. Elemen 5, 6, 7 & 8 (Prosedur, ERP/Medevac, Pelaporan Insiden & Tinjauan Manajemen): Periksa kelengkapan 8 skenario tanggap darurat wajib (Lampiran D.1 Elemen 5.4), batas waktu pelaporan insiden, dan salah ketik (typo).

FORMAT OUTPUT WAJIB:
Bagian A: Ringkasan Eksekutif & Skor Kepatuhan
Bagian B: Tabel Matriks Temuan Ketidaksesuaian (Hanya yang Melanggar / Tidak Konsisten / Copy-Paste)
Gunakan kolom tabel: | No | Elemen / Halaman HSSE Plan | Persyaratan Dokumen Tender (TOR/IKPP) | Fakta Tertulis di HSSE Plan (Kutip Teks/Gambar) | Kategori Temuan (Fatal / Mayor / Minor) | Rekomendasi Perbaikan |
Bagian C: Daftar Elemen yang Sudah Sesuai (Compliant)
"""

# Eksekusi Audit
if st.button("Jalankan Deep Audit (Gemini Pro + HD Vision)") and tor_files and hsse_files and selected_model:
    with st.spinner(f"Mempertajam gambar bagan (HD 3x Zoom) & melakukan audit mendalam dengan {selected_model}..."):
        try:
            # Merakit paket dokumen (aktifkan enhance_images=True khusus untuk HSSE Plan Vendor)
            contents_parts = [{"text": SYSTEM_PROMPT}]
            contents_parts.extend(prepare_pdf_parts(tor_files, "INSTRUKSI TENDER ELNUSA (TOR/IKPP)", enhance_images=False))
            contents_parts.extend(prepare_pdf_parts(hsse_files, "HSSE PLAN VENDOR", enhance_images=True))
            
            headers = {'Content-Type': 'application/json'}
            payload = {
                "contents": [{"parts": contents_parts}],
                "generationConfig": {
                    "temperature": 0.0,
                    "topP": 0.95,
                    "maxOutputTokens": 8192
                }
            }
            
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
                    st.success(f"Deep Audit Selesai! Dianalisis menggunakan: {model_name} (Fitur HD Image Enhancer Aktif)")
                    st.markdown(jawaban_ai)
                    berhasil = True
                    break
                else:
                    last_error = f"({response.status_code}) pada {model_name}: {response.text}"
            
            if not berhasil:
                st.error(f"Gagal mengeksekusi model: {last_error}")
                
        except Exception as e:
            st.error(f"Sistem mendeteksi kendala operasional: {e}")
