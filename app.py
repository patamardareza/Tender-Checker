import streamlit as st
import requests
import base64
import io
import pymupdf
from PIL import Image, ImageEnhance, ImageOps

# ==========================================
# KONFIGURASI HALAMAN UTAMA
# ==========================================
st.set_page_config(page_title="TUB Tender Checker", layout="wide")

# Inisialisasi State Navigasi Halaman
if "current_page" not in st.session_state:
    st.session_state.current_page = "login"
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# Fungsi Berpindah Halaman
def navigate_to(page_name):
    st.session_state.current_page = page_name
    st.rerun()

# Fungsi Logout
def logout():
    st.session_state.logged_in = False
    st.session_state.current_page = "login"
    st.rerun()

# ==========================================
# FUNGSI PENDUKUNG MESIN AUDIT & HD VISION
# ==========================================
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
    mat = pymupdf.Matrix(3.0, 3.0)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    img = ImageOps.autocontrast(img, cutoff=1)
    enhancer_sharp = ImageEnhance.Sharpness(img)
    img = enhancer_sharp.enhance(2.5)
    enhancer_contrast = ImageEnhance.Contrast(img)
    img = enhancer_contrast.enhance(1.35)
    buffer = io.BytesIO()
    # Menggunakan JPEG kualitas tinggi agar tetap tajam namun hemat kuota memori saat banyak file diunggah
    img.save(buffer, format="JPEG", quality=90, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

# Fungsi Mengklasifikasikan Dokumen HSSE Plan (Utama) vs Lampiran Elemen (Pendukung)
def is_main_hsse_plan(filename, idx):
    fname_upper = filename.upper()
    if "HSSE" in fname_upper and "PLAN" in fname_upper and "ELEMEN" not in fname_upper:
        return True
    if idx == 0 and "ELEMEN" not in fname_upper and "LAMPIRAN" not in fname_upper:
        return True
    return False

# Fungsi Menyiapkan Paket Dokumen Multi-File dengan Pengaman Kapasitas
def prepare_pdf_parts(pdf_files, label_kategori, is_vendor_side=False):
    parts = [{"text": f"\n\n========================================\nAWAL KELOMPOK DOKUMEN: {label_kategori}\n========================================"}]
    total_inline_bytes = 0
    MAX_INLINE_BYTES = 13 * 1024 * 1024  # Batas aman 13 MB agar bebas error saat unggah banyak file (D.1-D.9 + Elemen)

    for idx, pdf_file in enumerate(pdf_files):
        pdf_file.seek(0)
        raw_bytes = pdf_file.read()
        file_size = len(raw_bytes)

        # Tentukan peran dokumen
        if is_vendor_side:
            peran_dok = "DOKUMEN UTAMA (HSSE PLAN UTAMA - ACUAN UTAMA AUDIT)" if is_main_hsse_plan(pdf_file.name, idx) else "DOKUMEN PENDUKUNG (LAMPIRAN ELEMEN HSSE)"
        else:
            peran_dok = f"DOKUMEN INSTRUKSI TENDER (URUTAN KE-{idx + 1})"

        parts.append({
            "text": f"\n\n>>> MULAI FILE [{idx + 1}]: \"{pdf_file.name}\" | KATEGORI: {peran_dok} <<<"
        })

        # Lampirkan PDF visual utuh jika kapasitas masih di bawah batas aman
        if total_inline_bytes + file_size < MAX_INLINE_BYTES:
            b64_data = base64.b64encode(raw_bytes).decode("utf-8")
            parts.append({
                "inline_data": {
                    "mime_type": "application/pdf",
                    "data": b64_data
                }
            })
            total_inline_bytes += file_size

        # Ekstraksi teks verbatim per halaman + Peningkatan Gambar HD untuk halaman penting/scan
        doc = pymupdf.open(stream=raw_bytes, filetype="pdf")
        for page_idx, page in enumerate(doc):
            page_num = page_idx + 1
            page_text = page.get_text("text")
            parts.append({
                "text": f"\n--- [FILE: {pdf_file.name} | KATEGORI: {peran_dok} | HALAMAN {page_num}] ---\n{page_text}"
            })

            # Aktifkan HD Image Enhancer pada halaman bergambar/bagan atau halaman scan (sertifikat/form) di sisi vendor
            has_images = len(page.get_images(full=True)) > 0
            is_scanned_page = len(page_text.strip()) < 150 and has_images
            if is_vendor_side and (has_images or is_scanned_page):
                if total_inline_bytes < MAX_INLINE_BYTES:
                    enhanced_b64 = render_enhanced_page_image(page)
                    img_bytes_len = len(enhanced_b64) * 3 // 4
                    if total_inline_bytes + img_bytes_len < MAX_INLINE_BYTES:
                        parts.append({
                            "text": f"\n[GAMBAR HD DIPERTAJAM - FILE: {pdf_file.name} - HALAMAN {page_num}: Periksa seluruh detail tulisan kecil, nomor telepon (+62...), kode [P], tanggal masa berlaku sertifikat, nama proyek/perusahaan, dan tanda tangan di halaman ini!]"
                        })
                        parts.append({
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": enhanced_b64
                            }
                        })
                        total_inline_bytes += img_bytes_len

        parts.append({"text": f"\n>>> AKHIR FILE [{idx + 1}]: \"{pdf_file.name}\" <<<\n"})

    parts.append({"text": f"\n========================================\nAKHIR KELOMPOK DOKUMEN: {label_kategori}\n========================================\n"})
    return parts

