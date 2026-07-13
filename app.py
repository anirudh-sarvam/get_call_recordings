import os
import urllib.error
import urllib.request

import streamlit as st
from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
load_dotenv(ENV_PATH)

DEFAULT_ORG_ID = "axisbank.com"
DEFAULT_WORKSPACE_ID = "axisbank-com-defau-3b9581"
DEFAULT_APP_ID = "axis-cc-npa-08fc47d9-5a3e"


def fetch_recording(org_id, workspace_id, app_id, interaction_id, api_key):
    url = (
        f"https://apps.sarvam.ai/api/analytics/v1/{org_id}/{workspace_id}"
        f"/{app_id}/recordings/{interaction_id}"
    )
    req = urllib.request.Request(url, headers={"X-API-Key": api_key})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


st.set_page_config(page_title="Samvaad Recording Lookup", page_icon="\U0001F3A7")
st.title("Samvaad Call Recording Lookup")
st.caption("Fetch a single call recording by interaction ID via the analytics recordings API.")

api_key = os.environ.get("SARVAM_API_KEY")
if not api_key:
    st.error(f"Set SARVAM_API_KEY in {ENV_PATH} before running this app.")
    st.stop()

with st.form("lookup_form"):
    org_id = st.text_input("Org ID", value=DEFAULT_ORG_ID)
    workspace_id = st.text_input("Workspace ID", value=DEFAULT_WORKSPACE_ID)
    app_id = st.text_input("App ID", value=DEFAULT_APP_ID)
    interaction_id = st.text_input(
        "Interaction ID",
        placeholder="20260710/8f1bbbcb-13:37:26-cf68753c",
        help="Format: YYYYMMDD/identifier, as shown in the interaction URL.",
    )
    submitted = st.form_submit_button("Fetch recording")

if submitted:
    if not (org_id and workspace_id and app_id and interaction_id):
        st.error("All fields are required.")
    else:
        try:
            with st.spinner("Fetching recording..."):
                audio_bytes = fetch_recording(org_id, workspace_id, app_id, interaction_id, api_key)
            st.success(f"Fetched recording ({len(audio_bytes):,} bytes).")
            st.audio(audio_bytes, format="audio/wav")
            file_name = interaction_id.replace("/", "_").replace(":", "-") + ".wav"
            st.download_button("Download .wav", data=audio_bytes, file_name=file_name, mime="audio/wav")
        except urllib.error.HTTPError as e:
            st.error(f"Request failed: HTTP {e.code} — {e.read().decode(errors='replace')[:300]}")
        except Exception as e:
            st.error(f"Request failed: {e}")
