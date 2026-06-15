import json
import time

import requests
import streamlit as st

# ==================================================
# PAGE CONFIG
# ==================================================
st.set_page_config(
    page_title="Document AI",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ==================================================
# SESSION STATE MANAGEMENT
# ==================================================
# This ensures results don't vanish if the user interacts with the page
if "pipeline_result" not in st.session_state:
    st.session_state.pipeline_result = None

# ==================================================
# CUSTOM CSS
# ==================================================
st.markdown(
    """
    <style>
    [data-testid="stHeader"] {
        display:none;
    }
    .main .block-container {
        max-width: 1400px;
        padding-top: 0.75rem;
        padding-bottom: 0rem;
    }
    /* Style the download buttons to look like secondary actions */
    .stDownloadButton button {
        width: 100%;
        border-radius: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ==================================================
# HEADER
# ==================================================
st.title("✨ Document AI")
st.caption("Secure Field Extraction with PII Masking + LLMs")
st.divider()

# ==================================================
# PIPELINE FLOW GRAPHIC
# ==================================================
flow1, flow2, flow3, flow4, flow5 = st.columns(5)

with flow1:
    st.success("📄 Upload")
with flow2:
    st.info("🛡️ PII Mask")
with flow3:
    st.info("🤖 LLM Extract")
with flow4:
    st.info("🔓 Restore")
with flow5:
    st.success("📊 Output")

st.write("")  # Spacer
st.write("")  # Spacer

# ==================================================
# CONFIG AREA & ACTIONS
# ==================================================
cfg1, cfg2, cfg3 = st.columns([1.2, 1.2, 1], gap="large")

with cfg1:
    st.subheader("1. Input Document")
    uploaded_file = st.file_uploader(
        "Upload Financial PDF",
        type=["pdf"],
        label_visibility="collapsed",
    )

    # Auto-clear state if a new file is uploaded
    if uploaded_file and "last_file" not in st.session_state:
        st.session_state.last_file = uploaded_file.name
    elif uploaded_file and st.session_state.last_file != uploaded_file.name:
        st.session_state.pipeline_result = None
        st.session_state.last_file = uploaded_file.name

    st.write("")
    st.markdown("**Instructions**")
    instruction = st.text_area(
        "Instructions",
        value=(
            "Extract the parameters defined in the schema.\n\n"
            "- Extract values exactly as they appear.\n"
            '- Missing strings => "NOT_FOUND"'
        ),
        height=120,
        label_visibility="collapsed",
    )

with cfg2:
    st.subheader("2. Target Schema")
    schema_default = {
        "title": "DocumentExtraction",
        "type": "object",
        "properties": {
            "account_holder_name": {"type": "string"},
            "total_balance": {"type": "number"},
        },
    }
    schema = st.text_area(
        "JSON Schema",
        value=json.dumps(schema_default, indent=2),
        height=275,
        label_visibility="collapsed",
    )

with cfg3:
    st.subheader("3. Execution")

    execute_clicked = st.button(
        "🚀 Run Extraction Pipeline",
        type="primary",
        use_container_width=True,
    )

    st.divider()
    st.markdown("**Pre-Run Summary**")
    st.metric("Status", "Ready to process" if not execute_clicked else "Processing...")

    try:
        schema_dict = json.loads(schema)
        schema_keys = len(schema_dict.get("properties", {}))
    except:
        schema_keys = 0

    st.metric("Target Fields", schema_keys)

st.divider()

# ==================================================
# EXECUTION LOGIC
# ==================================================
if execute_clicked:
    if not uploaded_file:
        st.error("⚠️ Please upload a PDF document first.")
        st.stop()
    if not instruction.strip():
        st.error("⚠️ Please provide extraction instructions.")
        st.stop()
    if schema_keys == 0:
        st.error("⚠️ Invalid JSON Schema.")
        st.stop()

    # Step-by-Step UI Status
    with st.status("Running LangGraph Pipeline...", expanded=True) as status:
        try:
            st.write("📥 Uploading document to server...")
            files = {
                "file": (
                    uploaded_file.name,
                    uploaded_file.getvalue(),
                    "application/pdf",
                )
            }
            data = {"user_instruction": instruction, "json_schema": schema}

            time.sleep(0.5)  # Slight delay for UI effect
            st.write("🛡️ Masking PII entities...")

            # API Call
            response = requests.post(
                "http://localhost:8000/api/process",
                files=files,
                data=data,
                timeout=120,
            )
            response.raise_for_status()

            st.write("🤖 Extracting fields via LLM...")
            result = response.json()

            if result.get("status") != "success":
                status.update(label="Pipeline Failed", state="error", expanded=True)
                st.error(result.get("message", "Unknown error"))
                st.stop()

            st.write("🔓 Restoring unmasked data...")
            time.sleep(0.5)  # Slight delay for UI effect

            # Save to session state
            st.session_state.pipeline_result = result
            status.update(
                label="Pipeline Execution Complete!", state="complete", expanded=False
            )
            st.toast("Extraction Successful!", icon="🎉")

        except requests.exceptions.ConnectionError:
            status.update(label="Connection Error", state="error")
            st.error("Cannot reach FastAPI backend. Is Uvicorn running on port 8000?")
            st.stop()
        except Exception as e:
            status.update(label="System Error", state="error")
            st.error(str(e))
            st.stop()

# ==================================================
# RESULTS DISPLAY (Reads from Session State)
# ==================================================
if st.session_state.pipeline_result:
    result = st.session_state.pipeline_result

    st.success("✅ Results available for review.")

    # KPI Row
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("Fields Extracted", len(result.get("unmasked_json", {})))
    with k2:
        st.metric("Target Keys", schema_keys)
    with k3:
        st.metric("Document", "Processed")
    with k4:
        st.metric("Status", "Success")

    st.divider()

    # Core JSON Results
    st.subheader("📊 Extraction Results")
    res1, res2 = st.columns(2)

    with res1:
        with st.container(border=True):
            st.markdown("### 🔒 LLM Output (Masked)")
            st.json(result.get("extracted_json", {}))

    with res2:
        with st.container(border=True):
            st.markdown("### 🔓 Final Output (Restored)")
            st.json(result.get("unmasked_json", {}))

            # ENHANCEMENT: Download button for the JSON
            json_str = json.dumps(result.get("unmasked_json", {}), indent=2)
            st.download_button(
                label="⬇️ Download Extracted JSON",
                data=json_str,
                file_name=f"extracted_{uploaded_file.name}.json"
                if uploaded_file
                else "extracted.json",
                mime="application/json",
                use_container_width=True,
            )

    st.write("")

    # Technical Expander Details
    with st.expander("🔍 Document Comparison & Analytics", expanded=False):
        doc1, doc2 = st.columns(2)

        with doc1:
            st.markdown("#### Original Markdown")
            st.code(result.get("original_text", ""), language="markdown")

        with doc2:
            st.markdown("#### Anonymized Markdown")
            st.code(result.get("masked_text", ""), language="markdown")

            # ENHANCEMENT: Download button for the masked text
            st.download_button(
                label="⬇️ Download Masked Document",
                data=result.get("masked_text", ""),
                file_name="anonymized_document.md",
                mime="text/markdown",
                use_container_width=True,
            )

        st.divider()
        st.markdown("#### ⚙️ Raw API Response")
        st.json(result)

elif not execute_clicked:
    st.info("Upload a document and click Execute to view extraction results.")
