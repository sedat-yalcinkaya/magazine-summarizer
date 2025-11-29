import os
import requests
import google.generativeai as genai
from pypdf import PdfReader
import io

# --- CONFIGURATION ---
API_KEY = os.environ["GEMINI_API_KEY"]
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") 

genai.configure(api_key=API_KEY)

TARGET_REPO = "Monkfishare/The_Economist"
BASE_PATH = "TE/2025"

def get_github_headers():
    # This header makes the robot look like a real Chrome browser
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers

def get_latest_pdf_url():
    # 1. List all folders in the 2025 directory
    api_url = f"https://api.github.com/repos/{TARGET_REPO}/contents/{BASE_PATH}"
    print(f"Checking for updates in: {api_url}")
    
    response = requests.get(api_url, headers=get_github_headers())
    
    if response.status_code != 200:
        print(f"GitHub API Error: {response.status_code}")
        return None

    items = response.json()
    folders = [i['name'] for i in items if i['type'] == 'dir']
    
    if not folders:
        print("No folders found!")
        return None
        
    # Sort to find the latest
    latest_folder = sorted(folders)[-1]
    print(f"Latest issue folder found: {latest_folder}")

    # 2. Look inside that folder
    folder_url = f"https://api.github.com/repos/{TARGET_REPO}/contents/{BASE_PATH}/{latest_folder}"
    response = requests.get(folder_url, headers=get_github_headers())
    files = response.json()

    # 3. Find the PDF and build the 'Raw' link (The LFS Fix)
    for file in files:
        if file['name'].lower().endswith('.pdf'):
            print(f"Found PDF: {file['name']}")
            
            # We manually build the link to get the REAL file, not the pointer
            file_path = file['path']
            raw_url = f"https://github.com/{TARGET_REPO}/raw/main/{file_path}"
            print(f"Generated Raw Link: {raw_url}")
            return raw_url
            
    print("No PDF found in the latest folder.")
    return None

def download_pdf(url):
    print(f"Downloading PDF...")
    # Stream the download to handle large files better
    response = requests.get(url, headers=get_github_headers(), stream=True)
    return io.BytesIO(response.content)

def extract_text_from_pdf(pdf_file):
    print("Extracting text...")
    try:
        reader = PdfReader(pdf_file)
        text = ""
        # Read first 30 pages
        for i, page in enumerate(reader.pages[:30]): 
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return ""

def summarize_text(text):
    print("Summarizing with Gemini...")
    model = genai.GenerativeModel("gemini-2.5-flash")
    prompt = (
        "Summarize this magazine issue. "
        "Highlight the 3 biggest stories and list other notable topics.\n\n"
        f"{text}"
    )
    response = model.generate_content(prompt)
    return response.text

def main():
    pdf_url = get_latest_pdf_url()
    
    if pdf_url:
        pdf_file = download_pdf(pdf_url)
        pdf_text = extract_text_from_pdf(pdf_file)
        
        if pdf_text:
            summary = summarize_text(pdf_text)
            with open("summary.txt", "w", encoding="utf-8") as f:
                f.write(f"Source: {pdf_url}\n\n{summary}")
            print("Success! Summary saved.")
        else:
            print("PDF was empty or unreadable.")
    else:
        print("Skipping summarization (No PDF found).")

if __name__ == "__main__":
    main()
