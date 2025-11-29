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

# --- THE PUBLISHING ENGINE ---
class EconomistPDF(FPDF):
    def header(self):
        # 1. The "Economist Red" Bar at the top
        self.set_fill_color(227, 18, 11) # Economist Red (#E3120B)
        self.rect(0, 0, 210, 20, 'F') # Red header bar
        
        # 2. White Logo Text
        self.set_font('Arial', 'B', 24)
        self.set_text_color(255, 255, 255)
        self.set_y(5)
        self.cell(0, 10, 'The Weekly Digest', 0, 0, 'C')
        self.ln(20) # Add spacing after header

    def footer(self):
        # Page numbers in gray
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    def chapter_title(self, label):
        # SECTION HEADERS (e.g., "POLITICS")
        self.ln(5)
        self.set_font('Arial', 'B', 18) # Sans-Serif, Bold, Large
        self.set_text_color(227, 18, 11) # Red Text
        self.cell(0, 10, label.upper(), 0, 1, 'L')
        
        # Horizontal Rule (Hairline)
        self.set_draw_color(0, 0, 0)
        self.line(self.get_x(), self.get_y(), 190, self.get_y())
        self.ln(5)

    def story_headline(self, headline):
        # STORY HEADLINES
        self.set_font('Arial', 'B', 14) # Sans-Serif, Bold
        self.set_text_color(0, 0, 0) # Black
        self.multi_cell(0, 6, headline)
        self.ln(2)

    def story_body(self, body):
        # BODY TEXT (Serif, Readable)
        self.set_font('Times', '', 12) # Serif (matches Georgia/Merriweather feel)
        self.set_text_color(20, 20, 20) # Dark Grey (Softer than black)
        
        # We assume 1.4 line height for readability
        # We add a left margin (indent) to make the headline "hang"
        original_margin = self.l_margin
        self.set_left_margin(original_margin + 5) 
        self.multi_cell(0, 6, body)
        self.set_left_margin(original_margin) # Reset margin
        self.ln(6) # Spacing after story

# --- LOGIC ---

def get_github_headers():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers

def get_latest_pdf_url():
    # 1. Find the folder
    api_url = f"https://api.github.com/repos/{TARGET_REPO}/contents/{BASE_PATH}"
    print(f"Checking: {api_url}")
    
    response = requests.get(api_url, headers=get_github_headers())
    if response.status_code != 200: return None, None

    items = response.json()
    folders = [i['name'] for i in items if i['type'] == 'dir' and i['name'][0].isdigit()]
    
    if not folders: return None, None
        
    latest_folder = sorted(folders)[-1]
    print(f"Latest issue: {latest_folder}")

    # 2. Find the PDF
    folder_url = f"https://api.github.com/repos/{TARGET_REPO}/contents/{BASE_PATH}/{latest_folder}"
    response = requests.get(folder_url, headers=get_github_headers())
    files = response.json()

    for file in files:
        if file['name'].lower().endswith('.pdf'):
            file_path = file['path']
            raw_url = f"https://github.com/{TARGET_REPO}/raw/main/{file_path}"
            return raw_url, latest_folder
            
    return None, None

def download_pdf(url):
    print("Downloading PDF...")
    response = requests.get(url, headers=get_github_headers(), stream=True)
    return io.BytesIO(response.content)

def extract_text_from_pdf(pdf_file):
    print("Extracting full text...")
    try:
        reader = PdfReader(pdf_file)
        text = ""
        for page in reader.pages: 
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return ""

def summarize_text(text):
    print("Analyzing with Gemini...")
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    # STRICT FORMATTING PROMPT
    prompt = (
        "You are the Chief Editor at The Economist. Summarize this issue. "
        "IMPORTANT: You must format your output EXACTLY as follows using Markdown tags:\n"
        "1. Use '## ' (Double Hash) for Major Sections (e.g., ## POLITICS, ## BUSINESS).\n"
        "2. Use '### ' (Triple Hash) for Story Headlines.\n"
        "3. Put the story text immediately under the headline.\n"
        "4. Do not use bolding (**) inside the text, just plain text.\n"
        "5. Example Format:\n"
        "## POLITICS\n"
        "### Ukraine Peace Deal\n"
        "President Trump announced progress...\n\n"
        f"DOCUMENT CONTENT:\n{text}"
    )
    
    response = model.generate_content(prompt)
    return response.text

def create_formatted_pdf(text, date_label):
    print("Typesetting PDF...")
    pdf = EconomistPDF()
    pdf.set_margins(20, 20, 20) # Wide margins (approx 0.8 inch) for readability
    pdf.add_page()
    
    # Metadata Title
    pdf.set_font("Arial", 'B', 12)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 10, f"Issue Date: {date_label}", ln=True, align='R')
    pdf.ln(5)

    # Parse the AI Text
    lines = text.split('\n')
    
    for line in lines:
        # Clean special characters that break PDF generation
        clean = line.encode('latin-1', 'replace').decode('latin-1')
        clean = clean.strip()
        
        if not clean:
            continue # Skip empty lines
            
        if clean.startswith('## '):
            # Section Header (Red, Big, Line)
            section_title = clean.replace('##', '').strip()
            pdf.chapter_title(section_title)
            
        elif clean.startswith('### '):
            # Story Headline (Black, Bold)
            headline = clean.replace('###', '').strip()
            pdf.story_headline(headline)
            
        else:
            # Body Text (Serif, Indented)
            pdf.story_body(clean)

    filename = f"Economist_Summary_{date_label}.pdf"
    pdf.output(filename)
    return filename

def main():
    pdf_url, date_label = get_latest_pdf_url()
    
    if pdf_url:
        pdf_file = download_pdf(pdf_url)
        pdf_text = extract_text_from_pdf(pdf_file)
        if pdf_text:
            summary = summarize_text(pdf_text)
            filename = create_formatted_pdf(summary, date_label)
            print(f"Success! Published: {filename}")
        else:
            print("PDF Text empty.")
    else:
        print("No PDF found.")

if __name__ == "__main__":
    main()
