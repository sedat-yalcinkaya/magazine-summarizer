import os
import requests
import google.generativeai as genai
from pypdf import PdfReader
import io
from fpdf import FPDF

# --- CONFIGURATION ---
API_KEY = os.environ["GEMINI_API_KEY"]
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") 

genai.configure(api_key=API_KEY)

TARGET_REPO = "Monkfishare/The_Economist"
BASE_PATH = "TE/2025"

def get_github_headers():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers

def get_latest_pdf_url():
    # 1. List folders
    api_url = f"https://api.github.com/repos/{TARGET_REPO}/contents/{BASE_PATH}"
    print(f"Checking: {api_url}")
    
    response = requests.get(api_url, headers=get_github_headers())
    if response.status_code != 200:
        return None

    items = response.json()
    folders = [i['name'] for i in items if i['type'] == 'dir']
    
    # Filter for dated folders only (start with a number)
    folders = [f for f in folders if f[0].isdigit()]
    
    if not folders:
        return None
        
    latest_folder = sorted(folders)[-1]
    print(f"Latest issue: {latest_folder}")

    # 2. Find PDF
    folder_url = f"https://api.github.com/repos/{TARGET_REPO}/contents/{BASE_PATH}/{latest_folder}"
    response = requests.get(folder_url, headers=get_github_headers())
    files = response.json()

    for file in files:
        if file['name'].lower().endswith('.pdf'):
            # Build Raw Link
            file_path = file['path']
            raw_url = f"https://github.com/{TARGET_REPO}/raw/main/{file_path}"
            return raw_url, latest_folder # Return folder name for the date
            
    return None, None

def download_pdf(url):
    print(f"Downloading PDF...")
    response = requests.get(url, headers=get_github_headers(), stream=True)
    return io.BytesIO(response.content)

def extract_text_from_pdf(pdf_file):
    print("Extracting full text (this may take a moment)...")
    try:
        reader = PdfReader(pdf_file)
        text = ""
        # LIMIT REMOVED: Now reading every single page
        for page in reader.pages: 
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return ""

def summarize_text(text):
    print("Analyzing full document with Gemini...")
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    # Updated Prompt for Structure
    prompt = (
        "You are an expert editor. Read the entire magazine text provided below. "
        "Create a structured summary. "
        "Structure your response exactly like this:\n"
        "1. Start with a main title: '## The Economist Summary'\n"
        "2. For each major section (e.g., Politics, Business, Finance, Science), start with a header like '## Section Name'.\n"
        "3. Under each section, bullet point the key articles and a brief summary of what they say.\n"
        "4. Ignore table of contents and full-page ads.\n"
        "5. Keep the formatting clean.\n\n"
        f"TEXT CONTENT:\n{text}"
    )
    
    # Increase token limit for longer summaries
    response = model.generate_content(prompt)
    return response.text

def create_pdf(text, date_label):
    print("Generating PDF Report...")
    pdf = FPDF()
    pdf.add_page()
    
    # 1. Main Title
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"Weekly Digest: {date_label}", ln=True, align='C')
    pdf.ln(10) # Add space

    # 2. Process the text line by line
    pdf.set_font("Arial", size=12)
    
    lines = text.split('\n')
    
    for line in lines:
        # Strip confusing characters to prevent crashes
        clean_line = line.encode('latin-1', 'replace').decode('latin-1')
        
        if clean_line.strip().startswith('##'):
            # It is a Header -> Make it BOLD and Large
            header_text = clean_line.replace('#', '').strip()
            pdf.set_font("Arial", 'B', 14)
            pdf.ln(5)
            pdf.multi_cell(0, 10, header_text)
            pdf.set_font("Arial", size=12) # Reset to normal
        elif clean_line.strip().startswith('**'):
            # Bold Text -> Make it Bold
            pdf.set_font("Arial", 'B', 12)
            pdf.multi_cell(0, 8, clean_line.replace('*', ''))
            pdf.set_font("Arial", size=12)
        else:
            # Normal Text
            pdf.multi_cell(0, 8, clean_line)

    filename = f"Summary_{date_label}.pdf"
    pdf.output(filename)
    return filename

def main():
    pdf_url, date_label = get_latest_pdf_url()
    
    if pdf_url:
        pdf_file = download_pdf(pdf_url)
        pdf_text = extract_text_from_pdf(pdf_file)
        
        if pdf_text:
            summary = summarize_text(pdf_text)
            
            # Create the PDF
            output_filename = create_pdf(summary, date_label)
            print(f"Success! Saved as {output_filename}")
        else:
            print("PDF was empty.")
    else:
        print("No PDF found.")

if __name__ == "__main__":
    main()
