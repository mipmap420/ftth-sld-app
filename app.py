import streamlit as st
import fitz  # PyMuPDF
import google.generativeai as genai
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, Circle
import json
import io
import PIL.Image
import re

# ─── PAGE CONFIG ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FTTH AS-BUILT → SLD Generator",
    page_icon="📡",
    layout="wide"
)

# ─── API KEY (Replace with your own if needed) ─────────────────────────────────
API_KEY = "AIzaSyBQQ3KYgqlW20xdyQxMRyxEsx6YF1-mVqo"
genai.configure(api_key=API_KEY)

# ─── EXTRACTION PROMPT ─────────────────────────────────────────────────────────
EXTRACT_PROMPT = """
You are a Senior FTTH Network Design Engineer. Analyze the provided AS-BUILT plan data.

### OBJECTIVE:
Extract the OLT headend, LCP nodes, and their associated NAP nodes into a JSON structure.

### STRICT MAPPING RULES:
1. COORDINATES: The input text includes (x,y) coordinates. Use these to determine which labels belong together.
2. HIERARCHY: NAPs (e.g., ALMLP157NP1) MUST be placed inside the 'naps' list of their parent LCP (e.g., ALMLP157).
3. SPANS: Distances like "83m" or "30m" are spans. Assign them to the node they are physically closest to.
4. CO-LOCATORS: Identify if the pole/node is SMART, NPT, or DIGITEL.

Return ONLY this JSON structure:
{
  "project_name": "Name from title block",
  "lat": "LAT from plan",
  "long": "LONG from plan",
  "feeder_cable": "e.g., 72F",
  "feeder_length": "e.g., 1100m",
  "lcps": [
    {
      "id": "LCP_ID",
      "span_from_prev": "distance",
      "fibers_used": "fiber range",
      "co_locator": "SMART/NPT/DIGITEL",
      "landmark": "Address",
      "naps": [
        {
          "id": "NAP_ID",
          "span": "distance",
          "fibers_used": "fiber range",
          "co_locator": "SMART",
          "landmark": "Address"
        }
      ]
    }
  ]
}
"""

# ─── SLD DRAWING FUNCTIONS ──────────────────────────────────────────────────────
def draw_lcp_symbol(ax, x, y, size=0.35):
    circle = Circle((x, y), size, color='#27ae60', zorder=5)
    ax.add_patch(circle)
    ax.text(x, y, 'L|8', ha='center', va='center', fontsize=7, color='white', fontweight='bold')

def draw_nap_symbol(ax, x, y, size=0.3):
    circle = Circle((x, y), size, color='#c0392b', zorder=5)
    ax.add_patch(circle)
    ax.text(x, y, 'N|8', ha='center', va='center', fontsize=6, color='white', fontweight='bold')

def generate_sld(data):
    lcps = data.get('lcps', [])
    if not lcps: return None

    fig, ax = plt.subplots(figsize=(20, len(lcps) * 4))
    ax.set_facecolor('white')
    ax.axis('off')

    # Header Info
    ax.text(1, 12, f"PROJECT: {data.get('project_name', 'N/A')}", fontsize=14, fontweight='bold')
    ax.text(1, 11.5, f"LAT: {data.get('lat')} | LONG: {data.get('long')}", fontsize=10)
    ax.text(1, 11, f"FEEDER: {data.get('feeder_cable')} - {data.get('feeder_length')}", fontsize=10)

    curr_y = 9
    for lcp in lcps:
        # Draw LCP
        draw_lcp_symbol(ax, 2, curr_y)
        ax.text(2, curr_y + 0.5, lcp['id'], fontweight='bold', ha='center', fontsize=9)
        ax.text(2, curr_y - 0.7, f"{lcp.get('co_locator')}\n{lcp.get('landmark')[:25]}", fontsize=7, ha='center')
        
        # Draw NAPs
        naps = lcp.get('naps', [])
        for i, nap in enumerate(naps):
            nap_x = 5 + (i * 2.5)
            # Connection line
            prev_x = 2 if i == 0 else 5 + ((i-1) * 2.5)
            ax.plot([prev_x + 0.4, nap_x - 0.4], [curr_y, curr_y], 'k-', lw=1, alpha=0.6)
            
            draw_nap_symbol(ax, nap_x, curr_y)
            ax.text(nap_x, curr_y + 0.4, nap['id'], color='#c0392b', fontsize=7, ha='center', fontweight='bold')
            ax.text(nap_x, curr_y - 0.5, f"{nap.get('span')}\n{nap.get('fibers_used')}", fontsize=6, ha='center')

        curr_y -= 4 # Next row

    plt.tight_layout()
    return fig

# ─── MAIN UI ───────────────────────────────────────────────────────────────────
st.title("📡 FTTH AS-BUILT to SLD Generator")
st.write("Upload your PDF and I will generate the Single Line Diagram automatically.")

uploaded_file = st.file_uploader("Upload PDF", type="pdf")

if uploaded_file:
    # 1. Extract text with coordinates
    pdf_bytes = uploaded_file.read()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    
    coord_text = ""
    for page in doc:
        words = page.get_text("words") 
        for w in words:
            # Format: (x, y) Text
            coord_text += f"({round(w[0])},{round(w[1])}){w[4]} "
        coord_text += "\n"

    if st.button("🚀 Generate SLD Now"):
        with st.spinner("AI is analyzing network topology..."):
            try:
                model = genai.GenerativeModel("gemini-1.5-flash")
                response = model.generate_content([EXTRACT_PROMPT, "COORDINATE DATA: " + coord_text])
                
                # Extract JSON from response
                json_str = re.search(r'\{.*\}', response.text, re.DOTALL).group()
                data = json.loads(json_str)

                st.success("Analysis Complete!")
                
                # Show Diagram
                fig = generate_sld(data)
                if fig:
                    st.pyplot(fig)
                
                with st.expander("View Raw Data"):
                    st.json(data)
                    
            except Exception as e:
                st.error(f"Error: {e}")
                st.write("Raw AI Response for troubleshooting:")
                st.write(response.text)
