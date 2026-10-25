import os
import glob
import time
import asyncio
import subprocess
import streamlit as st
import edge_tts
from google import genai
from google.genai import types
import random

# --- EXACT SIDHU PAAJI COMMENTARY DATA MODULE ---
CORE_PHRASES = [
    "ओए गुरु!", "ठोको ताली!", "चक दे फट्टे, नप दे किल्ली!", "छा गया मुंडा!",
    "गगनचुंबी छक्का!", "धूल चटा दी", "आत्मा निकाल दी", "तांडव मचा दिया",
    "भगा-भगा के मारा", "पेपर लीक", "भाई कंट्रोवर्सी क्यों करते हो",
]

EXTRA_PHRASES = {
    "hook":    ["ओए गुरु, क्या बात है!", "ओए गुरु, तांडव!", "शेर आया शेर!", "हो गया कमाल!"],
    "six":     ["गगनचुंबी छक्का!", "गेंद स्टेडियम के बाहर, गुरु!", "सीधा आसमान में!", "बल्ला बोला, बॉल रोई!"],
    "praise": ["छा गया मुंडा!", "क्या खिलाड़ी है, गुरु!", "शेर दा पुत्तर!", "बादशाह है बादशाह!"],
    "roast":  ["धूल चटा दी", "आत्मा निकाल दी", "पेपर लीक", "भाई कंट्रोवर्सी क्यों करते हो", "बोलती बंद कर दी"],
    "closer": ["ठोको ताली!", "चक दे फट्टे, नप दे किल्ली!", "तिरंगा लहरा दिया, गुरु!", "जय हिंद, ठोको ताली!"],
}

DELIVERY = (
    "Loud, booming, laughing Punjabi-flavoured Hindi. Theatrical pauses before the punch word, "
    "rising energy at every sentence end, 'गुरु' as a filler, rhetorical questions to the audience, "
    "Punjabi words mixed in (मुंडा, फट्टे, शेर, पुत्तर). Never calm, never news-anchor flat."
)

RULES = (
    "Use 3-4 catchphrases total, never the same phrase twice. Facts (runs, balls, scores, names) must be "
    "visible in the video or given by the user; never invent stats. Keep it playful, no abuse, no real "
    "personal attacks; rivals are roasted on the cricket field only."
)

FEW_SHOT = [
    "ओए गुरु, तांडव मचा दिया! छा गया मुंडा, बत्तीस गेंद में बयासी रन, गगनचुंबी छक्के भगा-भगा के मारे! "
    "अफ़ग़ानिस्तान की आत्मा निकाल दी। भाई कंट्रोवर्सी क्यों करते हो, खेल देखो! ठोको ताली!",
    "ओए गुरु! गोल्ड जीत लिया! पाकिस्तान को धूल चटा दी, अभिषेक और तिलक ने भगा-भगा के मारा। "
    "चक दे फट्टे, नप दे किल्ली! ठोको ताली!",
    "ओए गुरु, मरते-मरते बचे! सिर्फ़ दो रन से जीत। जापान ने तो पेपर लीक कर दिया था हमारा! ठोको ताली!",
]

def get_sidhu_style_guide(lang_note="Devanagari"):
    core = "\n".join(f'- "{p}"' for p in CORE_PHRASES)
    ex = "\n".join(f"  • {s}" for s in FEW_SHOT)
    bank = "\n".join(f"  {k}: " + " | ".join(v) for k, v in EXTRA_PHRASES.items())
    return f"""
CRITICAL PERSONA: Navjot Singh Sidhu ("Sidhu Paaji") live commentary.
DELIVERY: {DELIVERY}

MANDATORY SIGNATURE PHRASES (use 3-4, natural, none repeated):
{core}

EXTRA PHRASE BANK BY MOMENT:
{bank}

SCENE-SYNCED PACING (chronological, follow the visuals):
1. 0-25%  HOOK (<=6 words): explosive reaction to the opening visual, e.g. "ओए गुरु, तांडव मचा दिया!"
2. 25-50% HERO LINE: the main player/action on screen ("छा गया मुंडा", "भगा-भगा के मारा", "गगनचुंबी छक्का!")
3. 50-75% TWIST/ROAST: rival, critic or drama ("धूल चटा दी", "पेपर लीक", "भाई कंट्रोवर्सी क्यों करते हो")
4. 75-100% CLOSER: theatrical finish landing exactly as video ends ("ठोको ताली!" / "चक दे फट्टे, नप दे किल्ली!")

EXAMPLES OF THE TARGET STYLE ({lang_note}):
{ex}

RULES: {RULES}
"""

