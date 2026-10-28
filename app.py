import streamlit as st
import requests
import base64
import io
import pymupdf
from PIL import Image, ImageEnhance, ImageOps

# ==========================================
# KONFIGURASI HALAMAN UTAMA
# ==========================================
st.set_page_config(page_title="TUB Tender Checker V. 1", layout="wide")

if "current_page" not in st.session_state:
    st.session_state.current_page = "login"
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

def navigate_to(page_name):
    st.session_state.current_page = page_name
    st.rerun()

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
    img.save(buffer, format="JPEG", quality=90, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

def prepare_pdf_parts(pdf_files, label_kategori, is_vendor_side=False):
    parts = [{"text": f"\n\n========================================\nAWAL KELOMPOK DOKUMEN: {label_kategori}\n========================================"}]
    total_inline_bytes = 0
    MAX_INLINE_BYTES = 13 * 1024 * 1024  

    for idx, pdf_file in enumerate(pdf_files):
        pdf_file.seek(0)
        raw_bytes = pdf_file.read()
        file_size = len(raw_bytes)

        peran_dok = "DOKUMEN HSSE PLAN VENDOR" if is_vendor_side else f"DOKUMEN INSTRUKSI TENDER (URUTAN KE-{idx + 1})"

        parts.append({"text": f"\n\n>>> MULAI FILE [{idx + 1}]: \"{pdf_file.name}\" | KATEGORI: {peran_dok} <<<"})

        if total_inline_bytes + file_size < MAX_INLINE_BYTES:
            b64_data = base64.b64encode(raw_bytes).decode("utf-8")
            parts.append({"inline_data": {"mime_type": "application/pdf", "data": b64_data}})
            total_inline_bytes += file_size

        doc = pymupdf.open(stream=raw_bytes, filetype="pdf")
        for page_idx, page in enumerate(doc):
            page_num = page_idx + 1
            page_text = page.get_text("text")
            parts.append({"text": f"\n--- [FILE: {pdf_file.name} | HALAMAN {page_num}] ---\n{page_text}"})

            has_images = len(page.get_images(full=True)) > 0
            is_scanned_page = len(page_text.strip()) < 150 and has_images
            if is_vendor_side and (has_images or is_scanned_page):
                if total_inline_bytes < MAX_INLINE_BYTES:
                    enhanced_b64 = render_enhanced_page_image(page)
                    img_bytes_len = len(enhanced_b64) * 3 // 4
                    if total_inline_bytes + img_bytes_len < MAX_INLINE_BYTES:
                        parts.append({"text": f"\n[GAMBAR HD DIPERTAJAM - FILE: {pdf_file.name} - HALAMAN {page_num}: Periksa seluruh detail tulisan kecil, nomor telepon (+62...), kode [P], judul bagan, dan catatan di halaman ini!]"})
                        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": enhanced_b64}})
                        total_inline_bytes += img_bytes_len

        parts.append({"text": f"\n>>> AKHIR FILE [{idx + 1}]: \"{pdf_file.name}\" <<<\n"})

    parts.append({"text": f"\n========================================\nAKHIR KELOMPOK DOKUMEN: {label_kategori}\n========================================\n"})
    return parts

# ==========================================
# SYSTEM PROMPT: FOKUS AUDIT DOKUMEN UTAMA (HYBRID: DETAIL & ADAPTIF)
# ==========================================
SYSTEM_PROMPT = """
Anda adalah Lead Auditor HSSE Senior PT Elnusa Tbk.
Tugas Anda adalah melakukan audit kepatuhan secara menyeluruh, teliti, dan mendalam dengan membandingkan DOKUMEN HSSE PLAN VENDOR terhadap DOKUMEN INSTRUKSI TENDER (IKPP, TOR, dan Lampiran D.1 - D.4) yang diunggah pada sesi ini.

PRINSIP UTAMA AUDIT (WAJIB DITAATI 100%):
1. EKSTRAKSI ATURAN (HUKUM MUTLAK):
   - Baca dengan teliti dokumen IKPP, TOR, dan Lampiran D.1-D.4. Jadikan dokumen tersebut sebagai "Hukum Mutlak". Tarik semua angka, spesifikasi, dan frekuensi dari sana.
2. HANYA LAPORKAN KESALAHAN MUTLAK (ZERO FALSE POSITIVE):
   - ATURAN DURASI: Bedakan secara tegas antara "Durasi Operasional Lapangan" (di TOR Lampiran A) dengan "Masa Berlaku Kontrak Payung" (di TOR Lampiran C). Angka durasi di HSSE Plan (Halaman 7 & Tabel Lagging Indicator Halaman 10) adalah Durasi Operasional Lapangan. WAJIB bandingkan hanya dengan target durasi operasional lapangan! Gabungkan temuan Hal. 7 dan Hal. 10 menjadi 1 poin temuan.
   - ATURAN GAMBAR BAGAN STRUKTUR ORGANISASI (HALAMAN 13): Jika di dalam kotak jabatan di gambar bagan sudah tertera nomor telepon `(+62...)` dan simbol `[P]` beserta kotak legenda `CATATAN: [P] semua posisi key personil... merupakan pegawai tetap`, maka syarat tersebut SUDAH TERPENUHI (jangan disalahkan!).
   - ATURAN COPY-PASTE (LINGKUP KERJA): Jika HSSE Plan mencantumkan prosedur, jabatan, atau peralatan dari tender lain (misal: tender Topografi tetapi di dokumen vendor tertulis "Workshop Pemboran", "Peralatan Perekaman", atau "Chief Mechanic Pemboran"), laporkan sebagai kesalahan fatal.

3. GAYA BAHASA SEDERHANA & KUTIPAN ASLI (VERBATIM):
   - Gunakan bahasa Indonesia yang **sederhana, lugas, dan sangat mudah dipahami** saat menjelaskan masalah.
   - NAMUN, untuk **Kutipan Isi Dokumen**, Anda **WAJIB menuliskannya di dalam tanda kutip ("...") PERSIS SESUAI ISI DOKUMEN ASLINYA**.

DAFTAR 10 AREA PEMERIKSAAN WAJIB (ANDA DILARANG MELEWATKAN SATUPUN AREA INI):
Lakukan pemindaian wajib pada 10 area ini. Jika ada ketidaksesuaian, masukkan ke dalam tabel temuan:
1. Identitas Proyek & Nama Klien: Pastikan tidak ada salah ketik nama perusahaan/klien di cover, narasi, maupun judul bagan.
2. Lingkungan Lingkup Kerja: Pastikan tidak ada sisa teks copy-paste dari proyek/bidang lain.
3. Durasi Pekerjaan Operasional Lapangan: Cek Hal. 7 dan Hal. 10 terhadap target di TOR (Lampiran A).
4. Program Proaktif Manajemen: Bandingkan frekuensi rapat (General TBM), Inspeksi, MWT di HSSE Plan terhadap syarat minimum pasti di Lampiran D.1.
5. Struktur Organisasi & Personil: Bandingkan posisi kunci di bagan HSSE Plan dengan syarat IKPP/TOR/Lampiran D.2.
6. Program Kesehatan Kerja: Cek kesesuaian prosedur MCU, DCU, dsb.
7. Spesifikasi & Usia Kendaraan: PERIKSA Hal. 19 di HSSE Plan. Cari batas aturan "Usia Kendaraan" dari TOR / Lampiran D.4 (misal: batas usia roda 4 dan roda >4), lalu pastikan angka di HSSE Plan tidak melebihinya.
8. Pengelolaan Lingkungan & Limbah: Cek aturan sampah dan zero burning.
9. Matriks APD (Alat Pelindung Diri): PERIKSA Hal. 21-22 di HSSE Plan secara baris demi baris! Cocokkan spesifikasinya dengan Lampiran D.3 (misal: pastikan jenis sarung tangan untuk Rintis Bridging, warna coverall, atau warna helm sudah sama persis dengan instruksi).
10. Skenario Tanggap Darurat / Emergency: PERIKSA Hal. 23 di HSSE Plan. Hitung dan cocokkan kelengkapan daftar skenario darurat dengan syarat wajib di Lampiran D.1 (misal: apakah sudah mencakup 8 skenario wajib seperti Man Lost, dll).

FORMAT LAPORAN AUDIT WAJIB:

### Ringkasan Eksekutif Hasil Audit
(Tuliskan ringkasan singkat dengan bahasa sederhana mengenai hasil pemeriksaan Dokumen HSSE Plan terhadap instruksi tender).

### Tabel Temuan Ketidaksesuaian (Pelanggaran / Ketidakkonsistenan)
*(Tabel ini HANYA menampilkan kesalahan mutlak yang ditemukan di dalam Dokumen HSSE Plan dibandingkan dengan aturan HSSE di IKPP, TOR, dan Lampiran D.1-D.4)*
| No | Lokasi di HSSE Plan (Bab & Halaman) | Syarat Instruksi Tender (Nama File, Hal & Kutipan Asli) | Isi Tertulis di HSSE Plan (Kutipan Asli Tanpa Diubah) | Penjelasan Masalah (Bahasa Sederhana) | Kategori (Fatal / Mayor / Minor) | Cara Perbaikan |

### Daftar Poin yang Sudah Sesuai (Compliant)
*(Sebutkan dengan bahasa sederhana area-area kritis di Dokumen HSSE Plan yang sudah terbukti BENAR / SESUAI dengan syarat HSSE di instruksi tender).*
"""

# ==========================================
# LAYER 1: HALAMAN LOGIN
# ==========================================
if st.session_state.current_page == "login":
    col_kiri, col_tengah, col_kanan = st.columns([1, 1.5, 1])
    with col_tengah:
        st.markdown("<h2 style='text-align: center;'>🔒 Portal Internal TUB Tender Checker V. 1</h2>", unsafe_allow_html=True)
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
        
    st.title("📂 Pilih Modul Pemeriksaan Dokumen Tender - V. 1")
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
        st.success("**Dokumen HSSE Plan**\n\nAudit mendalam kepatuhan dokumen Rencana K3LL (HSSE Plan) terhadap IKPP, TOR, dan Lampiran D.1 - D.4.")
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
        
    nav_col1, nav_col2, nav_col3 = st.columns([6, 1.5, 1])
    with nav_col1:
        st.title("🛡️ Tender Checker V. 1: Deep Audit HSSE Plan")
    with nav_col2:
        if st.button("⬅️ Menu Pilihan", use_container_width=True):
            navigate_to("menu")
    with nav_col3:
        if st.button("🔒 Logout", use_container_width=True):
            logout()
            
    st.divider()

    try:
        API_KEY = st.secrets["GEMINI_API_KEY"].strip()
    except Exception:
        st.error("Kunci API gagal diakses. Pastikan pengaturan rahasia (Secrets) di Streamlit sudah benar.")
        API_KEY = None

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

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("1. Dokumen Instruksi Tender (Ground Truth)")
        tor_files = st.file_uploader(
            "Silahkan unggah PDF: IKPP, TOR & Lampiran D.1, D.2, D.3 & D.4 secara berurutan", 
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
            "Silahkan unggah PDF HSSE Plan utama", 
            type=["pdf"], 
            accept_multiple_files=True
        )
        if hsse_files:
            st.caption(f"✅ Terunggah {len(hsse_files)} dokumen vendor:")
            for idx, f in enumerate(hsse_files):
                st.caption(f"   {idx + 1}. `{f.name}`")

    if st.button("Jalankan Deep Audit (Gemini Pro + HD Vision)", type="primary") and tor_files and hsse_files and selected_model:
        with st.spinner(f"Melakukan ekstraksi & audit cerdas menggunakan {selected_model}..."):
            try:
                contents_parts = [{"text": SYSTEM_PROMPT}]
                contents_parts.extend(prepare_pdf_parts(tor_files, "INSTRUKSI TENDER ELNUSA (IKPP, TOR, & LAMPIRAN D)", is_vendor_side=False))
                contents_parts.extend(prepare_pdf_parts(hsse_files, "DOKUMEN HSSE PLAN VENDOR", is_vendor_side=True))
                
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