# ==========================================
# SYSTEM PROMPT: FOKUS DOKUMEN UTAMA vs PENDUKUNG, KESALAHAN MUTLAK & BAHASA SEDERHANA
# ==========================================
SYSTEM_PROMPT = """
Anda adalah Lead Auditor HSSE Senior PT Elnusa Tbk.
Tugas Anda adalah melakukan audit kepatuhan secara teliti, tepat, dan konsisten terhadap dokumen yang diunggah.

PRINSIP UTAMA AUDIT (WAJIB DITAATI 100%):
1. URUTAN & HIERARKI FOKUS AUDIT:
   - FOKUS PERTAMA (UTAMA): Lakukan audit menyeluruh pada **DOKUMEN HSSE PLAN (UTAMA)** terlebih dahulu! Dokumen HSSE Plan Utama adalah acuan utama panitia tender untuk menilai apakah vendor sudah mematuhi instruksi tender (IKPP, TOR, dan Lampiran D.1 s.d D.9).
   - FOKUS KEDUA (PENDUKUNG): Setelah Dokumen HSSE Plan Utama selesai diaudit, periksa **LAMPIRAN ELEMEN (Dokumen Pendukung)** yang diunggah. Pastikan bukti pendukung (seperti prosedur, sertifikat, form laporan, jadwal, daftar peralatan) sinkron dengan klaim di HSSE Plan Utama dan tidak mengandung kesalahan fatal (seperti sertifikat mati/kedaluwarsa, form milik klien lain, atau salah nama proyek akibat copy-paste).

2. HANYA LAPORKAN KESALAHAN MUTLAK (ANTI-SALAH AUDIT / ZERO FALSE POSITIVE):
   - Jangan pernah menyalahkan hal yang sebenarnya sudah benar atau sudah sesuai konteks!
   - ATURAN DURASI PEKERJAAN: Bedakan antara "Durasi Operasional Lapangan" (misal: 84 hari untuk Topografi di TOR Lampiran A) dengan "Masa Berlaku Perjanjian Kontrak Payung" (misal: 365 hari di TOR Lampiran C). Angka durasi di HSSE Plan (Pendahuluan Hal. 7 & Tabel Lagging Indicator Hal. 10) adalah Durasi Operasional Lapangan, sehingga WAJIB dibandingkan dengan target hari operasional di Lampiran A (84 hari), BUKAN dengan 365 hari di Lampiran C!
   - ATURAN GAMBAR BAGAN STRUKTUR ORGANISASI (HALAMAN 13): Periksa gambar HD halaman 13 dengan teliti! Jika di dalam kotak jabatan sudah tertera nomor telepon `(+62...)` dan simbol `[P]` beserta kotak `CATATAN: [P] semua posisi key personil lapangan yang ditunjuk merupakan pegawai tetap PT TUB`, maka nomor telepon dan status pegawai tetap SUDAH TERPENUHI (jangan disalahkan!). Laporkan hanya yang benar-benar salah mutlak pada bagan tersebut (misal: judul bagan salah mencantumkan nama klien "PT PERTAMINA EP" padahal tender PT Elnusa Tbk, atau belum adanya alamat email jika disyaratkan di Lampiran D.1).
   - ATURAN KESESUAIAN LINGKUP LAMPIRAN D (D.1 s.d D.9): Pahami lingkup dokumen HSSE Plan yang sedang diaudit (misal: khusus Topografi). Gunakan Lampiran D.1 s.d D.9 secara cerdas sesuai relevansinya. Jika HSSE Plan Topografi justru membahas "Workshop Pemboran / Chief Mechanic Pemboran / Peralatan Perekaman" (seperti pada Bab 4.4.1 Logistik Hal. 18-19), laporkan itu sebagai kesalahan mutlak akibat *copy-paste* lintas pekerjaan!

3. GAYA BAHASA SEDERHANA & ATURAN KUTIPAN ASLI (VERBATIM):
   - Gunakan bahasa Indonesia yang **sederhana, lugas, dan sangat mudah dipahami** saat menuliskan penjelasan masalah dan rekomendasi perbaikan.
   - NAMUN, untuk **Kutipan Isi Dokumen** (baik kutipan aturan dari IKPP/TOR/Lampiran D maupun kutipan fakta dari HSSE Plan/Lampiran Elemen), Anda **WAJIB menuliskannya di dalam tanda kutip ("...") PERSIS SESUAI ISI DOKUMEN ASLINYA (JANGAN DIUBAH, JANGAN DIPARAon-kan, DAN JANGAN DIKURANGI)**. Cantumkan juga nama file dan nomor halamannya secara spesifik.

DAFTAR PEMERIKSAAN KESALAHAN MUTLAK PADA DOKUMEN HSSE PLAN UTAMA & LAMPIRAN:
- Identitas Proyek, Nama Perusahaan & Nama Klien (Cek cover, teks isi, dan judul gambar bagan Struktur Organisasi).
- Kesalahan Copy-Paste Lintas Lingkup Pekerjaan (Cek Bab 4.4.1 Logistik Hal. 18-19 apakah ada teks pemboran/perekaman di dokumen Topografi).
- Durasi Hari Kerja Operasional (Cek kesesuaian angka hari kerja di Hal. 7 & Hal. 10 terhadap TOR Lampiran A).
- Frekuensi Program Proaktif Manajemen (Cek Bab 1.2 Hal. 9 & Tabel Leading Indicator Hal. 11 terhadap syarat minimum Lampiran D.1 Elemen 1.2, seperti frekuensi General TBM, Inspeksi Field/Flying Camp, Inspeksi Aktivitas Kru).
- Persyaratan Organisasi & Kelengkapan Informasi Bagan (Cek Elemen 3.1.1 Hal. 13 terhadap IKPP, TOR, dan Lampiran D.1/D.2).
- Batas Usia Maksimal Kendaraan & Persyaratan Transportasi (Cek Elemen 4.4.2 Hal. 19 untuk usia kendaraan roda 4 dan roda >4 terhadap TOR Hal. 19 & Lampiran D.4).
- Standar Akomodasi, Makanan, Air Bersih, Pengelolaan Sampah/Limbah & Lingkungan (Cek Elemen 4.2, 4.4.1, 4.5 terhadap Lampiran D.1, D.5, D.8).
- Matriks APD & Perlengkapan Kerja (Cek Tabel Matrix APD Elemen 4.8 Hal. 21-22 baris demi baris terhadap Lampiran D.3, seperti jenis sarung tangan parang bahan Kevlar, warna coverall/helm, dll).
- Rencana Tanggap Darurat / Skenario Emergency (Cek Elemen 5.4 Hal. 23 apakah sudah mencakup seluruh 8 skenario darurat wajib di Lampiran D.1 Elemen 5.4).
- Penomoran Bab/Sub-bab, Salah Ketik (Typo), serta Bukti di Lampiran Elemen (Cek apakah di file Lampiran Elemen terdapat nama proyek fiktif/lama, sertifikat kedaluwarsa, rute evakuasi tidak sesuai lokasi Lampung/Sumsel, atau form milik klien lain).

FORMAT LAPORAN AUDIT WAJIB:

### Ringkasan Eksekutif Hasil Audit
(Tuliskan ringkasan singkat dengan bahasa yang sederhana dan mudah dipahami mengenai hasil pemeriksaan Dokumen HSSE Plan Utama dan Lampiran Pendukung).

### BAGIAN 1: Audit Dokumen HSSE Plan (Utama) — *Fokus Utama Panitia Tender*
*(Tabel ini khusus menampilkan kesalahan mutlak yang ditemukan di dalam Dokumen HSSE Plan Utama dibandingkan dengan IKPP, TOR, dan Lampiran D.1 - D.9)*
| No | Lokasi di HSSE Plan Utama (Bab & Halaman) | Aturan Instruksi Tender (Nama File, Hal & Kutipan Asli) | Isi Tertulis di HSSE Plan Utama (Kutipan Asli Tanpa Diubah) | Penjelasan Masalah (Bahasa Sederhana) | Kategori (Fatal / Mayor / Minor) | Cara Perbaikan |

### BAGIAN 2: Audit Dokumen Lampiran Elemen (Pendukung)
*(Jika user mengunggah file Lampiran Elemen pendukung, tampilkan temuan kesalahan mutlak pada lampiran tersebut di tabel ini. Jika user hanya mengunggah 1 file HSSE Plan Utama tanpa file Lampiran Elemen terpisah, tuliskan pemberitahuan singkat bahwa file Lampiran Elemen pendukung belum diunggah dan periksa daftar rencana lampiran di Hal. 4-6 HSSE Plan Utama).*
| No | Nama File Lampiran & Halaman | Acuan di HSSE Plan Utama / Instruksi Tender | Temuan di Lampiran Elemen (Kutipan Asli Tanpa Diubah) | Penjelasan Masalah (Bahasa Sederhana) | Kategori (Fatal / Mayor / Minor) | Cara Perbaikan |

### BAGIAN 3: Daftar Poin yang Sudah Sesuai (Compliant)
*(Sebutkan dengan bahasa sederhana poin-poin di Dokumen HSSE Plan Utama yang sudah diperiksa dan terbukti BENAR / SESUAI dengan instruksi tender, sehingga tim tidak perlu mengubah bagian tersebut).*
"""


