import streamlit as st
import fitz  # PyMuPDF
import google.generativeai as genai
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Circle
import json
import io
import re

# ─── PAGE CONFIG ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FTTH SLD Generator Pro",
    page_icon="📡",
    layout="wide"
)

# ─── API KEY ───────────────────────────────────────────────────────────────────
API_KEY = "AIzaSyBQQ3KYgqlW20xdyQxMRyxEsx6YF1-mVqo"
genai.configure(api_key=API_KEY)

# ─── EXTRACTION PROMPT ─────────────────────────────────────────────────────────
EXTRACT_PROMPT = """
You are an expert FTTH Network Auditor. Analyze the provided text coordinates from an AS-BUILT plan.

### OBJECTIVE:
Extract the OLT (Headend) details, LCP nodes, and their connected NAP nodes into a clean JSON structure.

### ACCURACY RULES:
1. GROUPING: NAPs (e.g., ALMLP157NP1) MUST be placed inside the 'naps' list of the correct LCP (ALMLP157). 
2. SPANS: Distances like "83m" or "30m" are crucial. Link them to the node closest to them.
3. CO-LOCATORS: Identify if the pole/node is SMART, NPT, or DIGITEL.

Return ONLY JSON:
{
  "project_name": "Project Name",
  "lat": "LAT",
  "long": "LONG",
  "feeder_cable": "e.g. 72F",
  "feeder_length": "e.g. 1100m",
  "lcps": [
    {
      "id": "LCP_ID",
      "span_from_prev": "XXm",
      "fibers_used": "fiber range",
      "co_locator": "SMART/NPT/DIGITEL",
      "landmark": "Address",
      "naps": [
        {
          "id": "NAP_ID",
          "span": "XXm",
          "fibers_used": "FX-FX",
          "co_locator": "SMART",
          "landmark": "Address"
        }
      ]
    }
  ]
}
"""

# ─── SLD DRAWING FUNCTIONS ──────────────────────────────────────────────────────
def generate_sld(data):
    lcps = data.get('lcps', [])
    if not lcps: return None

    fig, ax = plt.subplots(figsize=(22, len(lcps) * 4.5))
    ax.set_facecolor('#ffffff')
    ax.axis('off')

    plt.text(0.5, 1, f"PROJECT: {data.get('project_name', 'UNKNOWN').upper()}", transform=ax.transAxes, fontsize=16, fontweight='bold', ha='center')
    plt.text(0.5, 0.97, f"LAT: {data.get('lat')} | LONG: {data.get('long')} | FEEDER: {data.get('feeder_cable')} ({data.get('feeder_length')})", transform=ax.transAxes, fontsize=11, ha='center')

    curr_y = 10
    for lcp in lcps:
        lcp_x = 2
        circle = Circle((lcp_x, curr_y), 0.4, color='#27ae60', zorder=5)
        ax.add_patch(circle)
        ax.text(lcp_x, curr_y, 'L|8', ha='center', va='center', color='white', fontweight='bold', fontsize=9)
        ax.text(lcp_x, curr_y + 0.6, lcp['id'], fontweight='bold', ha='center', fontsize=10)
        ax.text(lcp_x, curr_y - 0.8, f"{lcp.get('co_locator')}\n{lcp.get('landmark')[:30]}", fontsize=8, ha='center', color='#555')

        naps = lcp.get('naps', [])
        for i, nap in enumerate(naps):
            nap_x = 6 + (i * 3.5)
            prev_x = lcp_x if i == 0 else 6 + ((i-1) * 3.5)
            ax.plot([prev_x + 0.4, nap_x - 0.4], [curr_y, curr_y], color='#34495e', lw=1.5)
            
            nap_circle = Circle((nap_x, curr_y), 0.35, color='#c0392b', zorder=5)
            ax.add_patch(nap_circle)
            ax.text(nap_x, curr_y, 'N|8', ha='center', va='center', color='white', fontweight='bold', fontsize=8)
            ax.text(nap_x, curr_y + 0.5, nap['id'], color='#c0392b', fontsize=8, ha='center', fontweight='bold')
            ax.text(nap_x, curr_y - 0.7, f"SPAN: {nap.get('span')}\n{nap.get('fibers_used')}", fontsize=7, ha='center')
        curr_y -= 5

    plt.tight_layout()
    return fig

# ─── MAIN APP INTERFACE ────────────────────────────────────────────────────────
st.title("📡 FTTH SLD Generator (v2.1)")
uploaded_file = st.file_uploader("Upload PDF Plan", type="pdf")

if uploaded_file:
    doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    coord_text = ""
    for page in doc:
        words = page.get_text("words") 
        for w in words:
            coord_text += f"({round(w[0])},{round(w[1])}){w[4]} "
        coord_text += "\n"

    if st.button("🚀 Generate Diagram"):
        with st.spinner("AI is finding a compatible model and analyzing layout..."):
            try:
                # FIX: Automatically find the best available model
                available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                target_model = next((m for m in available_models if 'gemini-1.5-flash' in m), 
                               available_models[0] if available_models else None)
                
                if not target_model:
                    st.error("No compatible AI models found in your project.")
                else:
                    model = genai.GenerativeModel(target_model)
                    response = model.generate_content([EXTRACT_PROMPT, "DATA: " + coord_text])
                    
                    json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
                    if json_match:
                        data = json.loads(json_match.group())
                        st.success(f"Successfully used model: {target_model}")
                        fig = generate_sld(data)
                        if fig:
                            st.pyplot(fig)
                    else:
                        st.error("AI output was not valid JSON.")
                        st.text(response.text)
            
            except Exception as e:
                st.error(f"Error: {e}")
