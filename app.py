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
    page_title="AI Viral Shorts Extractor & Script Makeover",
    page_icon="🎬",
    layout="wide"
)

# ==========================================
# 1. MASTER DICTIONARY OF ALL 7 SCRIPT MODES
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
    "Hindi / Hinglish Male (Madhur - Energetic)": {
        "edge": "hi-IN-MadhurNeural",
        "gemini": "Puck",
        "gtts_lang": "hi",
        "gtts_tld": "co.in"
    },
    "Hindi / Hinglish Female (Swara - Clear)": {
        "edge": "hi-IN-SwaraNeural",
        "gemini": "Aoede",
        "gtts_lang": "hi",
        "gtts_tld": "co.in"
    },
    "Indian English Male (Prabhat - Crisp)": {
        "edge": "en-IN-PrabhatNeural",
        "gemini": "Charon",
        "gtts_lang": "en",
        "gtts_tld": "co.in"
    },
    "Indian English Female (Neerja - Expressive)": {
        "edge": "en-IN-NeerjaNeural",
        "gemini": "Kore",
        "gtts_lang": "en",
        "gtts_tld": "co.in"
    },
    "US English Male (Christopher - Viral/Deep)": {
        "edge": "en-US-ChristopherNeural",
        "gemini": "Fenrir",
        "gtts_lang": "en",
        "gtts_tld": "com"
    }
}

