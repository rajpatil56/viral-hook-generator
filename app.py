import streamlit as st
import tempfile
import os
import json
import time
import re
import wave
import base64
import subprocess
from gtts import gTTS

# Support both new `google-genai` SDK and legacy `google-generativeai`
try:
    from google import genai
    from google.genai import types
    USING_NEW_SDK = True
except ImportError:
    import google.generativeai as genai_legacy
    USING_NEW_SDK = False

st.set_page_config(
    page_title="AI Script Makeover & Voiceover Studio",
    page_icon="🎬",
    layout="wide"
)

# ==========================================
# 1. MASTER DICTIONARY OF SCRIPT STYLES
# ==========================================
SCRIPT_STYLES = {
    "Sidhu Paaji Commentary (Oye Guru! Thoko Taali)": (
        "Watch the video actions closely and write a high-energy Navjot Singh Sidhu style commentary. "
        "Use signature phrases like 'Oye Guru!', 'Thoko Taali!', 'Chhaa Gaye Guru!', rhyming shayari, "
        "and hilarious energetic metaphors matching the exact visual moments in the clip."
    ),
    "Soul Lines Paaji Mode (Hook-Hero-Roast-Closer)": (
        "Observe the video clip and structure the voiceover strictly into 4 high-impact beats: "
        "1. Hook (grab attention immediately based on the opening frame), "
        "2. Hero (highlight the main person/action), "
        "3. Roast (playful, witty desi roast of what happens in the middle), "
        "4. Closer (punchy, memorable final line)."
    ),
    "High-Dopamine Viral Opening": (
        "Write an ultra-fast, high-retention script starting with an explosive visual hook in the first 2 seconds. "
        "Keep sentences under 6 words, punchy, dramatic, and hyper-engaging to maximize watch time."
    ),
    "Viral Explanation Mode (Hook-Scoop-Twist)": (
        "Break down what happens visually in the clip using: "
        "1. Hook (create an instant curiosity gap), "
        "2. Scoop (clearly explain the visual context and action), "
        "3. Twist (reveal an unexpected or mind-blowing takeaway at the end)."
    ),
    "Cinematic Storytelling": (
        "Write a dramatic, immersive, movie-trailer style narration that matches the visual pacing, "
        "camera movement, tension, and emotion of the clip."
    ),
    "Humorous & Punchy": (
        "Observe the actions and expressions in the video and write a witty, sarcastic, meme-style voiceover "
        "packed with quick comedic timing and relatable humour."
    ),
    "Explainer Hook": (
        "Start with a strong 'Watch closely at...' or 'Nobody noticed this, but...' hook and clearly explain "
        "the main event happening in the video step-by-step."
    )
}

VOICE_OPTIONS = {
    "Gemini Native: Charon (Deep, Crisp Male)": {
        "edge": "en-IN-PrabhatNeural",
        "gemini": "Charon",
        "gtts_lang": "en",
        "gtts_tld": "co.in"
    },
    "Gemini Native: Fenrir (Viral, Deep US Male)": {
        "edge": "en-US-ChristopherNeural",
        "gemini": "Fenrir",
        "gtts_lang": "en",
        "gtts_tld": "com"
    },
    "Gemini Native: Puck (Energetic Male)": {
        "edge": "hi-IN-MadhurNeural",
        "gemini": "Puck",
        "gtts_lang": "hi",
        "gtts_tld": "co.in"
    },
    "Gemini Native: Aoede (Clear Female)": {
        "edge": "hi-IN-SwaraNeural",
        "gemini": "Aoede",
        "gtts_lang": "hi",
        "gtts_tld": "co.in"
    },
    "Gemini Native: Kore (Expressive Female)": {
        "edge": "en-IN-NeerjaNeural",
        "gemini": "Kore",
        "gtts_lang": "en",
        "gtts_tld": "co.in"
    },
    "Edge-TTS: Hindi Male (Madhur)": {
        "edge": "hi-IN-MadhurNeural",
        "gemini": "Puck",
        "gtts_lang": "hi",
        "gtts_tld": "co.in"
    },
    "Edge-TTS: Hindi Female (Swara)": {
        "edge": "hi-IN-SwaraNeural",
        "gemini": "Aoede",
        "gtts_lang": "hi",
        "gtts_tld": "co.in"
    }
}

