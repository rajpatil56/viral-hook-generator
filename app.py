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
    # --- GEMINI NATIVE STUDIO VOICES ---
    "Gemini Native: Charon (Deep, Crisp Male)": {
        "engine": "gemini",
        "gemini_voice": "Charon",
        "edge": "en-IN-PrabhatNeural",
        "gtts_lang": "en",
        "gtts_tld": "co.in"
    },
    "Gemini Native: Fenrir (Viral, Deep US Male)": {
        "engine": "gemini",
        "gemini_voice": "Fenrir",
        "edge": "en-US-ChristopherNeural",
        "gtts_lang": "en",
        "gtts_tld": "com"
    },
    "Gemini Native: Puck (Energetic Male)": {
        "engine": "gemini",
        "gemini_voice": "Puck",
        "edge": "hi-IN-MadhurNeural",
        "gtts_lang": "hi",
        "gtts_tld": "co.in"
    },
    "Gemini Native: Aoede (Clear Female)": {
        "engine": "gemini",
        "gemini_voice": "Aoede",
        "edge": "hi-IN-SwaraNeural",
        "gtts_lang": "hi",
        "gtts_tld": "co.in"
    },
    "Gemini Native: Kore (Expressive Female)": {
        "engine": "gemini",
        "gemini_voice": "Kore",
        "edge": "en-IN-NeerjaNeural",
        "gtts_lang": "en",
        "gtts_tld": "co.in"
    },
    # --- EDGE-TTS MULTILINGUAL NEURAL VOICES ---
    "Edge-TTS: Hindi Male (Madhur)": {
        "engine": "edge",
        "gemini_voice": "Puck",
        "edge": "hi-IN-MadhurNeural",
        "gtts_lang": "hi",
        "gtts_tld": "co.in"
    },
    "Edge-TTS: Hindi Female (Swara)": {
        "engine": "edge",
        "gemini_voice": "Aoede",
        "edge": "hi-IN-SwaraNeural",
        "gtts_lang": "hi",
        "gtts_tld": "co.in"
    },
    "Edge-TTS: Marathi Male (Manohar)": {
        "engine": "edge",
        "gemini_voice": "Charon",
        "edge": "mr-IN-ManoharNeural",
        "gtts_lang": "mr",
        "gtts_tld": "co.in"
    },
    "Edge-TTS: Marathi Female (Aarohi)": {
        "engine": "edge",
        "gemini_voice": "Kore",
        "edge": "mr-IN-AarohiNeural",
        "gtts_lang": "mr",
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
            "Overlay AI Voiceover on Video Pipeline",
            "Keep Original Video Audio Only"
        ],
        index=0
    )

    st.divider()
    selected_voice_label = st.selectbox("🎙️ Voice Model (Gemini AI & Multilingual)", list(VOICE_OPTIONS.keys()))
    selected_voice_cfg = VOICE_OPTIONS[selected_voice_label]

    language_instruction = st.selectbox(
        "🌐 Script Output Language",
        [
            "Hinglish (Roman Hindi + English Mix - Best for Viral Shorts)",
            "Marathi (मराठी)",
            "Pure Hindi (Devanagari)",
            "English"
        ]
    )


