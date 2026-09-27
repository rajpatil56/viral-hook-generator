import os
import glob
import time
import asyncio
import subprocess
import streamlit as st
import edge_tts
from google import genai
from google.genai import types

st.set_page_config(page_title="Multimodal Video Hook Generator", layout="wide")
st.title("🎬 Direct Multimodal Video Hook Overlay")

# Sidebar Configuration
st.sidebar.header("Settings")
gemini_api_key = st.sidebar.text_input("Gemini API Key", type="password", help="Get a key from Google AI Studio")

# Integrated Voice Roster: Gemini Native & Edge-TTS
VOICE_OPTIONS = {
    "Gemini - Charon (Hindi)": {"engine": "gemini", "code": "Charon", "lang": "Hindi", "script_type": "Devanagari script"},
    "Gemini - Charon (Marathi)": {"engine": "gemini", "code": "Charon", "lang": "Marathi", "script_type": "Devanagari script"},
    "Gemini - Puck (Hindi)": {"engine": "gemini", "code": "Puck", "lang": "Hindi", "script_type": "Devanagari script"},
    "Gemini - Puck (Marathi)": {"engine": "gemini", "code": "Puck", "lang": "Marathi", "script_type": "Devanagari script"},
    "Gemini - Kore (English)": {"engine": "gemini", "code": "Kore", "lang": "English", "script_type": "English text"},
    "Edge - Hindi Male (Madhur)": {"engine": "edge", "code": "hi-IN-MadhurNeural", "lang": "Hindi", "script_type": "Devanagari script"},
    "Edge - Hindi Female (Swara)": {"engine": "edge", "code": "hi-IN-SwaraNeural", "lang": "Hindi", "script_type": "Devanagari script"},
    "Edge - Marathi Female (Aarohi)": {"engine": "edge", "code": "mr-IN-AarohiNeural", "lang": "Marathi", "script_type": "Devanagari script"},
    "Edge - English Male (Guy)": {"engine": "edge", "code": "en-US-GuyNeural", "lang": "English", "script_type": "English text"},
}

selected_voice_label = st.sidebar.selectbox("Voice Model & Language", list(VOICE_OPTIONS.keys()))
selected_voice_info = VOICE_OPTIONS[selected_voice_label]

script_style = st.sidebar.selectbox(
    "Hook / Script Style",
    [
        "High-Dopamine Viral Opening", 
        "Viral Explanation Mode (Hook-Scoop-Twist)", 
        "Cinematic Storytelling", 
        "Humorous & Punchy", 
        "Explainer Hook"
    ]
)

def cleanup_temp_files():
    patterns = ["temp_input.mp4", "generated_voice.mp3", "fitted_voice.wav", "output_hooked.mp4"]
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

async def synthesize_voice(text: str, voice: str, output_path: str):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

uploaded_file = st.file_uploader("Upload MP4 Video File", type=["mp4"])

