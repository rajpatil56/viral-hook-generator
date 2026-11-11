import os
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
st.title("🎬 Direct Multimodal Video Hook Overlay")

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

selected_voice_label = st.sidebar.selectbox("Voice Model & Language", list(VOICE_OPTIONS.keys()))
selected_voice_info = VOICE_OPTIONS[selected_voice_label]

voice_speed = st.sidebar.slider(
    "⚡ Voice Delivery Speed Multiplier", 
    min_value=1.0, 
    max_value=1.8, 
    value=1.22, 
    step=0.01,
    help="1.20x-1.25x is the sweet spot for reel commentary."
)

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

def save_gemini_audio_properly(raw_bytes: bytes, output_wav_path: str):
    """
    Saves Gemini audio output properly as a valid WAV file.
    - If Gemini 3.8 Interactions API returns a full WAV (starts with b'RIFF'), write directly.
    - If Gemini returns raw 24kHz 16-bit mono PCM bytes, wrap it in a WAV header so ffprobe works.
    """
    if isinstance(raw_bytes, str):
        raw_bytes = base64.b64decode(raw_bytes)

    if raw_bytes[:4] == b"RIFF":
        with open(output_wav_path, "wb") as f:
            f.write(raw_bytes)
    else:
        with wave.open(output_wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit PCM
            wf.setframerate(24000)
            wf.writeframes(raw_bytes)

# Robust API Call Wrapper: Handles 429 Rate Limits AND 503 Server Demand Spikes
def generate_content_with_retry(client, model, contents, config=None, max_retries=6):
    delay = 3.0
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
    """
    Synthesizes speech using Gemini Native TTS:
    1. Tries the official Gemini 3.8 TTS `client.interactions.create` API first (avoids speechConfig 400 error).
    2. Falls back to `v1beta` `generate_content` across 3.8 / 3.1 / 2.5 TTS models if needed.
    """
    # --- METHOD 1: Official Interactions API for Gemini 3.8 Flash TTS ---
    if hasattr(client, "interactions"):
        for tts_model in ["gemini-3.8-flash-tts", "gemini-3.1-flash-tts-preview"]:
            try:
                interaction = client.interactions.create(
                    model=tts_model,
                    input=[{
                        "type": "user_input",
                        "content": [{
                            "type": "text",
                            "text": text
                        }]
                    }],
                    response_format={"type": "audio"},
                    generation_config={
                        "speech_config": [{"voice": voice_name}]
                    }
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

    # --- METHOD 2: v1beta generate_content API with SpeechConfig ---
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

    raise RuntimeError(f"Gemini TTS synthesis failed across all endpoints. Last error: {last_error}")

async def synthesize_edge_voice(text: str, voice: str, output_path: str):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

uploaded_file = st.file_uploader("Upload MP4 Video File", type=["mp4"])

if uploaded_file is not None:
    temp_video = "temp_input.mp4"
    fitted_audio = "fitted_voice.wav"
    output_video = "output_hooked.mp4"

    with open(temp_video, "wb") as f:
        f.write(uploaded_file.getbuffer())

    st.video(temp_video)

    if st.button("🚀 Analyze Video & Overlay Viral Hook"):
        api_key = (gemini_api_key or os.environ.get("GEMINI_API_KEY", "")).strip()
        if not api_key:
            st.error("Please enter your Gemini API Key in the sidebar.")
            st.stop()

        cleanup_temp_files()
        with open(temp_video, "wb") as f:
            f.write(uploaded_file.getbuffer())

        # CRITICAL FIX: Force v1beta so `speechConfig` is recognized by the API
        client = genai.Client(
            api_key=api_key,
            http_options={"api_version": "v1beta"}
        )

        with st.status("Analyzing Video & Building Audio Overlay...", expanded=True) as status:

            # 1. Video Duration
            video_duration = get_file_duration(temp_video)
            st.write(f"⏱️ Video Duration: **{video_duration:.2f} seconds**")

            # 2. Upload Video to Gemini File API
            st.write("📹 Uploading raw video to Gemini for direct visual understanding...")
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

            # 3. Multimodal Analysis (Tries 3.8-flash -> 3.6-flash -> 2.5-flash)
            st.write(f"🤖 Gemini is analyzing video & writing a **{script_style}** script in **{selected_voice_info['lang']}**...")
            
            target_lang = selected_voice_info["lang"]
            script_type = selected_voice_info["script_type"]

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
            1. LANGUAGE REQUIREMENT: You MUST write the ENTIRE script natively in {target_lang} using standard {script_type}. YOU MUST RESPOND UNMISTAKABLY IN LANGUAGE <{target_lang}>.
            2. Total script length MUST be spoken aloud in EXACTLY {int(video_duration)} seconds or less. Target roughly {int(video_duration * 2.2)} spoken words in {target_lang}.
            3. The first sentence MUST be an immediate, viral hook to catch viewer attention in the first 3 seconds.
            4. Output ONLY the plain text script to be spoken in {target_lang}. No markdown, no translation notes, no scene instructions, no labels.
            """

            response = None
            last_script_err = None
            for vision_model in ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-2.5-flash"]:
                try:
                    response = generate_content_with_retry(
                        client,
                        model=vision_model,
                        contents=[video_file, prompt]
                    )
                    break
                except Exception as err:
                    last_script_err = err
                    continue

            if response is None:
                st.error(f"Error generating script: {last_script_err}")
                st.stop()

            # Clean up uploaded video from Gemini server
            try:
                client.files.delete(name=video_file.name)
            except Exception:
                pass

            creative_script = response.text.strip() if response.text else ""
            if not creative_script:
                st.error("Generated script was empty. Please try again.")
                st.stop()

            st.markdown(f"**Generated Script ({target_lang}):**\n\n{creative_script}")

            # 4. Clean Audio Voice Synthesis Path
            if selected_voice_info["engine"] == "gemini":
                script_audio = "generated_voice.wav"
                st.write(f"🎙️ Generating native AI dub using Gemini (**{selected_voice_info['code']}**) voice...")
                try:
                    synthesize_gemini_voice(
                        client=client,
                        text=creative_script,
                        voice_name=selected_voice_info["code"],
                        output_wav_path=script_audio
                    )
                except Exception as err:
                    st.error(f"Gemini Audio Generation Error: {err}")
                    st.stop()
            else:
                script_audio = "generated_voice.mp3"
                st.write(f"🎙️ Converting script to synthetic voiceover using Edge-TTS (**{selected_voice_info['code']}**)...")
                asyncio.run(synthesize_edge_voice(creative_script, selected_voice_info["code"], script_audio))

            # 5. Fit Audio Duration via FFmpeg ATempo (Respecting User Speed Multiplier)
            audio_duration = get_file_duration(script_audio)
            needed_tempo = audio_duration / video_duration
            
            final_tempo = max(needed_tempo, voice_speed)
            final_tempo = max(0.5, min(final_tempo, 2.0))

            subprocess.run([
                "ffmpeg", "-y", "-i", script_audio,
                "-filter:a", f"atempo={final_tempo}",
                "-ar", "24000", "-ac", "1",
                fitted_audio
            ], capture_output=True, check=True)

            # 6. Mux Final Audio/Video (100% replaces original video sound with AI voice)
            st.write("🎬 Muxing script audio into video via FFmpeg (original video audio muted)...")
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
                