# ==========================================
# 2. SIDEBAR SETTINGS & DYNAMIC MODE UI
# ==========================================
with st.sidebar:
    st.header("Settings")
    gemini_api_key = st.text_input("Gemini API Key", type="password")

    workflow_mode = st.selectbox(
        "Mode / Script Style",
        ["Auto Multi-Shorts Extractor (Generate 3+ Separate Shorts)"] + list(SCRIPT_STYLES.keys())
    )

    convert_vertical = st.checkbox(
        "📐 Auto-convert each Short to 9:16 Vertical (720x1280)",
        value=True
    )

    if workflow_mode == "Auto Multi-Shorts Extractor (Generate 3+ Separate Shorts)":
        audio_choice = st.radio(
            "🔊 Audio for Each Generated Short",
            [
                "Keep Original Video Audio Only (Pure Extracted Shorts, No Captions)",
                "Overlay AI Voiceover on Each Short (Select Style(s) Below)"
            ],
            index=1
        )

        if "Overlay AI Voiceover" in audio_choice:
            extractor_selection_type = st.radio(
                "🎯 How do you want to apply styles?",
                ["Single Style for All Extracted Shorts", "Multiple Styles (Compare/Makeover across modes)"],
                index=0
            )

            if extractor_selection_type == "Single Style for All Extracted Shorts":
                chosen_style = st.selectbox(
                    "🎨 Select Script Makeover Style",
                    options=list(SCRIPT_STYLES.keys()),
                    index=0
                )
                selected_extractor_styles = [chosen_style]
            else:
                selected_extractor_styles = st.multiselect(
                    "🎨 Select Script Makeover Styles (Pick 1 or more)",
                    options=list(SCRIPT_STYLES.keys()),
                    default=list(SCRIPT_STYLES.keys())[:2]
                )
        else:
            selected_extractor_styles = []
    else:
        audio_choice = "Overlay AI Voiceover on Each Short (Select Style(s) Below)"
        selected_extractor_styles = [workflow_mode]

    st.divider()
    tts_engine_preference = st.selectbox(
        "⚙️ Primary Voice Engine",
        [
            "Edge-TTS First (Fastest, No Gemini Quota Used)",
            "Gemini 2.5 Native TTS First (Auto-Fallback to Edge/gTTS)"
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
# 3. BULLETPROOF 3-TIER TTS ENGINE (NO CLIENTERROR)
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
    prefer_gemini: bool = False
) -> bool:
    """
    3-Tier TTS Generator:
    1. Optional Gemini 2.5 Flash TTS (with proper PCM wave framing & rate-limit handling)
    2. Subprocess CLI Edge-TTS (avoids Streamlit asyncio loop clash)
    3. gTTS + FFmpeg speed boost fallback (guarantees audio even if Edge-TTS 403 blocks IP)
    """
    clean_text = clean_script_for_tts(text)

    # --- TIER 1: GEMINI 2.5 NATIVE TTS (If selected) ---
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
                time.sleep(2)  # Prevent 429 ClientError on back-to-back shorts
                return True
        except Exception as e:
            st.caption(f"ℹ️ Gemini TTS skipped ({type(e).__name__}), using Edge-TTS engine...")

    # --- TIER 2: SUBPROCESS CLI EDGE-TTS (Bypasses asyncio loop errors) ---
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

    # --- TIER 3: gTTS FALLBACK (Never blocked on Cloud IPs) ---
    try:
        raw_gtts_path = output_audio_path + "_raw.mp3"
        tts = gTTS(text=clean_text, lang=voice_cfg["gtts_lang"], tld=voice_cfg["gtts_tld"], slow=False)
        tts.save(raw_gtts_path)

        # Speed up gTTS slightly (1.12x) via FFmpeg so it sounds punchy for Shorts
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
def timestamp_to_seconds(ts_str: str) -> float:
    parts = [float(p) for p in str(ts_str).strip().split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    elif len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return float(parts[0])


def process_video_clip(
    input_video: str,
    start_sec: float,
    end_sec: float,
    output_path: str,
    make_vertical: bool = True,
    tts_audio_path: str = None
):
    duration = max(1.0, end_sec - start_sec)
    vf_filter = (
        "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280"
        if make_vertical else "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    )

    if tts_audio_path and os.path.exists(tts_audio_path):
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_sec),
            "-t", str(duration),
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
            "-ss", str(start_sec),
            "-t", str(duration),
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
            "-ss", str(start_sec),
            "-t", str(duration),
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


def analyze_video_with_gemini(api_key: str, video_path: str, is_multi_extractor: bool, styles_list: list, lang_choice: str):
    clean_key = api_key.strip()

    if not styles_list:
        prompt = """
        You are an expert viral video editor. Watch the entire video carefully and identify 3 to 5 separate, 
        high-retention viral short segments (each 15 to 40 seconds long).
        Return ONLY valid JSON:
        [
          {
            "short_number": 1,
            "title": "Catchy Viral Title",
            "start_time": "00:05",
            "end_time": "00:25",
            "visual_summary": "What happens visually in this segment",
            "scripts_by_mode": {}
          }
        ]
        """
    else:
        style_rules = "\n".join([f"- **{style}**: {SCRIPT_STYLES[style]}" for style in styles_list])
        json_mode_keys = ",\n            ".join(
            [f'"{style}": "Write the full spoken voiceover script here in {style} style..."' for style in styles_list]
        )
        clip_count_instruction = (
            "Extract 3 to 5 separate, high-retention viral short segments (15 to 40 seconds each) from the video."
            if is_multi_extractor
            else "Select the single best 15 to 45 second viral segment (or full clip if already short) from the video."
        )

        prompt = f"""
        You are an expert viral Shorts producer and scriptwriter.
        Watch the entire video carefully, observing the exact visual actions, reactions, and pacing.
        
        Task 1: {clip_count_instruction}
        Task 2: For EACH clip, make over the audio script based on what is visibly happening on screen using the following selected style(s):
        {style_rules}

        Language Requirement: Write the spoken script in {lang_choice}.
        Important: Write ONLY the spoken words. No stage directions, no markdown asterisks, and no speaker labels.

        Return ONLY valid JSON in this exact format:
        [
          {{
            "short_number": 1,
            "title": "Catchy Viral Hook Title",
            "start_time": "00:00",
            "end_time": "00:22",
            "visual_summary": "Brief description of what happens visually in this clip",
            "scripts_by_mode": {{
              {json_mode_keys}
            }}
          }}
        ]
        """

    st.info("📤 Uploading video to Gemini Vision for scene analysis...")

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
st.title("🎬 AI Multi-Shorts Extractor & Script Makeover Studio")
st.caption("Extract multiple viral shorts from any video and apply any script makeover mode with AI Voiceover.")

uploaded_video = st.file_uploader("Upload Source Video (MP4, MOV, MKV)", type=["mp4", "mov", "mkv", "webm"])

if uploaded_video:
    col_preview, col_info = st.columns([1, 2])
    with col_preview:
        st.video(uploaded_video)
    with col_info:
        st.markdown("### Active Configuration")
        st.write(f"**Workflow Mode:** `{workflow_mode}`")
        st.write(f"**9:16 Vertical Crop:** `{'Enabled (720x1280)' if convert_vertical else 'Disabled (Original Ratio)'}`")
        st.write(f"**Audio Mode:** `{audio_choice}`")
        if selected_extractor_styles:
            st.write("**Selected Makeover Style(s):**")
            for s in selected_extractor_styles:
                st.markdown(f"- ✨ `{s}`")
        else:
            st.write("**Selected Makeover Style(s):** `None (Keeping Original Audio)`")

    if st.button("🚀 Generate Viral Shorts!", type="primary", use_container_width=True):
        if not gemini_api_key:
            st.error("Please enter your Gemini API Key in the left sidebar.")
            st.stop()

        if "Overlay AI Voiceover" in audio_choice and not selected_extractor_styles:
            st.error("Please select at least one Script Makeover Style in the sidebar.")
            st.stop()

        with tempfile.TemporaryDirectory() as temp_dir:
            source_video_path = os.path.join(temp_dir, "input_video.mp4")
            with open(source_video_path, "wb") as f:
                f.write(uploaded_video.read())

            is_multi = (workflow_mode == "Auto Multi-Shorts Extractor (Generate 3+ Separate Shorts)")
            prefer_gemini_tts = ("Gemini 2.5 Native TTS" in tts_engine_preference)

            try:
                with st.spinner("🧠 Gemini is watching your video, finding viral moments, and writing custom scripts..."):
                    extracted_clips = analyze_video_with_gemini(
                        api_key=gemini_api_key,
                        video_path=source_video_path,
                        is_multi_extractor=is_multi,
                        styles_list=selected_extractor_styles,
                        lang_choice=language_instruction
                    )

                st.success(f"✅ Extracted {len(extracted_clips)} Viral Short(s)!")

                for clip in extracted_clips:
                    short_num = clip.get("short_number", 1)
                    title = clip.get("title", f"Short #{short_num}")
                    start_str = clip.get("start_time", "00:00")
                    end_str = clip.get("end_time", "00:20")
                    visual_summary = clip.get("visual_summary", "")
                    scripts_dict = clip.get("scripts_by_mode", {})

                    start_sec = timestamp_to_seconds(start_str)
                    end_sec = timestamp_to_seconds(end_str)

                    st.divider()
                    st.subheader(f"🔥 Short #{short_num}: {title} (`{start_str}` - `{end_str}`)")
                    st.caption(f"**Visual Scene:** {visual_summary}")
                                        # Case A: Keep Original Audio Only
                    if not selected_extractor_styles or "Keep Original Video Audio Only" in audio_choice:
                        out_video_path = os.path.join(temp_dir, f"short_{short_num}_original.mp4")
                        with st.spinner(f"Cutting Short #{short_num} (Original Audio)..."):
                            process_video_clip(
                                input_video=source_video_path,
                                start_sec=start_sec,
                                end_sec=end_sec,
                                output_path=out_video_path,
                                make_vertical=convert_vertical,
                                tts_audio_path=None
                            )
                        if os.path.exists(out_video_path):
                            v_col, d_col = st.columns([1, 2])
                            with v_col:
                                st.video(out_video_path)
                            with d_col:
                                with open(out_video_path, "rb") as vf:
                                    st.download_button(
                                        label=f"⬇️ Download Short #{short_num} (Original Audio)",
                                        data=vf.read(),
                                        file_name=f"short_{short_num}_original.mp4",
                                        mime="video/mp4",
                                        key=f"dl_orig_{short_num}"
                                    )

                    # Case B: Overlay AI Voiceover for Each Selected Mode
                    else:
                        for mode_idx, (mode_name, script_text) in enumerate(scripts_dict.items()):
                            with st.expander(f"🎙️ Mode: {mode_name}", expanded=True):
                                tts_path = os.path.join(temp_dir, f"tts_{short_num}_{mode_idx}.mp3")
                                out_video_path = os.path.join(temp_dir, f"short_{short_num}_mode_{mode_idx}.mp4")

                                with st.spinner(f"Generating '{mode_name}' voiceover & rendering Short #{short_num}..."):
                                    generate_tts_bulletproof(
                                        text=script_text,
                                        voice_cfg=selected_voice_cfg,
                                        output_audio_path=tts_path,
                                        api_key=gemini_api_key,
                                        prefer_gemini=prefer_gemini_tts
                                    )
                                    process_video_clip(
                                        input_video=source_video_path,
                                        start_sec=start_sec,
                                        end_sec=end_sec,
                                        output_path=out_video_path,
                                        make_vertical=convert_vertical,
                                        tts_audio_path=tts_path
                                    )

                                c1, c2 = st.columns([1, 2])
                                with c1:
                                    if os.path.exists(out_video_path):
                                        st.video(out_video_path)
                                with c2:
                                    st.markdown("**Generated Makeover Script:**")
                                    st.info(script_text)
                                    if os.path.exists(out_video_path):
                                        with open(out_video_path, "rb") as vf:
                                            st.download_button(
                                                label=f"⬇️ Download Short #{short_num} ({mode_name.split('(')[0].strip()})",
                                                data=vf.read(),
                                                file_name=f"short_{short_num}_{mode_idx}.mp4",
                                                mime="video/mp4",
                                                key=f"dl_{short_num}_{mode_idx}"
                                            )

            except Exception as e:
                st.error(f"Error processing video: {e}")


      
