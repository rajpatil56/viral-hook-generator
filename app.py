import os
import glob
import time
import asyncio
import subprocess
import streamlit as st
import edge_tts
from google import genai
from google.genai import types

# Import Soul Lines voiceover specifications if soullines_voice.py is present
try:
    from soullines_voice import VOICE_SPEC
except ImportError:
    VOICE_SPEC = ""

st.set_page_config(page_title="Multimodal Video Hook Generator", layout="wide")
st.title("🎬 Direct Multimodal Video Hook Overlay")

# Sidebar Configuration
st.sidebar.header("Settings")
gemini_api_key = st.sidebar.text_input("Gemini API Key", type="password", help="Get a key from Google AI Studio")

# Integrated Voice Roster (Set to 0% base rate so 1.0x is true 1.0x natural speed)
VOICE_OPTIONS = {
    "Paaji Voice (Soul Lines - Madhur Hype)": {
        "engine": "edge",
        "code": "hi-IN-MadhurNeural",
        "lang": "Hindi",
        "script_type": "Devanagari script",
        "rate": "+0%",     # Keep base at 0% so 1.0x slider = true 1x speed
        "pitch": "+15Hz",  # Energetic Paaji pitch without rushing the tempo
    },
    "Gemini - Kore (Hindi / Energetic)": {"engine": "gemini", "code": "Kore", "lang": "Hindi", "script_type": "Devanagari script"},
    "Gemini - Kore (Marathi / Energetic)": {"engine": "gemini", "code": "Kore", "lang": "Marathi", "script_type": "Devanagari script"},
    "Gemini - Kore (English)": {"engine": "gemini", "code": "Kore", "lang": "English", "script_type": "English text"},
    "Gemini - Aoede (Hindi / Deep)": {"engine": "gemini", "code": "Aoede", "lang": "Hindi", "script_type": "Devanagari script"},
    "Gemini - Fenrir (Hindi / Bold)": {"engine": "gemini", "code": "Fenrir", "lang": "Hindi", "script_type": "Devanagari script"},
    "Gemini - Charon (Hindi)": {"engine": "gemini", "code": "Charon", "lang": "Hindi", "script_type": "Devanagari script"},
    "Gemini - Charon (Marathi)": {"engine": "gemini", "code": "Charon", "lang": "Marathi", "script_type": "Devanagari script"},
    "Gemini - Puck (Hindi)": {"engine": "gemini", "code": "Puck", "lang": "Hindi", "script_type": "Devanagari script"},
    "Gemini - Puck (Marathi)": {"engine": "gemini", "code": "Puck", "lang": "Marathi", "script_type": "Devanagari script"},
    "Edge - Hindi Male (Madhur Standard)": {"engine": "edge", "code": "hi-IN-MadhurNeural", "lang": "Hindi", "script_type": "Devanagari script", "rate": "+0%", "pitch": "+0Hz"},
    "Edge - Hindi Female (Swara)": {"engine": "edge", "code": "hi-IN-SwaraNeural", "lang": "Hindi", "script_type": "Devanagari script", "rate": "+0%", "pitch": "+0Hz"},
    "Edge - Marathi Female (Aarohi)": {"engine": "edge", "code": "mr-IN-AarohiNeural", "lang": "Marathi", "script_type": "Devanagari script", "rate": "+0%", "pitch": "+0Hz"},
    "Edge - English Male (Guy)": {"engine": "edge", "code": "en-US-GuyNeural", "lang": "English", "script_type": "English text", "rate": "+0%", "pitch": "+0Hz"},
}

selected_voice_label = st.sidebar.selectbox("Voice Model & Language", list(VOICE_OPTIONS.keys()))
selected_voice_info = VOICE_OPTIONS[selected_voice_label]

# Speed multiplier now defaults to 1.00x (and allows slowing down to 0.85x if needed)
voice_speed = st.sidebar.slider(
    "⚡ Voice Delivery Speed Multiplier",
    min_value=0.85,
    max_value=1.50,
    value=1.00,
    step=0.05,
    help="1.00x is natural synced speed. Increase only if you want faster delivery."
)

auto_fit_audio = st.sidebar.checkbox(
    "🔄 Auto-fit voice duration to match full video",
    value=True,
    help="Stretches or compresses the audio slightly so the voiceover starts at 0s and finishes right as the video ends (prevents voice running ahead of video)."
)