# ==========================================
# LAYER 1: HALAMAN LOGIN
# ==========================================
if st.session_state.current_page == "login":
    col_kiri, col_tengah, col_kanan = st.columns([1, 1.5, 1])
    with col_tengah:
        st.markdown("<h2 style='text-align: center;'>🔒 Portal Internal Tender Checker</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: gray;'>Sistem Audit Kepatuhan Dokumen Tender PT TUB</p>", unsafe_allow_html=True)
        st.divider()
        
        with st.form("login_form"):
            username_input = st.text_input("Username")
            password_input = st.text_input("Password", type="password")
            submit_login = st.form_submit_button("Log In", use_container_width=True)
            
            if submit_login:
                if username_input == "tub_tender_checker" and password_input == "patamarda19":
                    st.session_state.logged_in = True
                    navigate_to("disclaimer")
                else:
                    st.error("Username atau Password salah! Akses ditolak.")


# ==========================================
# LAYER 2: HALAMAN AGREEMENT & DISCLAIMER
# ==========================================
elif st.session_state.current_page == "disclaimer":
    if not st.session_state.logged_in:
        navigate_to("login")
        
    col_kiri, col_tengah, col_kanan = st.columns([0.5, 3, 0.5])
    with col_tengah:
        st.title("⚠️ Agreement & Pemberitahuan (Disclaimer)")
        st.markdown("Harap baca dengan saksama seluruh ketentuan penggunaan sistem internal di bawah ini sebelum melanjutkan:")
        
        st.warning(
            """
            - Website ini di buat secara khusus dan terbatas untuk kebutuhan internal tim manajemen PT TUB. secara khusus program ini diciptakan oleh **Reza Patamarda** sebagai developer tunggal.
            - Dilarang memberi akses ke sembarang orang ataupun memperjual belikan akses website ini ke pihak-pihak di luar organisasi PT TUB dan tanpa pengetahuan developer.
            - Mengunduh, menyebarluaskan, atau memodifikasi materi digital di situs ini secara ilegal merupakan bentuk pelanggaran hukum yang dapat dijerat sanksi pidana berdasarkan UU Hak Cipta dan UU ITE.
            - Program ini sebagai alat bantu (pendukung) untuk proses audit dokumen tender, mengingat program yang dirancang bisa saja melakukan kesalahan atau masih dalam tahap development. QC utama ada di tangan anda!
            """
        )
        
        st.divider()
        setuju = st.checkbox("Saya Mengerti")
        
        col_btn1, col_btn2 = st.columns([1, 4])
        with col_btn1:
            if st.button("OK Lanjut", type="primary", disabled=not setuju, use_container_width=True):
                navigate_to("menu")
        with col_btn2:
            if st.button("Keluar (Logout)"):
                logout()


