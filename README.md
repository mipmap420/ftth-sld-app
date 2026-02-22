# 📡 FTTH AS-BUILT → SLD Generator

Automatically generate Single Line Diagrams from FTTH AS-BUILT PDF plans.

## Setup Instructions

### Step 1 - Install Python
Download Python from: https://python.org/downloads
(Version 3.10 or higher)

### Step 2 - Install required packages
Open terminal/command prompt and run:
```
pip install streamlit PyMuPDF google-generativeai matplotlib Pillow
```

### Step 3 - Run the app
```
streamlit run app.py
```

### Step 4 - Use the app
1. Open browser at http://localhost:8501
2. Upload your AS-BUILT FTTH PDF
3. Click "Generate SLD Now!"
4. Download your SLD as PNG or PDF

## Deploy Free Online (Streamlit Cloud)
1. Create account at github.com
2. Upload this folder to a new repository
3. Go to share.streamlit.io
4. Connect your GitHub repo
5. Deploy - get a free public URL!
