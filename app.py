import os
import re
import glob
import time
import wave
import base64
import asyncio
import subprocess
import streamlit as st
import edge_tts
from google import genai
from google.genai import types

st.set_page_config(page_title="Multimodal Video Hook Generator", layout="wide")
st.title("🎬 Full-Video Gemini Analysis & Voiceover Pipeline")

# Sidebar Configuration
st.sidebar.header("⚙️ Settings")
gemini_api_key = st.sidebar.text_input("Gemini API Key", type="password", help="Get a key from Google AI Studio")

# Integrated Voice Roster (Hindi, Marathi, English)
VOICE_OPTIONS = {
    "Gemini - Kore (Hindi / Energetic)": {"engine": "gemini", "code": "Kore", "lang": "Hindi", "script_type": "Devanagari script"},
    "Gemini - Kore (Marathi / Energetic)": {"engine": "gemini", "code": "Kore", "lang": "Marathi", "script_type": "Devanagari script"},
    "Gemini - Kore (English)": {"engine": "gemini", "code": "Kore", "lang": "English", "script_type": "English text"},
    "Gemini - Aoede (Hindi / Deep)": {"engine": "gemini", "code": "Aoede", "lang": "Hindi", "script_type": "Devanagari script"},
    "Gemini - Fenrir (Hindi / Bold)": {"engine": "gemini", "code": "Fenrir", "lang": "Hindi", "script_type": "Devanagari script"},
    "Gemini - Fenrir (English / Viral)": {"engine": "gemini", "code": "Fenrir", "lang": "English", "script_type": "English text"},
    "Gemini - Charon (Hindi)": {"engine": "gemini", "code": "Charon", "lang": "Hindi", "script_type": "Devanagari script"},
    "Gemini - Charon (Marathi)": {"engine": "gemini", "code": "Charon", "lang": "Marathi", "script_type": "Devanagari script"},
    "Gemini - Charon (English)": {"engine": "gemini", "code": "Charon", "lang": "English", "script_type": "English text"},
    "Gemini - Puck (Hindi)": {"engine": "gemini", "code": "Puck", "lang": "Hindi", "script_type": "Devanagari script"},
    "Gemini - Puck (Marathi)": {"engine": "gemini", "code": "Puck", "lang": "Marathi", "script_type": "Devanagari script"},
    "Edge - Hindi Male (Madhur)": {"engine": "edge", "code": "hi-IN-MadhurNeural", "lang": "Hindi", "script_type": "Devanagari script"},
    "Edge - Hindi Female (Swara)": {"engine": "edge", "code": "hi-IN-SwaraNeural", "lang": "Hindi", "script_type": "Devanagari script"},
    "Edge - Marathi Female (Aarohi)": {"engine": "edge", "code": "mr-IN-AarohiNeural", "lang": "Marathi", "script_type": "Devanagari script"},
    "Edge - Marathi Male (Manohar)": {"engine": "edge", "code": "mr-IN-ManoharNeural", "lang": "Marathi", "script_type": "Devanagari script"},
    "Edge - English Male (Guy)": {"engine": "edge", "code": "en-US-GuyNeural", "lang": "English", "script_type": "English text"},
}

selected_voice_label = st.sidebar.selectbox("🎙️ Voice Model & Language", list(VOICE_OPTIONS.keys()))
selected_voice_info = VOICE_OPTIONS[selected_voice_label]

script_style = st.sidebar.selectbox(
    "🎨 Hook / Script Style",
    [
        "Sidhu Paaji Commentary (Oye Guru! Thoko Taali)",
        "Soul Lines Paaji Mode (Hook-Hero-Roast-Closer)",
        "High-Dopamine Viral Opening", 
        "Viral Explanation Mode (Hook-Scoop-Twist)", 
        "Cinematic Storytelling", 
        "Humorous & Punchy", 
        "Explainer Hook"
    ]
)


def cleanup_temp_files():
    patterns = ["temp_input.mp4", "generated_voice.*", "fitted_voice.wav", "output_hooked.mp4"]
    for pattern in patterns:
        for file in glob.glob(pattern):
            try:
                os.remove(file)
            except OSError:
                pass


