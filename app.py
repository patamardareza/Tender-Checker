import streamlit as st
import requests
import pymupdf

# Konfigurasi Halaman
st.set_page_config(page_title="Tender Checker - Modul HSSE", layout="wide")
st.title("Tender Checker: Modul HSSE Plan")

# Mengambil API Key
try:
    API_KEY = st.secrets["GEMINI_API_KEY"].strip()
except Exception:
    st.error("Kunci API gagal diakses. Pastikan pengaturan rahasia (Secrets) di Streamlit sudah benar.")
    API_KEY = None

# Fungsi Otomatis Mencari Model yang Aktif di Server Google (ListModels)
@st.cache_data(ttl=3600)
def get_available_models(api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    response = requests.get(url)
    if response.status_code == 200:
        models_data = response.json().get("models", [])
        valid_models = []
        for m in models_data:
            methods = m.get("supportedGenerationMethods", [])
            name = m.get("name", "")
            # Hanya ambil model Gemini yang mendukung pembuatan teks (generateContent)
            if "generateContent" in methods and "gemini" in name.lower():
                valid_models.append(name)
        return valid_models
    return []

# Fungsi Ekstraksi Teks PDF
def extract_text(pdf_files):
    text = ""
    for pdf_file in pdf_files:
        doc = pymupdf.open(stream=pdf_file.read(), filetype="pdf")
        for page in doc:
            text += page.get_text()
    return text

# Menampilkan Pilihan Model yang Tersedia Secara Otomatis
selected_model = None
if API_KEY:
    available_models = get_available_models(API_KEY)
    if available_models:
        # Prioritaskan model generasi terbaru (2.5 atau 2.0 flash) sebagai default
        default_idx = 0
        for i, m in enumerate(available_models):
            if "2.5-flash" in m or "2.0-flash" in m:
                default_idx = i
                break
        selected_model = st.selectbox(
            "Model AI Aktif (Terdeteksi Otomatis dari Server Google):",
            available_models,
            index=default_idx
        )
    else:
        st.error("Gagal memuat daftar model. Pastikan GEMINI_API_KEY Anda valid dan aktif.")

# Antarmuka Unggah Dokumen
col1, col2 = st.columns(2)
with col1:
    st.subheader("1. Dokumen Instruksi (TOR/IKPP Elnusa)")
    tor_files = st.file_uploader("Unggah PDF TOR & Lampiran D", type=["pdf"], accept_multiple_files=True)
with col2:
    st.subheader("2. Dokumen HSSE Plan Vendor")
    hsse_files = st.file_uploader("Unggah PDF HSSE Plan Vendor", type=["pdf"], accept_multiple_files=True)

# Eksekusi Audit
if st.button("Jalankan Audit HSSE") and tor_files and hsse_files and selected_model:
    with st.spinner(f"Mengekstrak dan menganalisis dokumen menggunakan {selected_model}..."):
        try:
            tor_text = extract_text(tor_files)
            hsse_text = extract_text(hsse_files)
            
            prompt = f"""
            Anda adalah Auditor HSSE profesional. Bandingkan Dokumen HSSE Plan Vendor dengan Dokumen Instruksi Tender (TOR).
            Tugas Anda:
            1. Temukan pelanggaran aturan mutlak (misal: batas usia kendaraan, rasio medis, aturan zero burning/pembakaran sampah, frekuensi inspeksi).
            2. Temukan kontradiksi atau indikasi dokumen hasil copy-paste dari proyek lain (misal: nama proyek atau lokasi yang salah).
            
            Tampilkan hasil dalam bentuk tabel Markdown dengan kolom: 
            | Area Temuan | Syarat Tender (TOR) | Fakta di HSSE Plan | Status (Pelanggaran Fatal / Sesuai) |
            
            Dokumen TOR:
            {tor_text}
            
            Dokumen HSSE Plan:
            {hsse_text}
            """
            
            # Menggunakan nama model yang sudah terverifikasi ada di server
            url = f"https://generativelanguage.googleapis.com/v1beta/{selected_model}:generateContent?key={API_KEY}"
            headers = {'Content-Type': 'application/json'}
            payload = {
                "contents": [{"parts": [{"text": prompt}]}]
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=120)
            
            if response.status_code == 200:
                result_json = response.json()
                jawaban_ai = result_json['candidates'][0]['content']['parts'][0]['text']
                st.success("Audit Selesai!")
                st.markdown(jawaban_ai)
            else:
                st.error(f"Koneksi Server Gagal ({response.status_code}): {response.text}")
                
        except Exception as e:
            st.error(f"Sistem mendeteksi kendala operasional: {e}")
