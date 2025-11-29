import os
import requests
import google.generativeai as genai
from pypdf import PdfReader
import io
from fpdf import FPDF
import smtplib
from email.message import EmailMessage

# --- CONFIGURATION ---
API_KEY = os.environ["GEMINI_API_KEY"]
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

# Email Credentials
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

# --- RECIPIENT LIST ---
# Add as many emails as you want here.
# NOTE: Ensure 'EMAIL_USER' is approved in your Amazon Kindle settings!
RECIPIENTS = [
    EMAIL_USER,                 # Send a copy to yourself
    "sedat.yalcinkaya@msn.com",  # Your friend's email
]

# Use PRO model for better reasoning
genai.configure(api_key=API_KEY)

TARGET_REPO = "Monkfishare/The_Economist"
BASE_PATH = "TE/2025"

# --- THE PUBLISHING ENGINE ---
class EconomistPDF(FPDF):
    def header(self):
        self.set_fill_color(227, 18, 11) 
        self.rect(0, 0, 210, 20, 'F')
        self.set_font('Arial', 'B', 24)
        self.set_text_color(255, 255, 255)
        self.set_y(5)
        self.cell(0, 10, 'The Weekly Digest', 0, 0, 'C')
        self.ln(20)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    def chapter_title(self, label):
        self.ln(8)
        self.set_font('Arial', 'B', 18)
        self.set_text_color(227, 18, 11)
        self.cell(0, 10, label.upper(), 0, 1, 'L')
        self.set_draw_color(0, 0, 0)
        self.line(self.get_x(), self.get_y(), 190, self.get_y())
        self.ln(5)

    def story_headline(self, headline):
        self.set_font('Arial', 'B', 14)
        self.set_text_color(0, 0, 0)
        self.multi_cell(0, 6, headline)
        self.ln(2)

    def story_body(self, body):
        self.set_font('Times', '', 12)
        self.set_text_color(20, 20, 20)
        original_margin = self.l_margin
        self.set_left_margin(original_margin + 5) 
        self.multi_cell(0, 6, body)
        self.set_left_margin(original_margin) 
        self.ln(6)

# --- LOGIC ---

def get_github_headers():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers

def get_latest_pdf_url():
    api_url = f"https://api.github.com/repos/{TARGET_REPO}/contents/{BASE_PATH}"
    print(f"Checking: {api_url}")
    
    response = requests.get(api_url, headers=get_github_headers())
    if response.status_code != 200: return None, None

    items = response.json()
    folders = [i['name'] for i in items if i['type'] == 'dir' and i['name'][0].isdigit()]
    
    if not folders: return None, None
        
    latest_folder = sorted(folders)[-1]
    print(f"Latest issue: {latest_folder}")

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
    print("Analyzing with Gemini Pro...")
    model = genai.GenerativeModel("gemini-1.5-pro")
    
    prompt = (
        "You are the Chief Editor at The Economist. Read the text below. "
        "Summarize the issue, but prioritizing these specific sections: "
        "'The World This Week', 'Britain', 'Business', 'Finance and Economics', and 'Science & Technology'.\n\n"
        "INSTRUCTIONS:\n"
        "1. For the PRIORITY SECTIONS listed above: Write detailed, 5-sentence summaries for each story.\n"
        "2. For OTHER sections: Keep them brief (1-2 sentences) or omit if minor.\n"
        "3. FORMATTING: Use '## ' for Section Headers and '### ' for Story Headlines.\n"
        "4. Do not use bold (**) characters in the body text.\n\n"
        f"DOCUMENT CONTENT:\n{text}"
    )
    
    response = model.generate_content(prompt)
    return response.text

def create_formatted_pdf(text, date_label):
    print("Typesetting PDF...")
    pdf = EconomistPDF()
    pdf.set_margins(20, 20, 20)
    pdf.add_page()
    
    pdf.set_font("Arial", 'B', 12)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 10, f"Issue Date: {date_label}", ln=True, align='R')
    pdf.ln(5)

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
    print(f"Sending email to {len(RECIPIENTS)} recipients...")
    if not EMAIL_USER or not EMAIL_PASSWORD:
        print("Email credentials missing! Skipping email.")
        return

    # Create the email
    msg = EmailMessage()
    msg['Subject'] = f"The Weekly Digest - {filename}"
    msg['From'] = EMAIL_USER
    # Join all emails with a comma (required format for email headers)
    msg['To'] = ", ".join(RECIPIENTS) 
    msg.set_content("Here is your AI-generated summary of The Economist (Latest Issue).")

    # Attach the PDF
    with open(filename, 'rb') as f:
        file_data = f.read()
        file_name = os.path.basename(filename)
    msg.add_attachment(file_data, maintype='application', subtype='pdf', filename=file_name)

    try:
        # Connect to Gmail Server
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
