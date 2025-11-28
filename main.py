import os
import requests
import google.generativeai as genai
from pypdf import PdfReader

# --- CONFIGURATION ---
# This line grabs your secret key from the GitHub settings
API_KEY = os.environ["GEMINI_API_KEY"]

# For this tutorial, we are using a sample PDF URL.
# In the future, you can change this to your specific magazine URL.
PDF_URL = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"

# Configure the Gemini "Brain"
genai.configure(api_key=API_KEY)

def download_pdf(url, filename="issue.pdf"):
    print(f"Downloading PDF from {url}...")
    response = requests.get(url)
    if response.status_code == 200:
        with open(filename, "wb") as f:
            f.write(response.content)
        print("Download successful!")
        return filename
    else:
        print("Failed to download PDF.")
        return None

def extract_text_from_pdf(pdf_path):
    print("Reading PDF text...")
    reader = PdfReader(pdf_path)
    text = ""
    # We loop through every page and stick the text together
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

def summarize_text(text):
    print("Sending text to Gemini for summarization...")
    # We use the specific model you requested
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    # This is the prompt we send to the AI
    prompt = f"Please provide a concise summary of the following magazine/document content:\n\n{text}"
    
    response = model.generate_content(prompt)
    return response.text

def main():
    # Step 1: Download
    pdf_file = download_pdf(PDF_URL)
    
    if pdf_file:
        # Step 2: Read Text
        pdf_text = extract_text_from_pdf(pdf_file)
        
        # Step 3: Summarize
        summary = summarize_text(pdf_text)
        print("Summary generated!")
        
        # Step 4: Save to file
        with open("summary.txt", "w") as f:
            f.write(summary)
        print("Summary saved to summary.txt")

if __name__ == "__main__":
    main()