if uploaded_file is not None:
    temp_video = "temp_input.mp4"
    script_audio = "generated_voice.mp3"
    fitted_audio = "fitted_voice.wav"
    output_video = "output_hooked.mp4"

    with open(temp_video, "wb") as f:
        f.write(uploaded_file.getbuffer())

    st.video(temp_video)

    if st.button("🚀 Analyze Video & Overlay Viral Hook"):
        api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            st.error("Please enter your Gemini API Key in the sidebar.")
            st.stop()

        cleanup_temp_files()
        with open(temp_video, "wb") as f:
            f.write(uploaded_file.getbuffer())

        client = genai.Client(api_key=api_key)

        with st.status("Analyzing Video & Building Audio Overlay...", expanded=True) as status:

            video_duration = get_file_duration(temp_video)
            st.write(f"⏱️ Video Duration: **{video_duration:.2f} seconds**")

            st.write("📹 Uploading raw video to Gemini for direct visual understanding...")
            try:
                video_file = client.files.upload(file=temp_video)
            except Exception as e:
                st.error(f"Authentication or Upload Error: {e}")
                st.stop()

            while video_file.state.name == "PROCESSING":
                time.sleep(2)
                video_file = client.files.get(name=video_file.name)

            if video_file.state.name == "FAILED":
                st.error("Gemini failed to process the video input.")
                st.stop()

            st.write(f"🤖 Gemini is generating a **{script_style}** script in **{selected_voice_info['lang']}**...")
            
            target_lang = selected_voice_info["lang"]
            script_type = selected_voice_info["script_type"]

            # Explanation Mode Injection
            if script_style == "Viral Explanation Mode (Hook-Scoop-Twist)":
                style_guide = """
                CRITICAL STYLE: You MUST use the exact 3-part 'Hook-Scoop-Twist' anatomy.
                1. The Hook (Contrasting Irony): Present an exaggerated, wholesome description of the subject in the video and immediately set up a surprising or slightly funny situation they've agreed to.
                2. The Scoop (The "Inside Story" Reveal): Dive into a juicy background detail told in a casual, gossipy tone.
                3. The Twist / Punchline: Highlight a quirky silver lining or funny dynamic, delivered with light humor.
                """
            else:
                style_guide = f"Style: {script_style}."

            prompt = f"""
            You are a master viral video content creator.
            Watch the visuals, movement, actions, and overall context of this attached video file.
            Write a high-converting, extremely interesting opening hook and creative story/script based directly on what is visually happening in the video.

            {style_guide}

            CRITICAL LANGUAGE & CONSTRAINTS:
            1. LANGUAGE REQUIREMENT: You MUST write the ENTIRE script natively in {target_lang} using the standard {script_type}. YOU MUST RESPOND UNMISTAKABLY IN LANGUAGE <{target_lang}>.
            2. Total script length MUST be spoken aloud in EXACTLY {int(video_duration)} seconds or less. Target roughly {int(video_duration * 2.2)} spoken words in {target_lang}.
            3. The first sentence MUST be an immediate, viral hook to catch viewer attention in the first 3 seconds.
            4. Output ONLY the plain text script to be spoken in {target_lang}. No markdown, no translation notes, no scene instructions, no labels.
            """

            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=[video_file, prompt]
            )

            try:
                client.files.delete(name=video_file.name)
            except Exception:
                pass

            creative_script = response.text.strip()
            st.markdown(f"**Generated Script ({target_lang}):**\n> {creative_script}")

            # Dual Audio Generation Path
            if selected_voice_info["engine"] == "gemini":
                st.write(f"🎙️ Generating native AI dub using Gemini ({selected_voice_info['code']}) voice...")
                
                audio_prompt = f"Read the following text out loud in {target_lang} with highly realistic emotion, gossipy tone, and natural pacing. Do not read any punctuation literally: {creative_script}"
                
                audio_response = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[audio_prompt],
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
                if audio_response.candidates and audio_response.candidates[0].content.parts:
                    for part in audio_response.candidates[0].content.parts:
                        if part.inline_data and part.inline_data.mime_type.startswith("audio/"):
                            audio_bytes = part.inline_data.data
                            break
                
                if audio_bytes:
                    with open(script_audio, "wb") as f:
                        f.write(audio_bytes)
                else:
                    st.error("Gemini failed to return audio data. Check your API usage or prompt.")
                    st.stop()
            else:
                st.write(f"🎙️ Converting script to synthetic voiceover using Edge-TTS ({selected_voice_info['code']})...")
                asyncio.run(synthesize_voice(creative_script, selected_voice_info["code"], script_audio))

            audio_duration = get_file_duration(script_audio)
            tempo = max(0.8, min(audio_duration / video_duration, 1.6))

            subprocess.run([
                "ffmpeg", "-y", "-i", script_audio,
                "-filter:a", f"atempo={tempo}",
                "-ar", "24000", "-ac", "1",
                fitted_audio
            ], capture_output=True, check=True)

            st.write("🎬 Muxing script audio into video via FFmpeg...")
            subprocess.run([
                "ffmpeg", "-y",
                "-i", temp_video,
                "-i", fitted_audio,
                "-c:v", "copy",
                "-c:a", "aac",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-shortest",
                output_video
            ], check=True)

            status.update(label="✨ Video Hook & Script Successfully Overlaid!", state="complete", expanded=False)

        st.subheader("🔥 Final Video Output")
        st.video(output_video)
