import streamlit as st
from google import genai
import pymupdf

# Konfigurasi Halaman
st.set_page_config(page_title="Tender Checker - Modul HSSE", layout="wide")
st.title("Tender Checker: Modul HSSE Plan")

# Autentikasi API Key dengan SDK Baru
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    client = genai.Client(api_key=API_KEY)
except Exception as e:
    st.error("Kunci API gagal diakses. Pastikan pengaturan rahasia (Secrets) di Streamlit sudah benar.")

# Fungsi Ekstraksi Teks PDF Modern
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
if st.button("Jalankan Audit HSSE") and tor_files and hsse_files:
    with st.spinner("Mengekstrak dan menganalisis kesesuaian dokumen... (Proses ini memakan waktu 1-2 menit)"):
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
            
            # Pemanggilan model dengan SDK terbaru
            response = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=prompt,
            )
            
            st.markdown(response.text)
            
        except Exception as e:
            st.error(f"Sistem mendeteksi kendala operasional: {e}")
