import streamlit as st
import requests
import pymupdf

# Konfigurasi Halaman
st.set_page_config(page_title="Tender Checker - Modul HSSE", layout="wide")
st.title("Tender Checker: Modul HSSE Plan")

# Mengambil API Key
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    st.error("Kunci API gagal diakses. Pastikan pengaturan rahasia (Secrets) di Streamlit sudah benar.")
    API_KEY = None

# Fungsi Ekstraksi Teks PDF
def extract_text(pdf_files):
    text = ""
    for pdf_file in pdf_files:
        doc = pymupdf.open(stream=pdf_file.read(), filetype="pdf")
        for page in doc:
            text += page.get_text()
    return text

# Antarmuka Unggah Dokumen
col1, col2 = st.columns(2)
with col1:
    st.subheader("1. Dokumen Instruksi (TOR/IKPP Elnusa)")
    tor_files = st.file_uploader("Unggah PDF TOR & Lampiran D", type=["pdf"], accept_multiple_files=True)
with col2:
    st.subheader("2. Dokumen HSSE Plan Vendor")
    hsse_files = st.file_uploader("Unggah PDF HSSE Plan Vendor", type=["pdf"], accept_multiple_files=True)

# Eksekusi Audit
if st.button("Jalankan Audit HSSE") and tor_files and hsse_files and API_KEY:
    with st.spinner("Mengekstrak dan menganalisis kesesuaian dokumen... (Jalur API Langsung)"):
        try:
            tor_text = extract_text(tor_files)
            hsse_text = extract_text(hsse_files)
            
            prompt = f"""
            Anda adalah Auditor HSSE profesional. Bandingkan Dokumen HSSE Plan Vendor dengan Dokumen Instruksi Tender (TOR).
            Tugas Anda:
            1. Temukan pelanggaran aturan mutlak (misal: batas usia kendaraan, rasio medis, aturan zero burning/pembakaran sampah).
            2. Temukan kontradiksi atau indikasi dokumen hasil copy-paste dari proyek lain (misal: nama proyek atau lokasi yang salah).
            
            Tampilkan hasil dalam bentuk tabel Markdown dengan kolom: 
            | Area Temuan | Syarat Tender (TOR) | Fakta di HSSE Plan | Status (Pelanggaran Fatal / Sesuai) |
            
            Dokumen TOR:
            {tor_text}
            
            Dokumen HSSE Plan:
            {hsse_text}
            """
            
            # KOMUNIKASI LANGSUNG KE SERVER GOOGLE (Bypass SDK)
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"
            headers = {'Content-Type': 'application/json'}
            payload = {
                "contents": [{"parts": [{"text": prompt}]}]
            }
            
            response = requests.post(url, headers=headers, json=payload)
            
            # Membaca hasil dari server
            if response.status_code == 200:
                result_json = response.json()
                jawaban_ai = result_json['candidates'][0]['content']['parts'][0]['text']
                st.markdown(jawaban_ai)
            else:
                st.error(f"Koneksi Server Gagal: {response.text}")
                
        except Exception as e:
            st.error(f"Sistem mendeteksi kendala operasional: {e}")