def get_file_duration(file_path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(res.stdout.strip())


def get_file_state_str(file_obj):
    state = getattr(file_obj, "state", None)
    if hasattr(state, "name"):
        return state.name
    return str(state).upper()


def build_atempo_filter(tempo: float) -> str:
    """Safely chains FFmpeg atempo filters for any ratio between 0.5x and 3.0x."""
    tempo = max(0.5, min(tempo, 3.0))
    filters = []
    while tempo > 2.0:
        filters.append("atempo=2.0")
        tempo /= 2.0
    while tempo < 0.5:
        filters.append("atempo=0.5")
        tempo /= 0.5
    filters.append(f"atempo={tempo:.4f}")
    return ",".join(filters)


def save_gemini_audio_properly(raw_bytes: bytes, output_wav_path: str):
    if isinstance(raw_bytes, str):
        raw_bytes = base64.b64decode(raw_bytes)

    if raw_bytes[:4] == b"RIFF":
        with open(output_wav_path, "wb") as f:
            f.write(raw_bytes)
    else:
        with wave.open(output_wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(raw_bytes)


def generate_content_with_retry(client, model, contents, config=None, max_retries=3):
    delay = 2.0
    transient_indicators = [
        "429", "RESOURCE_EXHAUSTED", "Quota", 
        "503", "UNAVAILABLE", "500", "502", "504", 
        "high demand", "Overloaded", "try again later"
    ]
    for attempt in range(max_retries):
        try:
            return client.models.generate_content(model=model, contents=contents, config=config)
        except Exception as e:
            err_msg = str(e)
            if any(indicator in err_msg for indicator in transient_indicators):
                if attempt < max_retries - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
            raise e


def synthesize_gemini_voice(client, text: str, voice_name: str, output_wav_path: str):
    # Method 1: Interactions API
    if hasattr(client, "interactions"):
        for tts_model in ["gemini-3.8-flash-tts", "gemini-3.1-flash-tts-preview"]:
            try:
                interaction = client.interactions.create(
                    model=tts_model,
                    input=[{
                        "type": "user_input",
                        "content": [{"type": "text", "text": text}]
                    }],
                    response_format={"type": "audio"},
                    generation_config={"speech_config": [{"voice": voice_name}]}
                )
                audio_data = None
                if hasattr(interaction, "output_audio") and interaction.output_audio:
                    audio_data = interaction.output_audio.data
                elif hasattr(interaction, "steps") and interaction.steps:
                    for step in interaction.steps:
                        for item in getattr(step, "content", []):
                            if getattr(item, "data", None):
                                audio_data = item.data
                                break

                if audio_data:
                    save_gemini_audio_properly(audio_data, output_wav_path)
                    return
            except Exception:
                continue

    # Method 2: v1beta generate_content API
    last_error = None
    for tts_model in ["gemini-3.8-flash-tts", "gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"]:
        try:
            audio_response = generate_content_with_retry(
                client,
                model=tts_model,
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=voice_name
                            )
                        )
                    )
                )
            )
            if audio_response.candidates and audio_response.candidates[0].content.parts:
                for part in audio_response.candidates[0].content.parts:
                    if part.inline_data and part.inline_data.data:
                        save_gemini_audio_properly(part.inline_data.data, output_wav_path)
                        return
        except Exception as err:
            last_error = err
            continue

    raise RuntimeError(f"Gemini TTS synthesis failed. Last error: {last_error}")


async def synthesize_edge_voice(text: str, voice: str, output_path: str):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


def synthesize_clean_voice(client, text: str, voice_info: dict, base_filename: str) -> str:
    raw_path = f"{base_filename}_raw.wav" if voice_info["engine"] == "gemini" else f"{base_filename}_raw.mp3"
    trimmed_wav = f"{base_filename}_clean.wav"

    if voice_info["engine"] == "gemini":
        synthesize_gemini_voice(client, text, voice_info["code"], raw_path)
    else:
        asyncio.run(synthesize_edge_voice(text, voice_info["code"], raw_path))

    # Remove leading and trailing dead silence so voice starts immediately at 0.0s
    subprocess.run([
        "ffmpeg", "-y", "-i", raw_path,
        "-af", "silenceremove=start_periods=1:start_silence=0.04:start_threshold=-42dB,areverse,silenceremove=start_periods=1:start_silence=0.04:start_threshold=-42dB,areverse",
        "-ar", "24000", "-ac", "1",
        trimmed_wav
    ], capture_output=True, check=True)

    return trimmed_wav


uploaded_file = st.file_uploader("Upload MP4 Video File", type=["mp4"])

