import os
import glob
import time
import json
import asyncio
import subprocess
import streamlit as st
import edge_tts
from google import genai
from google.genai import types

st.set_page_config(page_title="Multimodal Video Hook Generator", layout="wide")
st.title("🎬 Frame-Synced Multimodal Video Hook Overlay")

# Sidebar Configuration
st.sidebar.header("Settings")
gemini_api_key = st.sidebar.text_input("Gemini API Key", type="password", help="Get a key from Google AI Studio")

# Integrated Voice Roster
VOICE_OPTIONS = {
    "Gemini - Kore (Hindi / Energetic)": {"engine": "gemini", "code": "Kore", "lang": "Hindi", "script_type": "Devanagari script"},
    "Gemini - Kore (Marathi / Energetic)": {"engine": "gemini", "code": "Kore", "lang": "Marathi", "script_type": "Devanagari script"},
    "Gemini - Kore (English)": {"engine": "gemini", "code": "Kore", "lang": "English", "script_type": "English text"},
    "Gemini - Aoede (Hindi / Deep)": {"engine": "gemini", "code": "Aoede", "lang": "Hindi", "script_type": "Devanagari script"},
    "Gemini - Fenrir (Hindi / Bold)": {"engine": "gemini", "code": "Fenrir", "lang": "Hindi", "script_type": "Devanagari script"},
    "Gemini - Charon (Hindi)": {"engine": "gemini", "code": "Charon", "lang": "Hindi", "script_type": "Devanagari script"},
    "Gemini - Charon (Marathi)": {"engine": "gemini", "code": "Charon", "lang": "Marathi", "script_type": "Devanagari script"},
    "Gemini - Puck (Hindi)": {"engine": "gemini", "code": "Puck", "lang": "Hindi", "script_type": "Devanagari script"},
    "Gemini - Puck (Marathi)": {"engine": "gemini", "code": "Puck", "lang": "Marathi", "script_type": "Devanagari script"},
    "Edge - Hindi Male (Madhur)": {"engine": "edge", "code": "hi-IN-MadhurNeural", "lang": "Hindi", "script_type": "Devanagari script"},
    "Edge - Hindi Female (Swara)": {"engine": "edge", "code": "hi-IN-SwaraNeural", "lang": "Hindi", "script_type": "Devanagari script"},
    "Edge - Marathi Female (Aarohi)": {"engine": "edge", "code": "mr-IN-AarohiNeural", "lang": "Marathi", "script_type": "Devanagari script"},
    "Edge - English Male (Guy)": {"engine": "edge", "code": "en-US-GuyNeural", "lang": "English", "script_type": "English text"},
}

selected_voice_label = st.sidebar.selectbox("Voice Model & Language", list(VOICE_OPTIONS.keys()))
selected_voice_info = VOICE_OPTIONS[selected_voice_label]

voice_speed = st.sidebar.slider(
    "⚡ Voice Delivery Speed Multiplier", 
    min_value=1.1, 
    max_value=1.8, 
    value=1.3, 
    step=0.05,
    help="Controls how fast and energetic the speech is delivered within each visual segment."
)

script_style = st.sidebar.selectbox(
    "Hook / Script Style",
    [
        "Viral Explanation Mode (Hook-Scoop-Twist)",
        "High-Dopamine Viral Opening", 
        "Cinematic Storytelling", 
        "Humorous & Punchy", 
        "Explainer Hook"
    ]
)

def cleanup_temp_files():
    patterns = ["temp_input.mp4", "seg_*.wav", "master_audio.wav", "output_hooked.mp4"]
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

async def synthesize_voice_edge(text: str, voice: str, output_path: str):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

uploaded_file = st.file_uploader("Upload MP4 Video File", type=["mp4"])