script_style = st.sidebar.selectbox(
    "Hook / Script Style",
    [
        "Soul Lines Paaji Mode (Hook-Hero-Roast-Closer)",
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


def get_file_state_str(file_obj):
    state = getattr(file_obj, "state", None)
    if hasattr(state, "name"):
        return state.name
    return str(state).upper()


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


async def synthesize_voice(text: str, voice: str, output_path: str, rate: str = "+0%", pitch: str = "+15Hz"):
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
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

        with st.status("Analyzing Video & Building Synced Audio Overlay...", expanded=True) as status:

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

            # 3. Multimodal Analysis using Gemini 3.6 Flash (Timed to 1.0x Visual Pacing)
            st.write(f"🤖 Gemini 3.6 Flash is analyzing video & writing a synced **{script_style}** script in **{selected_voice_info['lang']}**...")

            target_lang = selected_voice_info["lang"]
            script_type = selected_voice_info["script_type"]
            # At 1.0x natural Hindi speaking speed, ~2.4 words/sec fills the full video without finishing early
            target_words = max(12, int(video_duration * 2.4 * voice_speed))

            if script_style == "Soul Lines Paaji Mode (Hook-Hero-Roast-Closer)":
                style_guide = f"""
                {VOICE_SPEC}

                CHRONOLOGICAL SCENE-SYNCED PACING (Match the video scenes in real time):
                - First Quarter (0% to 25% of video): HOOK (<=6 words) reacting to the opening visual! (e.g., "जीत लिया मैच और दे दिया जवाब!", "तांडव मचा दिया भाई!", "मरते-मरते बचे हैं आज!", "शर्मा जी के लौंडे ने भगा-भगा के मारा!", "गुद्दी लाल कर दी आज!")
                - Second Quarter (25% to 50% of video): HERO LINE describing the main action/player seen in the middle of the clip ("नमनधीर का तीर चल गया", "सरपंच ने बचा लिया", "संजू का बल्ला चल गया").
                - Third Quarter (50% to 75% of video): TWIST / ROAST reacting to the second half of the video ("लंका की लंका लगा दी", "पाकिस्तान को धूल चटा दी", "भाई कंट्रोवर्सी क्यों करते हो").
                - Final Quarter (75% to 100% of video): CLOSER wrapping up right as the video ends ("तो जीत तो जीत है!", "पूरी टीम ने जिम्मेदारी निभाई!").
                """
            elif script_style == "Viral Explanation Mode (Hook-Scoop-Twist)":
                style_guide = """
                CRITICAL STYLE: You MUST use the exact 3-part 'Hook-Scoop-Twist' anatomy synced chronologically to the video:
                1. The Hook (Beginning of video): Present an exaggerated, wholesome description of the subject in the video and set up the situation.
                2. The Scoop (Middle of video): Dive into the background detail matching the middle action in a casual tone.
                3. The Twist / Punchline (End of video): Highlight a quirky silver lining or funny closer right at the end.
                """
            else:
                style_guide = f"Style: {script_style}. Ensure the narration follows the beginning, middle, and end of the video chronologically."

            prompt = f"""
            You are a master viral video content creator.
            Watch the visuals, movement, actions, and exact timeline of this attached {video_duration:.1f}-second video file.
            Write a high-converting voiceover script that stays in sync with what is visually happening from start (0s) to finish ({video_duration:.1f}s).

            {style_guide}

            CRITICAL LANGUAGE & TIMING CONSTRAINTS:
            1. LANGUAGE REQUIREMENT: You MUST write the ENTIRE script natively in {target_lang} using standard {script_type}. YOU MUST RESPOND UNMISTAKABLY IN LANGUAGE <{target_lang}>.
            2. EXACT LENGTH FOR FULL VIDEO COVERAGE: The video is {video_duration:.1f} seconds long. Write approximately **{target_words} words** in {target_lang} so that when spoken at normal 1x speed, the voiceover covers the ENTIRE video and does not finish early.
            3. CHRONOLOGICAL SYNC: Do NOT rush to the ending in the first few words. Describe the events in the exact order they appear in the video.
            4. Output ONLY the plain text script to be spoken in {target_lang}. No markdown, no timestamps, no translation notes, no scene instructions, no labels.
            """

            try:
                response = generate_content_with_retry(
                    client,
                    model="gemini-3.6-flash",
                    contents=[video_file, prompt]
                )
            except Exception as err:
                st.error(f"Error generating script with gemini-3.6-flash: {err}")
                st.stop()

            try:
                client.files.delete(name=video_file.name)
            except Exception:
                pass

            creative_script = response.text.strip() if response.text else ""
            if not creative_script:
                st.error("Generated script was empty. Please try again.")
                st.stop()

            st.markdown(f"**Generated Script ({target_lang}):**\n> {creative_script}")

            # 4. Clean Audio Voice Synthesis Path (At true 1.0x base speed)
            if selected_voice_info["engine"] == "gemini":
                st.write(f"🎙️ Generating native AI dub using Gemini ({selected_voice_info['code']}) voice...")
                try:
                    audio_response = generate_content_with_retry(
                        client,
                        model="gemini-3.8-flash-tts",
                        contents=[creative_script],
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
                except Exception as err:
                    st.error(f"Gemini Audio Generation Error: {err}")
                    st.stop()

                audio_bytes = None
                if audio_response.candidates and audio_response.candidates[0].content.parts:
                    for part in audio_response.candidates[0].content.parts:
                        if part.inline_data and part.inline_data.mime_type and part.inline_data.mime_type.startswith("audio/"):
                            audio_bytes = part.inline_data.data
                            break

                if audio_bytes:
                    with open(script_audio, "wb") as f:
                        f.write(audio_bytes)
                else:
                    st.error("Gemini failed to return audio data. Please check your API key.")
                    st.stop()
            else:
                rate_str = selected_voice_info.get("rate", "+0%")
                pitch_str = selected_voice_info.get("pitch", "+15Hz")
                st.write(f"🎙️ Synthesizing voiceover via Edge-TTS ({selected_voice_info['code']}, pitch={pitch_str})...")
                asyncio.run(synthesize_voice(
                    text=creative_script,
                    voice=selected_voice_info["code"],
                    output_path=script_audio,
                    rate=rate_str,
                    pitch=pitch_str
                ))

            # 5. Sync Audio Duration & Loudness (-14.0 LUFS) Without Cutting Off Video
            audio_duration = get_file_duration(script_audio)
            st.write(f"🔊 Raw Voice Duration: **{audio_duration:.2f}s** | Target Video Duration: **{video_duration:.2f}s**")

            if auto_fit_audio:
                # Calculate exact ratio so audio neither races ahead (2x) nor gets cut off
                needed_tempo = audio_duration / video_duration
                # Clamp tempo between 0.85x and 1.35x so voice always sounds natural and synced
                final_tempo = max(0.85, min(needed_tempo, 1.35))
            else:
                # Strictly use the user's manual slider (1.0x default), unless audio is longer than video
                if audio_duration / voice_speed > video_duration:
                    final_tempo = min(audio_duration / video_duration, 1.50)
                else:
                    final_tempo = voice_speed

            st.write(f"⚡ Applied Audio Speed Multiplier: **{final_tempo:.2f}x**")

            # Use `apad` to pad silence at the end if audio finishes slightly early,
            # and trim at `video_duration` so the video is NEVER cut short!
            audio_filter = (
                f"atempo={final_tempo},"
                f"loudnorm=I=-14.0:TP=-1.5:LRA=11,"
                f"apad=whole_dur={video_duration}"
            )

            subprocess.run([
                "ffmpeg", "-y", "-i", script_audio,
                "-filter:a", audio_filter,
                "-t", str(video_duration),
                "-ar", "48000", "-ac", "2",
                fitted_audio
            ], capture_output=True, check=True)

            # 6. Mux Final Audio/Video (Removed `-shortest` so video is NEVER cut in half!)
            st.write("🎬 Muxing synced audio into full video via FFmpeg...")
            subprocess.run([
                "ffmpeg", "-y",
                "-i", temp_video,
                "-i", fitted_audio,
                "-c:v", "copy",
                "-c:a", "aac",
                "-ar", "48000",
                "-ac", "2",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-t", str(video_duration),
                output_video
            ], check=True)

            status.update(label="✨ Video Hook & Script Successfully Overlaid (100% Video Preserved)!", state="complete", expanded=False)

        st.subheader("🔥 Final Video Output")
        st.video(output_video)