# ==========================================
# LAYER 3: HALAMAN PILIHAN MODUL (MENU UTAMA)
# ==========================================
elif st.session_state.current_page == "menu":
    if not st.session_state.logged_in:
        navigate_to("login")
        
    st.title("📂 Pilih Modul Pemeriksaan Dokumen Tender")
    st.markdown("Silakan pilih kategori dokumen tender yang ingin Anda periksa:")
    st.divider()
    
    col_opsi1, col_opsi2 = st.columns(2)
    
    with col_opsi1:
        st.subheader("📋 Opsi 1")
        st.info("**Dokumen Administrasi, Teknis & Komersial**\n\nPemeriksaan kelengkapan surat administrasi, spesifikasi teknis peralatan, TKDN, serta penawaran komersial.")
        if st.button("Pilih: Dokumen Administrasi, Teknis & Komersial", use_container_width=True):
            navigate_to("admin_konstruksi")
            
    with col_opsi2:
        st.subheader("🛡️ Opsi 2")
        st.success("**Dokumen HSSE Plan**\n\nAudit mendalam kepatuhan dokumen Rencana K3LL (HSSE Plan) beserta Lampiran Elemen terhadap IKPP, TOR, dan Lampiran D.1 - D.9.")
        if st.button("Pilih: Dokumen HSSE Plan", type="primary", use_container_width=True):
            navigate_to("hsse_checker")
            
    st.divider()
    if st.button("🔒 Keluar (Logout)"):
        logout()