if uploaded_file is not None:
    temp_video = "temp_input.mp4"
    master_audio = "master_audio.wav"
    output_video = "output_hooked.mp4"

    with open(temp_video, "wb") as f:
        f.write(uploaded_file.getbuffer())

    st.video(temp_video)

    if st.button("🚀 Analyze Video & Overlay Synced Viral Hook"):
        api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            st.error("Please enter your Gemini API Key in the sidebar.")
            st.stop()

        cleanup_temp_files()
        with open(temp_video, "wb") as f:
            f.write(uploaded_file.getbuffer())

        client = genai.Client(api_key=api_key)

        with st.status("Analyzing Video Frames & Synchronizing Audio...", expanded=True) as status:

            # 1. Video Duration
            video_duration = get_file_duration(temp_video)
            st.write(f"⏱️ Video Duration: **{video_duration:.2f} seconds**")

            # 2. Upload Video to Gemini File API
            st.write("📹 Uploading raw video to Gemini for frame analysis...")
            try:
                video_file = client.files.upload(file=temp_video)
            except Exception as e:
                st.error(f"Authentication or Upload Error: {e}")
                st.stop()

            while get_file_state_str(video_file) in ["PROCESSING", "PENDING"]:
                time.sleep(2)
                video_file = client.files.get(name=video_file.name)

            if get_file_state_str(video_file) != "ACTIVE":
                st.error(f"Gemini failed to process video. File state: {get_file_state_str(video_file)}")
                st.stop()

            # 3. Multimodal Frame-by-Frame Segmentation via Gemini 3.6 Flash
            target_lang = selected_voice_info["lang"]
            script_type = selected_voice_info["script_type"]

            st.write(f"🤖 Gemini 3.6 Flash is detecting scene cuts and writing synced lines in **{target_lang}**...")

            prompt = f"""
            You are a viral reel editor.
            Watch the visuals and scene transitions in this video (duration: {video_duration:.2f} seconds).
            Break the video into 3 to 5 timed visual segments corresponding to scene changes or photo transitions.

            For EACH visual segment, write a concise, snappy, high-dopamine sentence in {target_lang} ({script_type}) that describes what is happening visually in THAT specific frame window.

            Return ONLY a valid JSON array of objects with these exact keys:
            - "start": start time in seconds (float)
            - "end": end time in seconds (float)
            - "text": plain text script line in {target_lang} to be spoken

            Constraints:
            1. Segments must start at 0.0 and cover up to {video_duration:.2f} seconds without gaps or overlaps.
            2. The text lines MUST be short enough to be spoken rapidly within their target time slot.
            3. Do not include markdown tags or explanation. Output JSON array ONLY.
            """

            try:
                response = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[video_file, prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )
            except Exception as err:
                st.error(f"Error analyzing video frames: {err}")
                st.stop()

            try:
                client.files.delete(name=video_file.name)
            except Exception:
                pass

            try:
                segments = json.loads(response.text)
            except Exception as e:
                st.error(f"Failed to parse scene JSON from Gemini: {e}")
                st.code(response.text)
                st.stop()

            st.markdown("### 🎯 Frame-Synced Script Segments")
            for seg in segments:
                st.write(f"⏱️ **[{seg['start']:.1f}s - {seg['end']:.1f}s]**: {seg['text']}")

            # 4. Generate & Time-Fit Audio Per Segment
            st.write("🎙️ Synthesizing and timing individual voice tracks...")
            processed_seg_files = []

            for i, seg in enumerate(segments):
                raw_seg_file = f"seg_raw_{i}.wav"
                fit_seg_file = f"seg_fit_{i}.wav"
                
                seg_text = seg["text"].strip()
                target_slot_dur = max(1.0, seg["end"] - seg["start"])

                # Synthesize individual segment clip
                if selected_voice_info["engine"] == "gemini":
                    audio_res = client.models.generate_content(
                        model="gemini-3.8-flash-tts",
                        contents=[seg_text],
                        config=types.GenerateContentConfig(
                            response_modalities=["AUDIO"],
                            speech_config=types.SpeechConfig(
                                voice_config=types.VoiceConfig(
                                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                        voice_name=selected_voice_info["code"]
                                    )
                                )
                            )
                        )
                    )
                    
                    audio_bytes = None
                    if audio_res.candidates and audio_res.candidates[0].content.parts:
                        for part in audio_res.candidates[0].content.parts:
                            if part.inline_data and part.inline_data.mime_type and part.inline_data.mime_type.startswith("audio/"):
                                audio_bytes = part.inline_data.data
                                break

                    if not audio_bytes:
                        st.error(f"Failed to generate TTS for segment {i}")
                        st.stop()

                    with open(raw_seg_file, "wb") as f:
                        f.write(audio_bytes)
                else:
                    asyncio.run(synthesize_voice_edge(seg_text, selected_voice_info["code"], raw_seg_file))

                # Calculate speed scaling factor
                raw_dur = get_file_duration(raw_seg_file)
                needed_tempo = raw_dur / target_slot_dur
                
                # Apply speed multiplier for snappy delivery
                final_tempo = max(needed_tempo, voice_speed)
                final_tempo = max(0.5, min(final_tempo, 2.0))

                subprocess.run([
                    "ffmpeg", "-y", "-i", raw_seg_file,
                    "-filter:a", f"atempo={final_tempo}",
                    "-ar", "24000", "-ac", "1",
                    fit_seg_file
                ], capture_output=True, check=True)

                processed_seg_files.append((fit_seg_file, seg["start"]))

            # 5. Precise Audio Stitching & Mixing using FFmpeg adelay
            st.write("🎛️ Mixing frame-aligned audio clips into master track...")
            
            ffmpeg_cmd = ["ffmpeg", "-y"]
            for file, _ in processed_seg_files:
                ffmpeg_cmd.extend(["-i", file])

            filter_parts = []
            for i, (_, start_time) in enumerate(processed_seg_files):
                delay_ms = int(start_time * 1000)
                filter_parts.append(f"[{i}:a]adelay={delay_ms}|{delay_ms}[a{i}]")

            mix_inputs = "".join(f"[a{i}]" for i in range(len(processed_seg_files)))
            filter_parts.append(f"{mix_inputs}amix=inputs={len(processed_seg_files)}:normalize=0[outa]")

            filter_complex = ";".join(filter_parts)
            ffmpeg_cmd.extend(["-filter_complex", filter_complex, "-map", "[outa]", master_audio])

            subprocess.run(ffmpeg_cmd, capture_output=True, check=True)

            # 6. Final Video Muxing
            st.write("🎬 Muxing frame-synced master audio into video...")
            subprocess.run([
                "ffmpeg", "-y",
                "-i", temp_video,
                "-i", master_audio,
                "-c:v", "copy",
                "-c:a", "aac",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-shortest",
                output_video
            ], check=True)

            status.update(label="✨ Frame-Synced Video Voiceover Completed!", state="complete", expanded=False)

        st.subheader("🔥 Final Video Output")
        st.video(output_video)
