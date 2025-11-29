import os
import requests
import google.generativeai as genai
from pypdf import PdfReader

# --- CONFIGURATION ---
API_KEY = os.environ["GEMINI_API_KEY"]
genai.configure(api_key=API_KEY)

# The repository we want to read from
TARGET_REPO = "Monkfishare/The_Economist"
BASE_PATH = "TE/2025"

def get_latest_pdf_url():
    """
    Finds the latest weekly folder, then finds the PDF inside it.
    """
    # 1. Get list of all weekly folders
    api_url = f"https://api.github.com/repos/{TARGET_REPO}/contents/{BASE_PATH}"
    print(f"Checking for updates in: {api_url}")
    
    response = requests.get(api_url)
    if response.status_code != 200:
        print(f"Error: Could not list folders. GitHub says: {response.text}")
        return None

    # Filter for only directories (folders) and sort them to get the last one
    items = response.json()
    folders = [i['name'] for i in items if i['type'] == 'dir']
    
    if not folders:
        print("No folders found!")
        return None
        
    # Assuming folders are named by date/issue, the last one is the latest
    latest_folder = sorted(folders)[-1]
    print(f"Latest issue folder found: {latest_folder}")

    # 2. Look inside that specific folder for a PDF
    folder_url = f"https://api.github.com/repos/{TARGET_REPO}/contents/{BASE_PATH}/{latest_folder}"
    response = requests.get(folder_url)
    files = response.json()

    # Find the file that ends with .pdf
    pdf_url = None
    for file in files:
        if file['name'].lower().endswith('.pdf'):
            print(f"Found PDF: {file['name']}")
            pdf_url = file['download_url']
            break
            
    return pdf_url

def download_pdf(url, filename="issue.pdf"):
    print(f"Downloading from {url}...")
    response = requests.get(url)
    with open(filename, "wb") as f:
        f.write(response.content)
    print("Download finished.")
    return filename

def extract_text_from_pdf(pdf_path):
    print("Extracting text...")
    try:
        reader = PdfReader(pdf_path)
        text = ""
        # Limit to first 30 pages to avoid hitting Gemini's limit or timeout
        # You can increase this if needed
        for i, page in enumerate(reader.pages[:30]): 
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return ""

def summarize_text(text):
    print("Analyzing text with Gemini...")
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    # We ask for a structured summary
    prompt = (
        "You are an expert editor. Please summarize the following magazine issue. "
        "Highlight the 3 biggest stories in detail, and then provide a bulleted list "
        "of other notable topics. ignore ads and table of contents.\n\n"
        f"{text}"
    )
    
    response = model.generate_content(prompt)
    return response.text

def main():
    # Step 1: Find the real PDF URL
    pdf_url = get_latest_pdf_url()
    
    if pdf_url:
        # Step 2: Download
        pdf_file = download_pdf(pdf_url)
        
        # Step 3: Read
        pdf_text = extract_text_from_pdf(pdf_file)
        
        if pdf_text:
            # Step 4: Summarize
            summary = summarize_text(pdf_text)
            
            # Step 5: Save
            with open("summary.txt", "w", encoding="utf-8") as f:
                f.write(f"Source: {pdf_url}\n\n")
                f.write(summary)
            print("Success! Summary saved.")
        else:
            print("PDF was empty or unreadable.")
    else:
        print("Could not find a PDF to download.")

if __name__ == "__main__":
    main()