# ==========================================
# LAYER 4A: OPSI 1 (UNDER CONSTRUCTION)
# ==========================================
elif st.session_state.current_page == "admin_konstruksi":
    if not st.session_state.logged_in:
        navigate_to("login")
        
    st.title("📋 Modul Dokumen Administrasi, Teknis & Komersial")
    st.divider()
    st.warning("🚧 **Page under construction, coming soon!**")
    st.write("Modul pengecekan otomatis untuk Dokumen Administrasi, Teknis & Komersial saat ini sedang dalam tahap pengembangan.")
    st.divider()
    
    if st.button("⬅️ Kembali ke Menu Pilihan"):
        navigate_to("menu")


# ==========================================
# LAYER 4B: OPSI 2 (HALAMAN UTAMA HSSE PLAN CHECKER)
# ==========================================
elif st.session_state.current_page == "hsse_checker":
    if not st.session_state.logged_in:
        navigate_to("login")
        
    # Baris Navigasi Atas
    nav_col1, nav_col2, nav_col3 = st.columns([6, 1.5, 1])
    with nav_col1:
        st.title("🛡️ Tender Checker: Deep Audit HSSE Plan")
    with nav_col2:
        if st.button("⬅️ Menu Pilihan", use_container_width=True):
            navigate_to("menu")
    with nav_col3:
        if st.button("🔒 Logout", use_container_width=True):
            logout()
            
    st.divider()

    # Mengambil API Key
    try:
        API_KEY = st.secrets["GEMINI_API_KEY"].strip()
    except Exception:
        st.error("Kunci API gagal diakses. Pastikan pengaturan rahasia (Secrets) di Streamlit sudah benar.")
        API_KEY = None

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

    # Antarmuka Unggah Dokumen dengan Label Sesuai Instruksi
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("1. Dokumen Instruksi Tender (Ground Truth)")
        tor_files = st.file_uploader(
            "Silahkan unggah PDF: IKPP, TOR & Lampiran D (semuanya : D.1 - D.9) secara berurutan", 
            type=["pdf"], 
            accept_multiple_files=True
        )
        if tor_files:
            st.caption(f"✅ Terunggah {len(tor_files)} dokumen instruksi tender:")
            for idx, f in enumerate(tor_files):
                st.caption(f"   {idx + 1}. `{f.name}`")

    with col2:
        st.subheader("2. Dokumen HSSE Plan Vendor (Objek Audit)")
        hsse_files = st.file_uploader(
            "Silahkan unggah PDF HSSE Plan beserta Lampiran Elemen-elemen yang sudah anda buat", 
            type=["pdf"], 
            accept_multiple_files=True
        )
        if hsse_files:
            st.caption(f"✅ Terunggah {len(hsse_files)} dokumen vendor (Otomatis memprioritaskan Dokumen HSSE Plan Utama):")
            for idx, f in enumerate(hsse_files):
                status_dok = "⭐ **[DOKUMEN UTAMA - Fokus Utama Audit]**" if is_main_hsse_plan(f.name, idx) else "📎 *[Lampiran Elemen / Pendukung]*"
                st.caption(f"   {idx + 1}. `{f.name}` — {status_dok}")

    # Eksekusi Audit
    if st.button("Jalankan Deep Audit (Gemini Pro + HD Vision)", type="primary") and tor_files and hsse_files and selected_model:
        with st.spinner(f"Memfokuskan audit pada Dokumen HSSE Plan Utama & memeriksa Lampiran Pendukung dengan {selected_model}..."):
            try:
                contents_parts = [{"text": SYSTEM_PROMPT}]
                contents_parts.extend(prepare_pdf_parts(tor_files, "INSTRUKSI TENDER ELNUSA (IKPP, TOR & LAMPIRAN D.1 - D.9)", is_vendor_side=False))
                contents_parts.extend(prepare_pdf_parts(hsse_files, "DOKUMEN HSSE PLAN UTAMA & LAMPIRAN ELEMEN VENDOR", is_vendor_side=True))
                
                headers = {'Content-Type': 'application/json'}
                payload = {
                    "contents": [{"parts": contents_parts}],
                    "generationConfig": {
                        "temperature": 0.0,
                        "topK": 1,
                        "topP": 0.1,
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
                    response = requests.post(url, headers=headers, json=payload, timeout=300)
                    
                    if response.status_code == 200:
                        result_json = response.json()
                        jawaban_ai = result_json['candidates'][0]['content']['parts'][0]['text']
                        st.success(f"Deep Audit Selesai! Dianalisis secara konsisten menggunakan: {model_name}")
                        st.markdown(jawaban_ai)
                        berhasil = True
                        break
                    else:
                        last_error = f"({response.status_code}) pada {model_name}: {response.text}"
                
                if not berhasil:
                    st.error(f"Gagal mengeksekusi model: {last_error}")
                    
            except Exception as e:
                st.error(f"Sistem mendeteksi kendala operasional: {e}")