st.set_page_config(page_title="Multimodal Video Hook Generator", layout="wide")
st.title("🎬 Direct Multimodal Video Hook Overlay (Sidhu Paaji Master Edition)")

# Sidebar Configuration
st.sidebar.header("Settings")
gemini_api_key = st.sidebar.text_input("Gemini API Key", type="password", help="Get a key from Google AI Studio")

# Integrated Voice Roster (Featuring Algenib & Fenrir Sidhu Paaji Voices)
VOICE_OPTIONS = {
    "Gemini - Algenib (Sidhu Paaji / Gravelly & Booming Male)": {
        "engine": "gemini",
        "code": "Algenib",
        "lang": "Punjabi-flavored Hindi (Sidhu Paaji style)",
        "script_type": "Devanagari script",
        "director_note": "Say in a loud, booming, gravelly, laughing Punjabi cricket commentator voice like Navjot Singh Sidhu Paaji with high projection and theatrical energy: "
    },
    "Gemini - Fenrir (Sidhu Paaji / Excitable & Passionate Male)": {
        "engine": "gemini",
        "code": "Fenrir",
        "lang": "Punjabi-flavored Hindi (Sidhu Paaji style)",
        "script_type": "Devanagari script",
        "director_note": "Speak in an extremely energetic, hyped North-Indian Punjabi dost-wala commentator tone: "
    },
    "Gemini - Kore (Hindi / Energetic)": {"engine": "gemini", "code": "Kore", "lang": "Hindi", "script_type": "Devanagari script"},
    "Gemini - Kore (Marathi / Energetic)": {"engine": "gemini", "code": "Kore", "lang": "Marathi", "script_type": "Devanagari script"},
    "Gemini - Kore (English)": {"engine": "gemini", "code": "Kore", "lang": "English", "script_type": "English text"},
    "Gemini - Aoede (Hindi / Deep)": {"engine": "gemini", "code": "Aoede", "lang": "Hindi", "script_type": "Devanagari script"},
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

voice_speed = st.sidebar.slider(
    "⚡ Voice Delivery Speed Multiplier",
    min_value=0.85,
    max_value=1.50,
    value=1.00,
    step=0.05,
    help="1.00x is natural synced speed."
)

auto_fit_audio = st.sidebar.checkbox(
    "🔄 Auto-fit voice duration to match full video",
    value=True,
    help="Stretches or compresses the audio slightly so the voiceover starts at 0s and finishes right as the video ends."
)

script_style = st.sidebar.selectbox(
    "Hook / Script Style",
    [
        "Sidhu Paaji Commentary (Oye Guru! Thoko Taali!)",
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

            # 3. Multimodal Analysis using Gemini 3.6 Flash
            st.write(f"🤖 Gemini 3.6 Flash is analyzing video & writing a structured **{script_style}** script in **{selected_voice_info['lang']}**...")

            target_lang = selected_voice_info["lang"]
            script_type = selected_voice_info["script_type"]
            target_words = max(12, int(video_duration * 2.4 * voice_speed))

            # Restored all style mode options
            if script_style == "Sidhu Paaji Commentary (Oye Guru! Thoko Taali!)":
                style_guide = get_sidhu_style_guide(lang_note=script_type)
            elif script_style == "Soul Lines Paaji Mode (Hook-Hero-Roast-Closer)":
                style_guide = """
                CRITICAL PERSONA: A loud, hyped, dost-wala male narrator.
                CHRONOLOGICAL SCENE-SYNCED PACING:
                - [0-25%]: HOOK reacting to opening visual.
                - [25-50%]: HERO LINE describing main action.
                - [50-75%]: TWIST / ROAST reacting to match drama.
                - [75-100%]: CLOSER wrapping up right as the video ends.
                """
            elif script_style == "Viral Explanation Mode (Hook-Scoop-Twist)":
                style_guide = """
                CRITICAL STYLE: You MUST use the exact 3-part 'Hook-Scoop-Twist' anatomy synced chronologically to the video:
                1. The Hook (Beginning of video): Exaggerated description + set up situation.
                2. The Scoop (Middle of video): Background detail matching middle action.
                3. The Twist / Punchline (End of video): Quirky silver lining or funny closer.
                """
            elif script_style == "High-Dopamine Viral Opening":
                style_guide = "Style: High-Dopamine Viral Opening. Deliver an electrifying, fast-paced statement that immediately hooks the viewer within the first 2 seconds."
            elif script_style == "Cinematic Storytelling":
                style_guide = "Style: Cinematic Storytelling. Narrate the video with a dramatic, movie-trailer voice, emphasizing epic scaling and visual impact."
            elif script_style == "Humorous & Punchy":
                style_guide = "Style: Humorous & Punchy. Poke fun at the visuals with witty sarcasm and light-hearted comedy."
            else:
                style_guide = f"Style: {script_style}. Ensure narration follows the beginning, middle, and end of the video chronologically."

            prompt = f"""
            You are a master viral video content creator and legendary cricket commentator.
            Watch the visuals, movement, actions, and exact timeline of this attached {video_duration:.1f}-second video file.
            Write a high-converting voiceover script that stays strictly in sync with what is visually happening from start (0s) to finish ({video_duration:.1f}s).

            {style_guide}

            CRITICAL LANGUAGE & TIMING CONSTRAINTS:
            1. LANGUAGE REQUIREMENT: You MUST write the ENTIRE script natively in {target_lang} using standard {script_type}. YOU MUST RESPOND UNMISTAKABLY IN LANGUAGE <{target_lang}>.
            2. EXACT LENGTH FOR FULL VIDEO COVERAGE: The video is {video_duration:.1f} seconds long. Write approximately **{target_words} words** in {target_lang} so that when spoken at normal 1x speed, the voiceover covers the ENTIRE video and does not finish early.
            3. Output ONLY the plain text script to be spoken in {target_lang}. No markdown, no timestamps, no translation notes, no scene instructions, no labels.
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

            # 4. Clean Audio Voice Synthesis Path
            if selected_voice_info["engine"] == "gemini":
                st.write(f"🎙️ Generating native AI dub using Gemini ({selected_voice_info['code']}) voice...")
                director_prefix = selected_voice_info.get("director_note", "")
                tts_input = f"{director_prefix}{creative_script}" if director_prefix else creative_script

                try:
                    audio_response = generate_content_with_retry(
                        client,
                        model="gemini-3.8-flash-tts",
                        contents=[tts_input],
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
                needed_tempo = audio_duration / video_duration
                final_tempo = max(0.85, min(needed_tempo, 1.35))
            else:
                if audio_duration / voice_speed > video_duration:
                    final_tempo = min(audio_duration / video_duration, 1.50)
                else:
                    final_tempo = voice_speed

            st.write(f"⚡ Applied Audio Speed Multiplier: **{final_tempo:.2f}x**")

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

            # 6. Mux Final Audio/Video (Full Video Preserved)
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

            status.update(label="✨ Sidhu Paaji Master Hook Successfully Overlaid (100% Video Preserved)!", state="complete", expanded=False)

        st.subheader("🔥 Final Video Output")
        st.video(output_video)