# ==========================================
# 3. PIPELINE TTS GENERATOR (GEMINI & EDGE)
# ==========================================
def clean_script_for_tts(text: str) -> str:
    """Removes markdown, stage directions, and emojis that trigger TTS errors."""
    text = re.sub(r"\[.*?\]|\(.*?\)|\*+", "", text)
    text = re.sub(r"^(Narrator|Voiceover|Speaker|Audio|Script)\s*:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text or "Watch this amazing moment right now!"


def generate_pipeline_tts(
    text: str,
    voice_cfg: dict,
    output_audio_path: str,
    api_key: str
) -> bool:
    """
    Pipeline TTS Execution:
    1. Gemini 3.8 Flash TTS Pipeline (Charon, Fenrir, Puck, Aoede, Kore)
    2. Edge-TTS Multilingual Fallback
    3. gTTS Fallback
    """
    clean_text = clean_script_for_tts(text)

    # --- PIPELINE TIER 1: GEMINI NATIVE TTS API ---
    if voice_cfg["engine"] == "gemini" and USING_NEW_SDK and api_key:
        try:
            client = genai.Client(api_key=api_key.strip())
            # Using the native Gemini Interactions / TTS generation pipeline
            interaction = client.interactions.create(
                model="gemini-3.8-flash-tts",
                input=[{
                    "type": "user_input",
                    "content": [{
                        "type": "text",
                        "text": f"Read this viral video voiceover script with high energy, natural pacing, and sharp dramatic pauses: {clean_text}"
                    }]
                }],
                response_format={"type": "audio"},
                generation_config={
                    "speech_config": [
                        {"voice": voice_cfg["gemini_voice"]}
                    ]
                }
            )
            
            if hasattr(interaction, "output_audio") and interaction.output_audio:
                pcm_bytes = base64.b64decode(interaction.output_audio.data)
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
                    return True
        except Exception as e:
            st.caption(f"ℹ️ Gemini Native TTS pipeline note ({type(e).__name__}), shifting to Edge-TTS neural fallback...")

    # --- PIPELINE TIER 2: EDGE-TTS NEURAL VOICES ---
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

    # --- PIPELINE TIER 3: GTTS FALLBACK ---
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
        st.error(f"All TTS pipeline tiers failed: {e}")

    return False


# ==========================================
# 4. VIDEO PROCESSING & GEMINI ANALYSIS PIPELINE
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
    Watch the uploaded video frame by frame, observing the exact visual actions, expressions, and pacing.
    
    Task: Write a high-retention voiceover script tailored precisely to what happens visually using this style:
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

    st.info("📤 Step 1/3: Uploading video to Gemini 3.8 Flash Vision for scene & action analysis...")

    if USING_NEW_SDK:
        client = genai.Client(api_key=clean_key)
        uploaded_file = client.files.upload(file=video_path)
        while uploaded_file.state.name == "PROCESSING":
            time.sleep(2)
            uploaded_file = client.files.get(name=uploaded_file.name)
        if uploaded_file.state.name == "FAILED":
            raise RuntimeError("Gemini video processing failed.")

        response = client.models.generate_content(
            model="gemini-3.8-flash",
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

        model = genai_legacy.GenerativeModel("gemini-3.8-flash")
        response = model.generate_content([uploaded_file, prompt])
        raw_text = response.text.strip()

    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[-1]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3].strip()

    return json.loads(raw_text)


# ==========================================
# 5. MAIN APP UI & EXECUTION PIPELINE
# ==========================================
st.title("🎬 AI Script Makeover & Voice Pipeline Studio")
st.caption("Pipeline: Gemini Video Vision Analysis ➔ Custom Viral Script ➔ Gemini 3.8 Flash Native Studio Voices.")

uploaded_video = st.file_uploader("Upload Video (MP4, MOV, MKV, WebM)", type=["mp4", "mov", "mkv", "webm"])

if uploaded_video:
    col_preview, col_info = st.columns([1, 2])
    with col_preview:
        st.video(uploaded_video)
    with col_info:
        st.markdown("### Pipeline Configuration")
        st.write(f"**Script Style:** `{selected_style}`")
        st.write(f"**9:16 Vertical Crop:** `{'Enabled (720x1280)' if convert_vertical else 'Disabled'}`")
        st.write(f"**Selected Voice Engine:** `{selected_voice_label}`")
        st.write(f"**Audio Mode:** `{audio_choice}`")

    if st.button("🚀 Run AI Video-to-Voice Pipeline", type="primary", use_container_width=True):
        if not gemini_api_key:
            st.error("Please enter your Gemini API Key in the left sidebar.")
            st.stop()

        with tempfile.TemporaryDirectory() as temp_dir:
            source_video_path = os.path.join(temp_dir, "input_video.mp4")
            with open(source_video_path, "wb") as f:
                f.write(uploaded_video.read())

            try:
                # PIPELINE STAGE 1: Gemini Vision Scene Analysis & Script Generation
                with st.spinner("🧠 Pipeline Stage 1/3: Gemini 3.8 Flash analyzing video frames & writing script..."):
                    analysis_result = analyze_video_with_gemini(
                        api_key=gemini_api_key,
                        video_path=source_video_path,
                        style_name=selected_style,
                        lang_choice=language_instruction
                    )

                title = analysis_result.get("title", "Viral Short")
                visual_summary = analysis_result.get("visual_summary", "")
                script_text = analysis_result.get("script", "")

                st.success("✅ Script successfully generated from video actions!")
                
                st.subheader(f"📝 Generated Script ({selected_style})")
                st.info(script_text)
                st.caption(f"**Visual Context Captured:** {visual_summary}")

                audio_path = None
                if "Pipeline" in audio_choice:
                    audio_path = os.path.join(temp_dir, "voiceover.mp3")
                    
                    # PIPELINE STAGE 2: Gemini Native Voice Synthesis Pipeline
                    with st.spinner(f"🎙️ Pipeline Stage 2/3: Converting script into natural speech via `{selected_voice_label}`..."):
                        success_tts = generate_pipeline_tts(
                            text=script_text,
                            voice_cfg=selected_voice_cfg,
                            output_audio_path=audio_path,
                            api_key=gemini_api_key
                        )
                        if not success_tts:
                            st.warning("⚠️ Voice generation encountered a snag. Exporting video with original audio.")
                            audio_path = None

                output_video_path = os.path.join(temp_dir, "output_viral_short.mp4")
                
                # PIPELINE STAGE 3: FFmpeg Audio Mixing & Formatting
                with st.spinner("🎞️ Pipeline Stage 3/3: Mixing AI voiceover audio & formatting video via FFmpeg..."):
                    process_video_clip(
                        input_video=source_video_path,
                        output_path=output_video_path,
                        make_vertical=convert_vertical,
                        tts_audio_path=audio_path
                    )

                st.divider()
                st.subheader("🔥 Your Final Pipeline-Rendered Viral Short")
                if os.path.exists(output_video_path):
                    st.video(output_video_path)
                    with open(output_video_path, "rb") as f:
                        st.download_button(
                            label="📥 Download Pipeline Short",
                            data=f,
                            file_name="viral_short_pipeline.mp4",
                            mime="video/mp4",
                            use_container_width=True
                        )
                else:
                    st.error("Video processing pipeline failed to generate output file.")

            except Exception as e:
                st.error(f"Pipeline error occurred during execution: {e}")
                