# ==========================================
# 2. SIDEBAR SETTINGS
# ==========================================
with st.sidebar:
    st.header("Settings")
    gemini_api_key = st.text_input("Gemini API Key", type="password")

    selected_style = st.selectbox(
        "🎨 Script Makeover Style",
        options=list(SCRIPT_STYLES.keys())
    )

    convert_vertical = st.checkbox(
        "📐 Auto-convert video to 9:16 Vertical (720x1280)",
        value=True
    )

    audio_choice = st.radio(
        "🔊 Audio Output Mode",
        [
            "Overlay AI Voiceover on Video",
            "Keep Original Video Audio Only"
        ],
        index=0
    )

    st.divider()
    tts_engine_preference = st.selectbox(
        "⚙️ Primary Voice Engine",
        [
            "Gemini 2.5 Native TTS First (Charon, Fenrir, Puck, etc.)",
            "Edge-TTS First (Fastest, No Gemini Quota Used)"
        ],
        index=0
    )
    
    selected_voice_label = st.selectbox("🎙️ Voice Model & Language", list(VOICE_OPTIONS.keys()))
    selected_voice_cfg = VOICE_OPTIONS[selected_voice_label]

    language_instruction = st.selectbox(
        "🌐 Script Output Language",
        ["Hinglish (Roman Hindi + English Mix - Best for Viral Shorts)", "Pure Hindi (Devanagari)", "English"]
    )


