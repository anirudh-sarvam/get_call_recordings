import audioop
import io
import os
import urllib.error
import urllib.request
import wave
import zipfile

import streamlit as st
from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
load_dotenv(ENV_PATH)

DEFAULT_ORG_ID = "axisbank.com"
DEFAULT_WORKSPACE_ID = "axisbank-com-defau-3b9581"
DEFAULT_APP_ID = "axis-cc-npa-08fc47d9-5a3e"

MAX_BYTES = 2 * 1024 * 1024
MIN_FRAMERATE = 4000


def fetch_recording(org_id, workspace_id, app_id, interaction_id, api_key):
    url = (
        f"https://apps.sarvam.ai/api/analytics/v1/{org_id}/{workspace_id}"
        f"/{app_id}/recordings/{interaction_id}"
    )
    req = urllib.request.Request(url, headers={"X-API-Key": api_key})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def compress_wav_if_needed(wav_bytes, max_bytes=MAX_BYTES):
    """Downsample + reduce to 8-bit PCM so the file fits under max_bytes.
    Returns (wav_bytes, was_compressed). Uses stdlib wave/audioop only.
    """
    if len(wav_bytes) <= max_bytes:
        return wav_bytes, False

    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        nchannels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)

    duration = nframes / float(framerate)

    if nchannels == 2:
        raw = audioop.tomono(raw, sampwidth, 0.5, 0.5)
        nchannels = 1

    target_data_bytes = int(max_bytes * 0.95) - 44  # leave margin + WAV header size
    target_framerate = max(MIN_FRAMERATE, min(framerate, int(target_data_bytes / duration)))

    resampled, _ = audioop.ratecv(raw, sampwidth, nchannels, framerate, target_framerate, None)
    signed8 = audioop.lin2lin(resampled, sampwidth, 1)
    unsigned8 = audioop.bias(signed8, 1, 128)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(1)
        out.setframerate(target_framerate)
        out.writeframes(unsigned8)

    return buf.getvalue(), True


st.set_page_config(page_title="Samvaad Recording Lookup", page_icon="\U0001F3A7")
st.title("Samvaad Call Recording Lookup")
st.caption("Fetch call recordings by interaction ID via the analytics recordings API.")


def _get_secret(key):
    try:
        return st.secrets.get(key)
    except Exception:
        return None


api_key = os.environ.get("SARVAM_API_KEY") or _get_secret("SARVAM_API_KEY")
if not api_key:
    st.error(
        f"Set SARVAM_API_KEY in {ENV_PATH} (local) or in the app's Secrets (deployed)."
    )
    st.stop()

with st.form("lookup_form"):
    org_id = st.text_input("Org ID", value=DEFAULT_ORG_ID)
    workspace_id = st.text_input("Workspace ID", value=DEFAULT_WORKSPACE_ID)
    app_id = st.text_input("App ID", value=DEFAULT_APP_ID)
    interaction_ids_raw = st.text_area(
        "Interaction ID(s)",
        placeholder="20260710/8f1bbbcb-13:37:26-cf68753c\n20260710/cc94cffe-13:43:07-5bf6ffc7",
        help="One per line. Format: YYYYMMDD/identifier, as shown in the interaction URL.",
        height=120,
    )
    submitted = st.form_submit_button("Fetch recording(s)")

if submitted:
    interaction_ids = [line.strip() for line in interaction_ids_raw.splitlines() if line.strip()]
    if not (org_id and workspace_id and app_id and interaction_ids):
        st.error("Org ID, Workspace ID, App ID, and at least one Interaction ID are required.")
    else:
        results = []
        progress = st.progress(0.0, text="Fetching...")
        for i, interaction_id in enumerate(interaction_ids):
            try:
                audio_bytes = fetch_recording(org_id, workspace_id, app_id, interaction_id, api_key)
                original_size = len(audio_bytes)
                compressed_bytes, was_compressed = compress_wav_if_needed(audio_bytes)
                results.append({
                    "interaction_id": interaction_id,
                    "status": "ok",
                    "audio": compressed_bytes,
                    "original_size": original_size,
                    "final_size": len(compressed_bytes),
                    "compressed": was_compressed,
                })
            except urllib.error.HTTPError as e:
                results.append({
                    "interaction_id": interaction_id,
                    "status": "error",
                    "message": f"HTTP {e.code} — {e.read().decode(errors='replace')[:300]}",
                })
            except Exception as e:
                results.append({"interaction_id": interaction_id, "status": "error", "message": str(e)})
            progress.progress((i + 1) / len(interaction_ids), text=f"Fetched {i + 1}/{len(interaction_ids)}")
        progress.empty()

        ok_results = [r for r in results if r["status"] == "ok"]
        failed_results = [r for r in results if r["status"] != "ok"]

        st.success(f"Fetched {len(ok_results)}/{len(interaction_ids)} recording(s).")

        if len(ok_results) > 1:
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for r in ok_results:
                    fname = r["interaction_id"].replace("/", "_").replace(":", "-") + ".wav"
                    zf.writestr(fname, r["audio"])
            st.download_button(
                "Download all as .zip",
                data=zip_buf.getvalue(),
                file_name="recordings.zip",
                mime="application/zip",
            )

        for r in ok_results:
            file_name = r["interaction_id"].replace("/", "_").replace(":", "-") + ".wav"
            size_note = f"{r['final_size']:,} bytes"
            if r["compressed"]:
                size_note += f" (compressed from {r['original_size']:,} bytes)"
            with st.expander(f"{r['interaction_id']} — {size_note}", expanded=len(ok_results) == 1):
                st.audio(r["audio"], format="audio/wav")
                st.download_button(
                    "Download .wav",
                    data=r["audio"],
                    file_name=file_name,
                    mime="audio/wav",
                    key=f"dl_{r['interaction_id']}",
                )

        for r in failed_results:
            st.error(f"{r['interaction_id']}: {r['message']}")