if uploaded_file is not None:
    temp_video = "temp_input.mp4"
    fitted_audio = "fitted_voice.wav"
    output_video = "output_hooked.mp4"

    with open(temp_video, "wb") as f:
        f.write(uploaded_file.getbuffer())

    st.video(temp_video)

    if st.button("🚀 Send Full Video to Gemini & Generate Synced Voiceover", type="primary", use_container_width=True):
        api_key = (gemini_api_key or os.environ.get("GEMINI_API_KEY", "")).strip()
        if not api_key:
            st.error("Please enter your Gemini API Key in the sidebar.")
            st.stop()

        cleanup_temp_files()
        with open(temp_video, "wb") as f:
            f.write(uploaded_file.getbuffer())

        client = genai.Client(
            api_key=api_key,
            http_options={"api_version": "v1beta"}
        )

        with st.status("Running Full-Video Pipeline...", expanded=True) as status:

            # STEP 1: Measure full video duration
            video_duration = get_file_duration(temp_video)
            st.write(f"⏱️ Step 1/5: Full Video Duration: **{video_duration:.2f} seconds**")

            # STEP 2: Upload the WHOLE raw video to Gemini first
            st.write("📹 Step 2/5: Uploading the whole video to Gemini File API...")
            try:
                video_file = client.files.upload(file=temp_video)
            except Exception as e:
                st.error(f"Upload Error: {e}")
                st.stop()

            # Wait until Gemini has completely ingested the full video
            while get_file_state_str(video_file) in ["PROCESSING", "PENDING"]:
                time.sleep(2)
                video_file = client.files.get(name=video_file.name)

            if get_file_state_str(video_file) != "ACTIVE":
                st.error(f"Gemini failed to process video. State: {get_file_state_str(video_file)}")
                st.stop()

            st.write("✅ Full video received by Gemini!")

            # STEP 3: Gemini watches the whole video and writes the chronological script
            target_lang = selected_voice_info["lang"]
            script_type = selected_voice_info["script_type"]
            target_words = max(10, int(video_duration * 2.3))

            st.write(f"🤖 Step 3/5: Gemini is watching the entire {video_duration:.1f}s video and writing the **{script_style}** script in **{target_lang}**...")

            if script_style == "Viral Explanation Mode (Hook-Scoop-Twist)":
                style_guide = """
                CRITICAL STYLE: Use the 3-part 'Hook-Scoop-Twist' structure:
                1. The Hook: Grab attention immediately based on the opening visuals.
                2. The Scoop: Explain what is happening chronologically across the middle of the video.
                3. The Twist / Climax: Deliver a punchy takeaway matching the ending of the video.
                """
            else:
                style_guide = f"Style: {script_style}."

            prompt = f"""
            You are a master viral video narrator.
            Watch this entire {video_duration:.1f}-second video from start to finish.
            Write a single, continuous voiceover script that follows the exact chronological order of visual events in the video so the narration matches what is happening on screen from beginning to end.

            {style_guide}

            CRITICAL CONSTRAINTS:
            1. Write the ENTIRE script natively in {target_lang} using {script_type}.
            2. Write approximately {target_words} spoken words so the narration naturally spans the full {video_duration:.1f} seconds.
            3. Output ONLY the plain spoken script in {target_lang}. No markdown, no timestamps, no stage directions, and no speaker labels.
            """

            response = None
            last_err = None
            for vision_model in ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-2.5-flash"]:
                try:
                    response = generate_content_with_retry(
                        client,
                        model=vision_model,
                        contents=[video_file, prompt]
                    )
                    if response and response.text:
                        st.write(f"✅ Full video analyzed using `{vision_model}`")
                        break
                except Exception as err:
                    last_err = err
                    continue

            # Clean up the remote file from Google's servers after analysis
            try:
                client.files.delete(name=video_file.name)
            except Exception:
                pass

            if response is None or not response.text:
                st.error(f"Failed to generate script from video: {last_err}")
                st.stop()

            creative_script = response.text.strip()
            st.markdown(f"**📝 Generated Script ({target_lang}):**\n\n{creative_script}")

            # STEP 4: Generate AI Voiceover from the script & sync its duration to the video
            st.write(f"🎙️ Step 4/5: Generating AI Voiceover using **{selected_voice_label}**...")
            try:
                clean_wav = synthesize_clean_voice(client, creative_script, selected_voice_info, "generated_voice")
            except Exception as tts_err:
                st.error(f"Audio Generation Error: {tts_err}")
                st.stop()

            audio_duration = get_file_duration(clean_wav)
            exact_tempo = audio_duration / (video_duration * 0.98)
            st.write(f"⚖️ Syncing Audio (**{audio_duration:.2f}s**) to Video (**{video_duration:.2f}s**) at **{exact_tempo:.2f}x** pace...")

            atempo_chain = build_atempo_filter(exact_tempo)
            subprocess.run([
                "ffmpeg", "-y", "-i", clean_wav,
                "-filter:a", f"{atempo_chain},apad,atrim=0:{video_duration}",
                "-ar", "24000", "-ac", "1",
                fitted_audio
            ], capture_output=True, check=True)

            # STEP 5: Mute original video audio 100% and attach synced AI voiceover
            st.write("🎬 Step 5/5: Merging synced AI voiceover with full video (original video audio muted)...")
            subprocess.run([
                "ffmpeg", "-y",
                "-i", temp_video,
                "-i", fitted_audio,
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-t", str(video_duration),
                output_video
            ], check=True)

            status.update(label="✨ Full Video Analyzed & Voiceover Synced!", state="complete", expanded=False)

        st.subheader("🔥 Final Video Output")
        st.video(output_video)
        with open(output_video, "rb") as vf:
            st.download_button(
                label="📥 Download Final Video (MP4)",
                data=vf,
                file_name="synced_viral_video.mp4",
                mime="video/mp4",
                use_container_width=True
    )
            
