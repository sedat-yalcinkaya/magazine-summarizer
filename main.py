import os
import re
import requests
import google.generativeai as genai
from pypdf import PdfReader
import io
from fpdf import FPDF
import smtplib
from email.message import EmailMessage
from datetime import datetime

# --- CONFIGURATION ---
API_KEY = os.environ["GEMINI_API_KEY"]
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

# Email Credentials
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

# --- RECIPIENT LIST ---
RECIPIENTS = [
    EMAIL_USER,                 # Send to yourself
    "sedat.yalcinkaya@msn.com",  # CHANGE THIS (Optional)
    "sedat.yacinkaya@gmail.com"    # CHANGE THIS (Optional)
]

# Configure Gemini
genai.configure(api_key=API_KEY)

TARGET_REPO = "Monkfishare/The_Economist"
BASE_PATH = "TE/2026"

# --- THE PUBLISHING ENGINE ---
class EconomistPDF(FPDF):
    def header(self):
        bar_height = 22
        self.set_fill_color(227, 18, 11)
        self.rect(0, 0, self.w, bar_height, 'F')
        self.set_font('Arial', 'B', 24)
        self.set_text_color(255, 255, 255)
        self.set_y(6)
        self.cell(0, 12, 'The Weekly Digest', 0, 0, 'C')
        self.ln(bar_height)

    def footer(self):
        self.set_y(-16)
        self.set_font('Arial', 'I', 10)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    def chapter_title(self, label):
        self.ln(10)
        self.set_font('Arial', 'B', 20)
        self.set_text_color(227, 18, 11)
        self.cell(0, 12, label.upper(), 0, 1, 'L')
        self.set_draw_color(0, 0, 0)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(6)

    def story_headline(self, headline):
        self.set_font('Arial', 'B', 16)
        self.set_text_color(0, 0, 0)
        self.multi_cell(0, 8, headline)
        self.ln(3)

    def story_body(self, body):
        self.set_font('Times', '', 14)
        self.set_text_color(20, 20, 20)
        original_margin = self.l_margin
        self.set_left_margin(original_margin + 5) 
        self.multi_cell(0, 8, body)
        self.set_left_margin(original_margin) 
        self.ln(8)

# --- LOGIC ---

def get_github_headers():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers

def parse_issue_date(text):
    match = re.search(r"20\d{2}-\d{2}-\d{2}", text)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(0), "%Y-%m-%d")
    except ValueError:
        return None

def get_latest_pdf_url():
    api_url = f"https://api.github.com/repos/{TARGET_REPO}/contents/{BASE_PATH}"
    print(f"Checking: {api_url}")
    
    response = requests.get(api_url, headers=get_github_headers())
    if response.status_code != 200: return None, None

    items = response.json()
    folders = [i for i in items if i['type'] == 'dir' and i['name'][0].isdigit()]
    
    if not folders: return None, None

    dated_folders = [(parse_issue_date(i['name']), i['name']) for i in folders]
    dated_folders = [i for i in dated_folders if i[0]]
    if dated_folders:
        latest_folder = max(dated_folders)[1]
    else:
        latest_folder = sorted([i['name'] for i in folders])[-1]
    print(f"Latest issue: {latest_folder}")

    folder_url = f"https://api.github.com/repos/{TARGET_REPO}/contents/{BASE_PATH}/{latest_folder}"
    response = requests.get(folder_url, headers=get_github_headers())
    files = response.json()

    pdf_items = [
        f for f in files
        if f['type'] == 'file' and f['name'].lower().endswith('.pdf')
    ]
    if not pdf_items:
        return None, None

    def pdf_sort_key(item):
        date = parse_issue_date(item['name']) or parse_issue_date(item.get('path', ''))
        if date:
            return (1, date, item['name'])
        return (0, item['name'])

    latest_pdf = max(pdf_items, key=pdf_sort_key)
    raw_url = latest_pdf.get('download_url')
    if not raw_url:
        file_path = latest_pdf['path']
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
    print("Analyzing with Gemini Pro...")
    
    # We use 'gemini-1.5-pro-latest' to fix the 404 error
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    prompt = (
        "You are the Chief Editor at The Economist. Read the full magazine text below.\n"
        "Your job is to produce a structured summary that mirrors the magazine's own sections and article headlines.\n\n"
        "SECTION & HEADLINE RULES:\n"
        "- Use the Table of Contents within the document to identify every section and the article headlines inside each section.\n"
        "- Preserve the exact section names and article headlines from the magazine. Do not invent new ones.\n"
        "- Keep the original section order. Under each section, list every headline in the order it appears.\n\n"
        "SUMMARY RULES:\n"
        "- Under each headline, write a concise summary of the corresponding article.\n"
        "- Priority sections ('The world this week', 'Britain', 'Business', 'Finance & economics', 'Science & technology') should receive 4-6 sentences per article.\n"
        "- Other sections can be shorter (1-3 sentences) but must stay under their correct headline.\n"
        "- If a section or headline appears but has no meaningful content in the issue, include the heading but write 'No significant coverage this issue.'\n\n"
        "FORMATTING:\n"
        "- Use '## ' for Section headers and '### ' for Article headlines.\n"
        "- Do not use bold (**) characters in the body text.\n\n"
        f"DOCUMENT CONTENT:\n{text}"
    )
    
    response = model.generate_content(prompt)
    return response.text

def create_formatted_pdf(text, date_label):
    print("Typesetting PDF...")
    pdf = EconomistPDF(format="A5")
    pdf.set_margins(14, 18, 14)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    
    pdf.set_font("Arial", 'B', 14)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 12, f"Issue Date: {date_label}", ln=True, align='R')
    pdf.ln(6)

    lines = text.split('\n')
    for line in lines:
        clean = line.encode('latin-1', 'replace').decode('latin-1').strip()
        if not clean: continue
        if clean.startswith('## '):
            pdf.chapter_title(clean.replace('##', '').strip())
        elif clean.startswith('### '):
            pdf.story_headline(clean.replace('###', '').strip())
        else:
            pdf.story_body(clean)

    filename = f"Economist_Summary_{date_label}.pdf"
    pdf.output(filename)
    return filename

def send_email(filename):
    # Filter out empty emails just in case
    valid_recipients = [r for r in RECIPIENTS if r and "@" in r]
    
    print(f"Sending email to {len(valid_recipients)} recipients...")
    if not EMAIL_USER or not EMAIL_PASSWORD:
        print("Email credentials missing! Skipping email.")
        return

    msg = EmailMessage()
    msg['Subject'] = f"The Weekly Digest - {filename}"
    msg['From'] = EMAIL_USER
    msg['To'] = ", ".join(valid_recipients)
    msg.set_content("Here is your AI-generated summary of The Economist (Latest Issue).")

    with open(filename, 'rb') as f:
        file_data = f.read()
        file_name = os.path.basename(filename)
    msg.add_attachment(file_data, maintype='application', subtype='pdf', filename=file_name)

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_USER, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print("Emails sent successfully!")
    except Exception as e:
        print(f"Failed to send email: {e}")

def main():
    pdf_url, date_label = get_latest_pdf_url()
    
    if pdf_url:
        pdf_file = download_pdf(pdf_url)
        pdf_text = extract_text_from_pdf(pdf_file)
        if pdf_text:
            summary = summarize_text(pdf_text)
            filename = create_formatted_pdf(summary, date_label)
            print(f"Success! Published: {filename}")
            
            # SEND EMAIL
            send_email(filename)
        else:
            print("PDF Text empty.")
    else:
        print("No PDF found.")

if __name__ == "__main__":
    main()