# ==========================================
# 3. BULLETPROOF 3-TIER TTS ENGINE
# ==========================================
def clean_script_for_tts(text: str) -> str:
    """Removes markdown, stage directions, and emojis that trigger TTS ClientError."""
    text = re.sub(r"\[.*?\]|\(.*?\)|\*+", "", text)
    text = re.sub(r"^(Narrator|Voiceover|Speaker|Audio|Script)\s*:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text or "Watch this amazing moment right now!"


def generate_tts_bulletproof(
    text: str,
    voice_cfg: dict,
    output_audio_path: str,
    api_key: str,
    prefer_gemini: bool = True
) -> bool:
    """
    3-Tier TTS Generator:
    1. Gemini 2.5 Flash TTS (Charon, Fenrir, Puck, etc.)
    2. Subprocess CLI Edge-TTS
    3. gTTS + FFmpeg speed boost fallback
    """
    clean_text = clean_script_for_tts(text)

    # --- TIER 1: GEMINI 2.5 NATIVE TTS ---
    if prefer_gemini and USING_NEW_SDK and api_key:
        try:
            client = genai.Client(api_key=api_key.strip())
            tts_resp = client.models.generate_content(
                model="gemini-2.5-flash-preview-tts",
                contents=f"Read this script with high energy and natural pacing: {clean_text}",
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=voice_cfg["gemini"]
                            )
                        )
                    )
                )
            )
            inline_data = tts_resp.candidates[0].content.parts[0].inline_data
            pcm_bytes = inline_data.data
            if isinstance(pcm_bytes, str):
                pcm_bytes = base64.b64decode(pcm_bytes)

            wav_temp = output_audio_path + ".wav"
            with wave.open(wav_temp, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                wf.writeframes(pcm_bytes)

            subprocess.run(
                ["ffmpeg", "-y", "-i", wav_temp, "-c:a", "libmp3lame", "-q:a", "2", output_audio_path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            if os.path.exists(output_audio_path) and os.path.getsize(output_audio_path) > 500:
                time.sleep(1)
                return True
        except Exception as e:
            st.caption(f"ℹ️ Gemini TTS skipped ({type(e).__name__}), falling back to Edge-TTS...")

    # --- TIER 2: SUBPROCESS CLI EDGE-TTS ---
    try:
        edge_cmd = [
            "edge-tts",
            "--voice", voice_cfg["edge"],
            "--rate=+8%",
            "--text", clean_text,
            "--write-media", output_audio_path
        ]
        res = subprocess.run(edge_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        if res.returncode == 0 and os.path.exists(output_audio_path) and os.path.getsize(output_audio_path) > 500:
            return True
    except Exception:
        pass

    # --- TIER 3: gTTS FALLBACK ---
    try:
        raw_gtts_path = output_audio_path + "_raw.mp3"
        tts = gTTS(text=clean_text, lang=voice_cfg["gtts_lang"], tld=voice_cfg["gtts_tld"], slow=False)
        tts.save(raw_gtts_path)

        subprocess.run(
            ["ffmpeg", "-y", "-i", raw_gtts_path, "-filter:a", "atempo=1.12", output_audio_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        if os.path.exists(output_audio_path) and os.path.getsize(output_audio_path) > 300:
            return True
    except Exception as e:
        st.error(f"All TTS engines failed: {e}")

    return False


# ==========================================
# 4. VIDEO PROCESSING & GEMINI ANALYSIS
# ==========================================
def process_video_clip(
    input_video: str,
    output_path: str,
    make_vertical: bool = True,
    tts_audio_path: str = None
):
    vf_filter = (
        "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280"
        if make_vertical else "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    )

    if tts_audio_path and os.path.exists(tts_audio_path):
        cmd = [
            "ffmpeg", "-y",
            "-i", input_video,
            "-i", tts_audio_path,
            "-filter_complex",
            f"[0:v]{vf_filter}[v];[0:a]volume=0.15[a0];[1:a]volume=1.0[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[a]",
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            output_path
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", input_video,
            "-vf", vf_filter,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            output_path
        ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0 and tts_audio_path:
        fallback_cmd = [
            "ffmpeg", "-y",
            "-i", input_video,
            "-i", tts_audio_path,
            "-vf", vf_filter,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac", "-shortest",
            output_path
        ]
        subprocess.run(fallback_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def analyze_video_with_gemini(api_key: str, video_path: str, style_name: str, lang_choice: str):
    clean_key = api_key.strip()
    style_prompt = SCRIPT_STYLES[style_name]

    prompt = f"""
    You are an expert viral Shorts producer and scriptwriter.
    Watch the uploaded video carefully, observing the exact visual actions, reactions, and pacing.
    
    Task: Write a high-retention voiceover script for this video using the following style:
    - **{style_name}**: {style_prompt}

    Language Requirement: Write the spoken script in {lang_choice}.
    Important: Write ONLY the spoken words. No stage directions, no markdown asterisks, and no speaker labels.

    Return ONLY valid JSON in this exact format:
    {{
      "title": "Catchy Viral Hook Title",
      "visual_summary": "Brief description of what happens visually in this clip",
      "script": "Full spoken voiceover script text..."
    }}
    """

    st.info("📤 Uploading video to Gemini Vision for script generation...")

    if USING_NEW_SDK:
        client = genai.Client(api_key=clean_key)
        uploaded_file = client.files.upload(file=video_path)
        while uploaded_file.state.name == "PROCESSING":
            time.sleep(2)
            uploaded_file = client.files.get(name=uploaded_file.name)
        if uploaded_file.state.name == "FAILED":
            raise RuntimeError("Gemini video processing failed.")

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[uploaded_file, prompt],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        raw_text = response.text.strip()
    else:
        genai_legacy.configure(api_key=clean_key)
        uploaded_file = genai_legacy.upload_file(path=video_path)
        while uploaded_file.state.name == "PROCESSING":
            time.sleep(2)
            uploaded_file = genai_legacy.get_file(uploaded_file.name)
        if uploaded_file.state.name == "FAILED":
            raise RuntimeError("Gemini video processing failed.")

        model = genai_legacy.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content([uploaded_file, prompt])
        raw_text = response.text.strip()

    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[-1]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3].strip()

    return json.loads(raw_text)


# ==========================================
# 5. MAIN APP UI & EXECUTION FLOW
# ==========================================
st.title("🎬 AI Script Makeover & Voiceover Studio")
st.caption("Transform any video with professional AI voice models (Charon, Fenrir, Puck, Aoede, Kore) and custom viral script styles.")

uploaded_video = st.file_uploader("Upload Video (MP4, MOV, MKV, WebM)", type=["mp4", "mov", "mkv", "webm"])

if uploaded_video:
    col_preview, col_info = st.columns([1, 2])
    with col_preview:
        st.video(uploaded_video)
    with col_info:
        st.markdown("### Active Configuration")
        st.write(f"**Script Style:** `{selected_style}`")
        st.write(f"**9:16 Vertical Crop:** `{'Enabled (720x1280)' if convert_vertical else 'Disabled'}`")
        st.write(f"**Voice Model:** `{selected_voice_label}`")
        st.write(f"**Audio Mode:** `{audio_choice}`")

    if st.button("🚀 Generate AI Voiceover & Makeover", type="primary", use_container_width=True):
        if not gemini_api_key:
            st.error("Please enter your Gemini API Key in the left sidebar.")
            st.stop()

        with tempfile.TemporaryDirectory() as temp_dir:
            source_video_path = os.path.join(temp_dir, "input_video.mp4")
            with open(source_video_path, "wb") as f:
                f.write(uploaded_video.read())

            prefer_gemini_tts = ("Gemini 2.5 Native TTS" in tts_engine_preference)

            try:
                with st.spinner("🧠 Gemini is analyzing your video and crafting the script makeover..."):
                    analysis_result = analyze_video_with_gemini(
                        api_key=gemini_api_key,
                        video_path=source_video_path,
                        style_name=selected_style,
                        lang_choice=language_instruction
                    )

                title = analysis_result.get("title", "Viral Short")
                visual_summary = analysis_result.get("visual_summary", "")
                script_text = analysis_result.get("script", "")

                st.success("✅ Script makeover generated successfully!")
                
                st.subheader(f"📝 Generated Script ({selected_style})")
                st.info(script_text)
                st.caption(f"**Visual Summary:** {visual_summary}")

                audio_path = None
                if "Overlay AI Voiceover" in audio_choice:
                    audio_path = os.path.join(temp_dir, "voiceover.mp3")
                    with st.spinner(f"🎙️ Synthesizing voiceover using `{selected_voice_label}`..."):
                        success_tts = generate_tts_bulletproof(
                            text=script_text,
                            voice_cfg=selected_voice_cfg,
                            output_audio_path=audio_path,
                            api_key=gemini_api_key,
                            prefer_gemini=prefer_gemini_tts
                        )
                        if not success_tts:
                            st.warning("⚠️ AI Voice synthesis encountered an issue. Exporting video with original audio.")
                            audio_path = None

                output_video_path = os.path.join(temp_dir, "output_viral_short.mp4")
                with st.spinner("🎞️ Processing video formatting and audio mixing via FFmpeg..."):
                    process_video_clip(
                        input_video=source_video_path,
                        output_path=output_video_path,
                        make_vertical=convert_vertical,
                        tts_audio_path=audio_path
                    )

                st.divider()
                st.subheader("🔥 Your Rendered Viral Short")
                if os.path.exists(output_video_path):
                    st.video(output_video_path)
                    with open(output_video_path, "rb") as f:
                        st.download_button(
                            label="📥 Download Viral Short",
                            data=f,
                            file_name="viral_short_makeover.mp4",
                            mime="video/mp4",
                            use_container_width=True
                        )
                else:
                    st.error("Video processing failed to generate output file.")

            except Exception as e:
                st.error(f"An error occurred during processing: {e}")
    
