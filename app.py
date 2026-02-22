import streamlit as st
import fitz  # PyMuPDF
import google.generativeai as genai
from google.generativeai import GenerativeModel
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, Circle
import matplotlib.patheffects as pe
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

# ─── STYLES ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { background-color: #f0f4f8; }
    .stButton>button {
        background-color: #e74c3c;
        color: white;
        font-weight: bold;
        border-radius: 8px;
        padding: 0.5em 2em;
        font-size: 16px;
    }
    .title-box {
        background: linear-gradient(90deg, #1a1a2e, #16213e);
        color: white;
        padding: 20px 30px;
        border-radius: 12px;
        margin-bottom: 20px;
    }
    .info-box {
        background: #fff;
        border-left: 5px solid #e74c3c;
        padding: 15px;
        border-radius: 6px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

# ─── HEADER ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="title-box">
    <h1 style="margin:0;">📡 FTTH AS-BUILT → SLD Generator</h1>
    <p style="margin:5px 0 0 0; opacity:0.8;">Upload your AS-BUILT FTTH Plan PDF and get an automatic Single Line Diagram</p>
</div>
""", unsafe_allow_html=True)

# ─── API KEY ───────────────────────────────────────────────────────────────────
API_KEY = "AIzaSyBQQ3KYgqlW20xdyQxMRyxEsx6YF1-mVqo"
genai.configure(api_key=API_KEY)

# ─── EXTRACTION PROMPT ─────────────────────────────────────────────────────────
EXTRACT_PROMPT = """
You are an expert FTTH network engineer analyzing a PLDT/Huawei FTTH AS-BUILT plan.

Carefully read this plan and extract the complete network topology.

Return ONLY a valid JSON object with this exact structure (no explanation, no markdown):
{
  "project_name": "area name from the plan",
  "lat": "latitude coordinate of OLT/closure",
  "long": "longitude coordinate of OLT/closure",
  "feeder_cable": "e.g. 72F or 48F",
  "feeder_length": "e.g. 1100m",
  "lcps": [
    {
      "id": "e.g. ALMLP157",
      "span_from_prev": "distance in meters e.g. 83m",
      "fibers_used": "e.g. F1-F8(24FOC) F9-F11(24FOC)",
      "co_locator": "e.g. SMART or DIGITEL or NPT",
      "landmark": "location description e.g. ALONG ALAMINOS-SUAL RD NEAR HOME IDEAS",
      "naps": [
        {
          "id": "e.g. ALMLP157NP1",
          "span": "distance e.g. 30m",
          "fibers_used": "e.g. F1-F8(24FOC) F9-F11(24FOC)",
          "co_locator": "e.g. SMART",
          "landmark": "location description"
        }
      ]
    }
  ]
}

Important rules:
- Extract ALL LCPs (they start with L 8 in the plan)
- Extract ALL NAPs under each LCP (they start with N 8)
- NAP IDs follow pattern: LCPIDNP1, LCPIDNP2... up to NP8
- Include span distances between each node
- Include fiber assignments for each span
- Include co-locators (SMART, DIGITEL, NPT, PLDT etc.)
- Include landmark/address descriptions
- Return ONLY the JSON, nothing else
"""

# ─── SLD DRAWING FUNCTION ──────────────────────────────────────────────────────
def draw_lcp_symbol(ax, x, y, size=0.35):
    """Draw LCP symbol - green circle with L|8"""
    circle = Circle((x, y), size, color='#27ae60', zorder=5)
    ax.add_patch(circle)
    ax.text(x - size*0.3, y, 'L', ha='center', va='center', fontsize=7,
            color='white', fontweight='bold', zorder=6)
    ax.plot([x, x], [y - size*0.8, y + size*0.8], color='white', linewidth=1, zorder=6)
    ax.text(x + size*0.4, y, '8', ha='center', va='center', fontsize=7,
            color='white', fontweight='bold', zorder=6)

def draw_nap_symbol(ax, x, y, size=0.3):
    """Draw NAP symbol - striped circle with N|8"""
    # Outer circle
    circle = Circle((x, y), size, color='#c0392b', zorder=5)
    ax.add_patch(circle)
    # Inner stripes simulation
    for i in range(-2, 3):
        ax.plot([x - size*0.8, x + size*0.8],
                [y + i * size * 0.25, y + i * size * 0.25],
                color='white', linewidth=0.5, alpha=0.4, zorder=6)
    ax.text(x - size*0.3, y, 'N', ha='center', va='center', fontsize=6,
            color='white', fontweight='bold', zorder=7)
    ax.plot([x, x], [y - size*0.7, y + size*0.7], color='white', linewidth=0.8, zorder=7)
    ax.text(x + size*0.4, y, '8', ha='center', va='center', fontsize=6,
            color='white', fontweight='bold', zorder=7)

def draw_closure_symbol(ax, x, y):
    """Draw OLT/closure symbol - rectangle with X"""
    rect = FancyBboxPatch((x-0.4, y-0.25), 0.8, 0.5,
                           boxstyle="round,pad=0.05",
                           linewidth=1.5, edgecolor='black', facecolor='white', zorder=5)
    ax.add_patch(rect)
    ax.plot([x-0.35, x+0.35], [y-0.2, y+0.2], color='black', linewidth=1.5, zorder=6)
    ax.plot([x-0.35, x+0.35], [y+0.2, y-0.2], color='black', linewidth=1.5, zorder=6)

def generate_sld(data):
    """Generate the SLD diagram matching PLDT format"""

    lcps = data.get('lcps', [])
    if not lcps:
        return None

    # ── Layout constants ────────────────────────────────────────────────────────
    ROW_HEIGHT = 4.5        # vertical spacing between LCP rows
    NAP_SPACING = 3.2       # horizontal spacing between NAPs
    LCP_START_X = 3.0       # where first LCP starts horizontally
    LCPS_PER_ROW = 3        # LCPs per row before wrapping

    # Calculate figure size
    max_naps = max((len(lcp.get('naps', [])) for lcp in lcps), default=8)
    num_rows = (len(lcps) + LCPS_PER_ROW - 1) // LCPS_PER_ROW
    fig_width = max(22, LCPS_PER_ROW * max_naps * NAP_SPACING * 0.6 + 4)
    fig_height = max(12, num_rows * ROW_HEIGHT + 4)

    fig, ax = plt.subplots(1, 1, figsize=(fig_width, fig_height))
    ax.set_facecolor('white')
    fig.patch.set_facecolor('white')
    ax.axis('off')

    # ── Title / Header ──────────────────────────────────────────────────────────
    project = data.get('project_name', 'FTTH PLAN')
    lat = data.get('lat', '')
    long = data.get('long', '')
    feeder = data.get('feeder_cable', '72F')
    feeder_len = data.get('feeder_length', '')

    ax.text(0.5, 0.97, project, transform=ax.transAxes,
            fontsize=16, fontweight='bold', ha='center', va='top')
    ax.text(0.02, 0.97, f"LAT: {lat}\nLONG: {long}", transform=ax.transAxes,
            fontsize=8, va='top', family='monospace')

    # ── OLT/Closure at top-left ─────────────────────────────────────────────────
    olt_x, olt_y = 1.0, fig_height - 2.5
    draw_closure_symbol(ax, olt_x, olt_y)
    ax.text(olt_x, olt_y - 0.5, f'{feeder}', ha='center', va='top',
            fontsize=9, fontweight='bold')
    ax.text(olt_x, olt_y - 0.85,
            f'TO BE PROVIDED\nBY FXATOP\n3 CORES\n{feeder_len}',
            ha='center', va='top', fontsize=6.5, color='#333')

    # ── Draw each LCP row ───────────────────────────────────────────────────────
    for lcp_idx, lcp in enumerate(lcps):
        row = lcp_idx // LCPS_PER_ROW
        col = lcp_idx % LCPS_PER_ROW

        # LCP position
        lcp_y = olt_y - 1.5 - row * ROW_HEIGHT
        naps = lcp.get('naps', [])
        row_width = max(len(naps), 1) * NAP_SPACING
        lcp_x = LCP_START_X + col * row_width + (col * 1.5)

        # Draw feeder line from OLT to first LCP in row
        if col == 0:
            ax.annotate('', xy=(lcp_x - 0.4, lcp_y),
                        xytext=(olt_x + 0.4, olt_y if row == 0 else olt_y - row * ROW_HEIGHT),
                        arrowprops=dict(arrowstyle='-', color='black', lw=1.5))

        # Span label above LCP
        span_from = lcp.get('span_from_prev', '')
        fibers = lcp.get('fibers_used', '')
        if span_from:
            ax.text(lcp_x - 1.0, lcp_y + 0.15, fibers,
                    fontsize=5.5, color='#27ae60', ha='center')
            ax.text(lcp_x - 0.6, lcp_y - 0.05, span_from,
                    fontsize=7, ha='center', color='#333')

        # Draw LCP symbol
        draw_lcp_symbol(ax, lcp_x, lcp_y)

        # LCP label above
        ax.text(lcp_x, lcp_y + 0.55, lcp['id'],
                ha='center', va='bottom', fontsize=7.5,
                fontweight='bold', color='black')

        # Co-locator below LCP
        co_loc = lcp.get('co_locator', '')
        landmark = lcp.get('landmark', '')
        ax.text(lcp_x, lcp_y - 0.5, co_loc,
                ha='center', va='top', fontsize=7, fontweight='bold')
        ax.text(lcp_x, lcp_y - 0.75,
                '\n'.join([landmark[i:i+20] for i in range(0, min(len(landmark),60), 20)]),
                ha='center', va='top', fontsize=5, color='#555')

        # ── Draw NAPs ──────────────────────────────────────────────────────────
        nap_start_x = lcp_x + NAP_SPACING * 0.5

        # Horizontal backbone line from LCP
        if naps:
            line_end_x = nap_start_x + (len(naps) - 1) * NAP_SPACING
            ax.plot([lcp_x + 0.3, line_end_x], [lcp_y, lcp_y],
                    color='black', linewidth=1.5, zorder=3)

        for nap_idx, nap in enumerate(naps):
            nap_x = nap_start_x + nap_idx * NAP_SPACING
            nap_y = lcp_y  # same level as LCP

            # Vertical drop line to NAP
            ax.plot([nap_x, nap_x], [lcp_y, nap_y],
                    color='black', linewidth=1.2, zorder=3)

            # NAP fiber label (above line)
            nap_fibers = nap.get('fibers_used', '')
            nap_span = nap.get('span', '')
            ax.text(nap_x + 0.05, nap_y + 0.22, nap_fibers,
                    ha='left', va='bottom', fontsize=5, color='#c0392b')
            ax.text(nap_x + 0.05, nap_y - 0.22, nap_span,
                    ha='left', va='top', fontsize=6.5, color='#333')

            # Draw NAP symbol
            draw_nap_symbol(ax, nap_x, nap_y)

            # NAP ID label (red, above)
            ax.text(nap_x, nap_y + 0.5, nap['id'],
                    ha='center', va='bottom', fontsize=6,
                    color='#c0392b', fontweight='bold')

            # Co-locator and landmark below NAP
            nap_co = nap.get('co_locator', '')
            nap_lm = nap.get('landmark', '')
            ax.text(nap_x, nap_y - 0.5, nap_co,
                    ha='center', va='top', fontsize=6.5, fontweight='bold')
            ax.text(nap_x, nap_y - 0.75,
                    '\n'.join([nap_lm[i:i+18] for i in range(0, min(len(nap_lm),54), 18)]),
                    ha='center', va='top', fontsize=4.5, color='#555')

    # ── Legend ──────────────────────────────────────────────────────────────────
    handles = [
        mpatches.Patch(color='#27ae60', label='LCP (1:8)'),
        mpatches.Patch(color='#c0392b', label='NAP (1:8)'),
        mpatches.Patch(color='black', label='ODN FOC SPAN'),
    ]
    ax.legend(handles=handles, loc='lower right', fontsize=8,
              frameon=True, framealpha=0.9)

    # ── Footer ──────────────────────────────────────────────────────────────────
    ax.text(0.5, 0.01,
            'PLDT FIXED ACCESS ENGINEERING TEAM | Huawei Technologies Phils., Inc.',
            transform=ax.transAxes, fontsize=7, ha='center',
            color='#888', style='italic')

    plt.tight_layout(pad=1.5)
    return fig

# ─── MAIN UI ───────────────────────────────────────────────────────────────────
col1, col2 = st.columns([1, 2])

with col1:
    st.markdown("### 📂 Upload AS-BUILT FTTH Plan")
    uploaded_file = st.file_uploader(
        "Upload your PDF here",
        type="pdf",
        help="Upload the AS-BUILT FTTH span details PDF"
    )

    if uploaded_file:
        st.success(f"✅ File uploaded: {uploaded_file.name}")

        pdf_bytes = uploaded_file.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        st.info(f"📄 Pages detected: {len(doc)}")

        # Show preview of first page
        page = doc[0]
        pix = page.get_pixmap(dpi=120)
        img_bytes = pix.tobytes("png")
        st.image(img_bytes, caption="Page 1 Preview", use_column_width=True)

        generate_btn = st.button("⚡ Generate SLD Now!", use_container_width=True)
    else:
        generate_btn = False
        st.markdown("""
        <div class="info-box">
        <b>How to use:</b><br>
        1. Upload your AS-BUILT FTTH PDF<br>
        2. Click "Generate SLD Now!"<br>
        3. Download your Single Line Diagram
        </div>
        """, unsafe_allow_html=True)

with col2:
    st.markdown("### 📊 Generated Single Line Diagram")

    if uploaded_file and generate_btn:
        with st.spinner("🤖 AI is reading your FTTH plan... please wait..."):
            try:
                # Extract all pages as images
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                all_images = []
                all_text = ""

                for page_num in range(len(doc)):
                    page = doc[page_num]
                    # Get text
                    all_text += page.get_text() + "\n"
                    # Get image
                    pix = page.get_pixmap(dpi=150)
                    img_bytes_page = pix.tobytes("png")
                    img = PIL.Image.open(io.BytesIO(img_bytes_page))
                    all_images.append(img)

                # Auto-detect available model
                available = [m.name for m in genai.list_models() 
                             if 'generateContent' in m.supported_generation_methods]
                # Pick best available flash model
                model_name = next((m for m in available if 'flash' in m), 
                             next((m for m in available if 'pro' in m and 'vision' in m),
                             available[0] if available else "gemini-pro-vision"))
                st.info(f"Using model: {model_name}")
                model = genai.GenerativeModel(model_name)

                content = [EXTRACT_PROMPT]
                content.append(f"\n\nEXTRACTED TEXT FROM PDF:\n{all_text}\n\nNow analyze the images:")
                for img in all_images:
                    content.append(img)

                response = model.generate_content(content)
                raw = response.text.strip()

                # Clean JSON
                raw = re.sub(r'```json', '', raw)
                raw = re.sub(r'```', '', raw)
                raw = raw.strip()

                # Parse JSON
                data = json.loads(raw)

                st.success("✅ AI successfully extracted network topology!")

                # Show extracted data
                with st.expander("🔍 View Extracted Network Data"):
                    st.json(data)

                # Generate SLD
                with st.spinner("🎨 Drawing your SLD..."):
                    fig = generate_sld(data)

                if fig:
                    st.pyplot(fig)

                    # Export buttons
                    col_a, col_b = st.columns(2)

                    # PNG export
                    buf_png = io.BytesIO()
                    fig.savefig(buf_png, format='png', dpi=200,
                                bbox_inches='tight', facecolor='white')
                    col_a.download_button(
                        "⬇️ Download SLD (PNG)",
                        buf_png.getvalue(),
                        file_name="FTTH_SLD.png",
                        mime="image/png",
                        use_container_width=True
                    )

                    # PDF export
                    buf_pdf = io.BytesIO()
                    fig.savefig(buf_pdf, format='pdf',
                                bbox_inches='tight', facecolor='white')
                    col_b.download_button(
                        "⬇️ Download SLD (PDF)",
                        buf_pdf.getvalue(),
                        file_name="FTTH_SLD.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                else:
                    st.error("Could not generate diagram. Please check extracted data.")

            except json.JSONDecodeError as e:
                st.error(f"❌ Could not parse network data from AI response.")
                st.text("Raw AI response:")
                st.text(raw[:2000])
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
                st.text("Please make sure your PDF is a valid FTTH AS-BUILT plan.")
    else:
        st.markdown("""
        <div style="background:#f8f9fa; border-radius:12px; padding:40px; text-align:center; color:#aaa; margin-top:20px;">
            <h2>📡</h2>
            <p>Your SLD will appear here after upload and generation</p>
        </div>
        """, unsafe_allow_html=True)
