import os
import sys

# Force UTF-8 encoding to prevent ASCII codec errors with Unicode/Devanagari characters
os.environ["PYTHONIOENCODING"] = "utf-8"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import glob
import json
import time
import wave
import random
import asyncio
import subprocess
import streamlit as st
import edge_tts
from google import genai
from google.genai import types

# --- EXACT SIDHU PAAJI COMMENTARY DATA MODULE ---
CORE_PHRASES = [
    "ओए गुरु!", "ठोको ताली!", "चक दे फट्टे, नप दे किल्ली!", "छा गया मुंडा!",
    "गगनचुंबी छक्का!", "धूल चटा दी", "आत्मा निकाल दी", "तांडव मचा दिया",
    "भगा-भगा के मारा", "पेपर लीक", "भाई कंट्रोवर्सी क्यों करते हो",
]

EXTRA_PHRASES = {
    "hook":    ["ओए गुरु, क्या बात है!", "ओए गुरु, तांडव!", "शेर आया शेर!", "हो गया कमाल!"],
    "six":     ["गगनचुंबी छक्का!", "गेंद स्टेडियम के बाहर, गुरु!", "सीधा आसमान में!", "बल्ला बोला, बॉल रोई!"],
    "praise":  ["छा गया मुंडा!", "क्या खिलाड़ी है, गुरु!", "शेर दा पुत्तर!", "बादशाह है बादशाह!"],
    "roast":   ["धूल चटा दी", "आत्मा निकाल दी", "पेपर लीक", "भाई कंट्रोवर्सी क्यों करते हो", "बोलती बंद कर दी"],
    "closer":  ["ठोको ताली!", "चक दे फट्टे, नप दे किल्ली!", "तिरंगा लहरा दिया, गुरु!", "जय हिंद, ठोको ताली!"],
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
    "ओए गुरु, [हुक: दृश्य पर प्रतिक्रिया]! [खिलाड़ी] छा गया मुंडा, [स्कोर] भगा-भगा के मारा! [विपक्ष] को धूल चटा दी। ठोको ताली!",
    "[खिलाड़ी] ने तांडव मचा दिया, गगनचुंबी छक्का! [विपक्ष] की आत्मा निकाल दी। चक दे फट्टे, नप दे किल्ली!",
    "ओए गुरु, [स्थिति] देखो! [खिलाड़ी] का [काम]। भाई कंट्रोवर्सी क्यों करते हो, खेल देखो! ठोको ताली!",
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

STRUCTURE TEMPLATES ONLY ({lang_note}) — brackets are placeholders. NEVER copy these sentences; invent fresh lines from what is actually in THIS video:
{ex}

RULES: {RULES}
"""


st.set_page_config(page_title="Multimodal Video Hook & Multi-Shorts Extractor", layout="wide")
st.title("🎬 Direct Multimodal Video Hook & Multi-Shorts Extractor")

# Sidebar Configuration
st.sidebar.header("Settings")
gemini_api_key = st.sidebar.text_input("Gemini API Key", type="password", help="Get a key from Google AI Studio")

# Integrated Voice Roster
VOICE_OPTIONS = {
    "Gemini - Algenib (Sidhu Paaji / Gravelly & Booming Male)": {
        "engine": "gemini",
        "code": "Algenib",
        "lang": "Hindi",
        "script_type": "Devanagari script",
    },
    "Gemini - Fenrir (Sidhu Paaji / Excitable & Passionate Male)": {
        "engine": "gemini",
        "code": "Fenrir",
        "lang": "Hindi",
        "script_type": "Devanagari script",
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

script_style = st.sidebar.selectbox(
    "Mode / Script Style",
    [
        "Auto Multi-Shorts Extractor (Generate 3+ Separate Shorts)",
        "Sidhu Paaji Commentary (Oye Guru! Thoko Taali!)",
        "Soul Lines Paaji Mode (Hook-Hero-Roast-Closer)",
        "High-Dopamine Viral Opening",
        "Viral Explanation Mode (Hook-Scoop-Twist)",
        "Cinematic Storytelling",
        "Humorous & Punchy",
        "Explainer Hook"
    ]
)

multi_shorts_mode = (script_style == "Auto Multi-Shorts Extractor (Generate 3+ Separate Shorts)")

if multi_shorts_mode:
    st.sidebar.markdown("---")
    st.sidebar.subheader("📱 Multi-Shorts Extractor Settings")
    num_shorts_to_make = st.sidebar.slider(
        "🔢 Number of Separate Shorts to Generate",
        min_value=3,
        max_value=6,
        value=3,
        step=1,
        help="Finds at least 3 distinct exciting moments and saves each one as a separate Short video."
    )
    each_short_duration = st.sidebar.slider(
        "⏱️ Duration of Each Short (seconds)",
        min_value=6,
        max_value=30,
        value=12,
        step=2,
        help="Target length for each individual extracted Short."
    )
    convert_vertical_916 = st.sidebar.checkbox(
        "📐 Auto-convert each Short to 9:16 Vertical (720x1280)",
        value=True,
        help="Crops/scales horizontal videos into 9:16 vertical format for YouTube Shorts & Instagram Reels."
    )
    shorts_audio_mode = st.sidebar.radio(
        "🔊 Audio for Each Generated Short",
        [
            "Keep Original Video Audio Only (Pure Extracted Shorts, No Captions)",
            "Overlay AI Voiceover on Each Short (Sidhu Paaji Style)",
        ]
    )
    add_voiceover_on_short = shorts_audio_mode.startswith("Overlay AI Voiceover")
else:
    num_shorts_to_make = 3
    each_short_duration = 12
    convert_vertical_916 = False
    add_voiceover_on_short = True

selected_voice_label = st.sidebar.selectbox(
    "Voice Model & Language",
    list(VOICE_OPTIONS.keys()),
    disabled=(multi_shorts_mode and not add_voiceover_on_short)
)
selected_voice_info = VOICE_OPTIONS[selected_voice_label]

voice_speed = st.sidebar.slider(
    "⚡ Voice Delivery Speed Multiplier",
    min_value=0.85,
    max_value=1.50,
    value=1.00,
    step=0.05,
    help="1.00x is natural synced speed.",
    disabled=(multi_shorts_mode and not add_voiceover_on_short)
)

auto_fit_audio = st.sidebar.checkbox(
    "🔄 Auto-fit voice duration to match full video",
    value=True,
    help="Stretches or compresses the audio slightly so the voiceover starts at 0s and finishes right as the video ends.",
    disabled=(multi_shorts_mode and not add_voiceover_on_short)
)

match_context = st.sidebar.text_area(
    "Match / Video Context (Optional)",
    placeholder="e.g. Focus on sixes, wickets, and crowd celebrations. India vs Pakistan.",
    help="Tell the AI what kind of moments you want extracted or player names for commentary."
)


def cleanup_temp_files():
    patterns = [
        "temp_input.mp4", "generated_voice*.*", "fitted_voice*.wav",
        "output_hooked.mp4", "extracted_short_*.mp4", "raw_short_*.mp4"
    ]
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


def has_audio_stream(file_path: str) -> bool:
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=index", "-of", "csv=p=0", file_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return bool(res.stdout.strip())
    except Exception:
        return False


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


async def synthesize_edge_voice(text: str, voice: str, output_path: str, rate: str = "+0%", pitch: str = "+0Hz"):
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)


def synthesize_speech_unified(client, text: str, voice_info: dict, output_audio_path: str):
    """Synthesizes speech using either Gemini TTS or Edge TTS."""
    if voice_info["engine"] == "gemini":
        try:
            response = generate_content_with_retry(
                client,
                model="gemini-2.5-flash-preview-tts",
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=voice_info["code"]
                            )
                        )
                    ),
                ),
            )
            pcm_data = response.candidates[0].content.parts[0].inline_data.data
            with wave.open(output_audio_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                wf.writeframes(pcm_data)
            return
        except Exception as e:
            st.warning(f"Gemini TTS fallback to Edge-TTS triggered ({e})")

    # Fallback / Edge-TTS execution
    fallback_code = voice_info.get("code", "hi-IN-MadhurNeural")
    if not fallback_code.endswith("Neural"):
        fallback_code = "hi-IN-MadhurNeural" if voice_info.get("lang") != "English" else "en-US-GuyNeural"
    asyncio.run(
        synthesize_edge_voice(
            text=text,
            voice=fallback_code,
            output_path=output_audio_path,
            rate=voice_info.get("rate", "+0%"),
            pitch=voice_info.get("pitch", "+0Hz"),
        )
    )


def build_atempo_chain(speed_factor: float) -> str:
    """Builds a valid ffmpeg atempo filter chain (each stage between 0.5 and 2.0)."""
    factor = max(0.5, min(4.0, float(speed_factor)))
    filters = []
    while factor > 2.0:
        filters.append("atempo=2.0")
        factor /= 2.0
    while factor < 0.5:
        filters.append("atempo=0.5")
        factor /= 0.5
    filters.append(f"atempo={factor:.4f}")
    return ",".join(filters)


def fit_and_mix_voiceover(
    input_video: str,
    raw_voice_path: str,
    fitted_voice_path: str,
    output_video: str,
    target_duration: float,
    base_speed: float = 1.0,
    auto_fit: bool = True,
):
    """Adjusts voiceover speed/duration and mixes it over the original video audio."""
    raw_voice_dur = get_file_duration(raw_voice_path)
    effective_speed = base_speed

    if auto_fit and target_duration > 1.0 and raw_voice_dur > 0.5:
        # Fit audio so it finishes right before the video ends
        effective_speed = (raw_voice_dur / (target_duration * 0.96)) * base_speed
        effective_speed = max(0.80, min(1.65, effective_speed))

    atempo_filter = build_atempo_chain(effective_speed)
    subprocess.run(
        ["ffmpeg", "-y", "-i", raw_voice_path, "-filter:a", atempo_filter, fitted_voice_path],
        capture_output=True,
        check=True,
    )

    if has_audio_stream(input_video):
        filter_complex = (
            "[0:a]volume=0.22[orig];"
            "[1:a]volume=1.8[voice];"
            "[orig][voice]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", input_video,
            "-i", fitted_voice_path,
            "-filter_complex", filter_complex,
            "-map", "0:v:0",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            output_video,
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", input_video,
            "-i", fitted_voice_path,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            output_video,
        ]
    subprocess.run(cmd, capture_output=True, check=True)


def generate_commentary_script(
    client,
    video_source_part,
    duration_sec: float,
    style_name: str,
    voice_info: dict,
    context_hint: str,
    moment_desc: str = "",
) -> str:
    """Generates a scene-synced voiceover script matched to the target duration."""
    target_words = max(8, int(duration_sec * 2.4))
    lang = voice_info["lang"]
    script_type = voice_info["script_type"]

    is_sidhu = ("Sidhu" in style_name) or ("Paaji" in style_name) or ("Multi-Shorts" in style_name)
    style_instructions = get_sidhu_style_guide(script_type) if is_sidhu else f"Style: {style_name}. High-energy, viral pacing."

    prompt = f"""
    Watch this {duration_sec:.1f}-second video clip carefully.
    Write a single, continuous voiceover script in {lang} written strictly in {script_type}.
    Target length: approximately {target_words} words (must be spoken naturally within {duration_sec:.1f} seconds).

    Context / User Hint: {context_hint or "Highlight the action on screen."}
    Specific Moment Focus: {moment_desc or "Full clip."}

    {style_instructions}

    OUTPUT RULES:
    - Output ONLY the spoken script text in {script_type}.
    - Do NOT include stage directions, timestamps, brackets, speaker labels, or markdown formatting.
    """

    contents = [video_source_part, prompt] if video_source_part is not None else [prompt]
    resp = generate_content_with_retry(
        client,
        model="gemini-2.5-flash",
        contents=contents,
        config=types.GenerateContentConfig(temperature=0.7),
    )
    return (resp.text or "").strip().strip('"')


def parse_timestamp_to_seconds(val) -> float:
    """Safely converts float, int, 'SS.s', or 'MM:SS' strings to float seconds."""
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace("s", "")
    if ":" in s:
        parts = s.split(":")
        if len(parts) == 2:
            return float(parts[0]) * 60.0 + float(parts[1])
        if len(parts) == 3:
            return float(parts[0]) * 3600.0 + float(parts[1]) * 60.0 + float(parts[2])
    return float(s)


def find_multiple_short_moments(client, video_file, video_duration: float, num_shorts: int, clip_dur: int, context_hint: str) -> list[dict]:
    """Watches the video and returns at least `num_shorts` separate, high-impact moments to be exported as individual Shorts."""
    sample_fps = 2 if video_duration <= 120 else 1
    video_part = types.Part(
        file_data=types.FileData(file_uri=video_file.uri, mime_type=video_file.mime_type or "video/mp4"),
        video_metadata=types.VideoMetadata(fps=sample_fps),
    )

    effective_clip_dur = min(float(clip_dur), max(3.0, video_duration / float(num_shorts)))

    prompt = f"""
    You are an expert viral YouTube Shorts & Instagram Reels producer.
    Watch this {video_duration:.1f}-second video carefully.
    Identify EXACTLY {num_shorts} SEPARATE, MOST INTERESTING, VIRAL-WORTHY moments that will each become its own standalone Short video.
    User focus/hint: {context_hint or "Pick the most exciting, high-action, emotional, or viral moments."}

    CRITICAL RULES:
    1. You MUST return at least {num_shorts} distinct moments.
    2. Every `start` and `end` timestamp MUST be in float seconds strictly within `0.0` and `{video_duration:.1f}`.
    3. Each individual Short should be approximately `{effective_clip_dur:.1f}` seconds long (minimum 3.0 seconds).
    4. Spread the picks across different exciting parts of the video so you get {num_shorts} unique Shorts.
    5. Return ONLY a raw JSON list of objects with these exact keys:
    [
      {{
        "title": "Catchy 4-word title for this Short",
        "start": 2.0,
        "end": 14.0,
        "reason": "Detailed description of what happens visually in this specific Short"
      }}
    ]
    Output ONLY valid JSON, no markdown fences, no commentary.
    """

    cleaned = []
    try:
        resp = generate_content_with_retry(
            client,
            model="gemini-2.5-flash",
            contents=[video_part, prompt],
            config=types.GenerateContentConfig(temperature=0.2)
        )
        raw = (resp.text or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
        items = json.loads(raw)

        for idx, item in enumerate(items):
            st_t = max(0.0, parse_timestamp_to_seconds(item.get("start", 0.0)))
            end_t = min(video_duration, parse_timestamp_to_seconds(item.get("end", st_t + effective_clip_dur)))
            if end_t - st_t < 2.5:
                end_t = min(video_duration, st_t + effective_clip_dur)
            if end_t - st_t < 2.0 and st_t > 2.0:
                st_t = max(0.0, end_t - effective_clip_dur)
            if end_t - st_t >= 1.5:
                cleaned.append({
                    "title": str(item.get("title", f"Viral Short #{idx + 1}")).strip(),
                    "start": round(st_t, 2),
                    "end": round(end_t, 2),
                    "reason": str(item.get("reason", "Exciting highlight moment")).strip()
                })
    except Exception:
        pass

    # Guarantee at least `num_shorts` clips even if video is short or AI returned fewer
    if len(cleaned) < num_shorts:
        step = video_duration / float(num_shorts)
        for i in range(len(cleaned), num_shorts):
            st_t = round(i * step, 2)
            end_t = round(min(video_duration, st_t + effective_clip_dur), 2)
            if end_t - st_t < 1.5:
                st_t = round(max(0.0, video_duration - effective_clip_dur), 2)
                end_t = round(video_duration, 2)
            cleaned.append({
                "title": f"Highlight Short #{i + 1}",
                "start": st_t,
                "end": end_t,
                "reason": f"Key action segment #{i + 1} from the video"
            })

    return cleaned[:num_shorts]


def extract_single_short_ffmpeg(input_video: str, start_t: float, end_t: float, output_path: str, vertical_916: bool = True) -> bool:
    """Cuts a single standalone Short from `input_video` between `start_t` and `end_t` with zero captions."""
    dur = max(1.5, round(end_t - start_t, 2))
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_t),
        "-t", str(dur),
        "-i", input_video,
    ]
    if vertical_916:
        vf_str = "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1,format=yuv420p"
        cmd.extend(["-vf", vf_str])
    else:
        cmd.extend(["-pix_fmt", "yuv420p"])

    if has_audio_stream(input_video):
        cmd.extend([
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-c:a", "aac", "-ar", "48000", "-ac", "2",
            output_path
        ])
    else:
        cmd.extend([
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-an",
            output_path
        ])

    subprocess.run(cmd, capture_output=True, check=True)
    return os.path.exists(output_path)


# --- MAIN PAGE EXECUTION ---
uploaded_file = st.file_uploader("Upload MP4 Video File", type=["mp4"])

if uploaded_file is not None:
    temp_video = "temp_input.mp4"
    script_audio = "generated_voice.wav"
    fitted_audio = "fitted_voice.wav"
    output_video = "output_hooked.mp4"

    with open(temp_video, "wb") as f:
        f.write(uploaded_file.getbuffer())

    st.video(temp_video)

    btn_label = (
        f"🔥 Find Best Moments & Convert into {num_shorts_to_make} Separate Shorts"
        if multi_shorts_mode
        else "🚀 Analyze Video & Overlay Viral Hook"
    )

    if st.button(btn_label):
        api_key = (gemini_api_key or os.environ.get("GEMINI_API_KEY") or "").strip()
        if not api_key:
            st.error("Please enter your Gemini API Key in the sidebar.")
            st.stop()
        if not api_key.isascii() or len(api_key) > 100 or any(c.isspace() for c in api_key):
            st.error(
                f"The Gemini API key looks wrong: {len(api_key)} characters, "
                f"{'contains non-English characters' if not api_key.isascii() else 'unexpected length/spaces'}. "
                "A real key is ~39 characters starting with 'AIza'. Clear the sidebar field "
                "(and check the GEMINI_API_KEY environment variable) and paste only the key from Google AI Studio."
            )
            st.stop()

        cleanup_temp_files()
        with open(temp_video, "wb") as f:
            f.write(uploaded_file.getbuffer())

        client = genai.Client(api_key=api_key)

        # =========================================================================
        # MODE 1: AUTO MULTI-SHORTS EXTRACTOR (3+ SEPARATE SHORTS, NO JOINING)
        # =========================================================================
        if multi_shorts_mode:
            generated_shorts_info = []

            with st.status(f"Scanning Video & Generating {num_shorts_to_make} Separate Shorts...", expanded=True) as status:
                orig_duration = get_file_duration(temp_video)
                st.write(f"⏱️ Source Video Duration: **{orig_duration:.2f} seconds**")

                st.write("📹 Uploading video to Gemini to detect the top viral moments...")
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

                st.write(f"🔎 Finding the **{num_shorts_to_make}** most interesting moments (~{each_short_duration}s each)...")
                moments = find_multiple_short_moments(
                    client, video_file, orig_duration, num_shorts_to_make, each_short_duration, match_context
                )

                try:
                    client.files.delete(name=video_file.name)
                except Exception:
                    pass

                # Process each moment into its own separate MP4 Short
                for idx, m in enumerate(moments, start=1):
                    st_t = m["start"]
                    end_t = m["end"]
                    clip_dur = round(end_t - st_t, 2)
                    raw_short_path = f"raw_short_{idx}.mp4"
                    final_short_path = f"extracted_short_{idx}.mp4"

                    st.write(f"✂️ **Short #{idx}: {m['title']}** (`{st_t:.1f}s` → `{end_t:.1f}s` | `{clip_dur:.1f}s`)")
                    extract_single_short_ffmpeg(
                        input_video=temp_video,
                        start_t=st_t,
                        end_t=end_t,
                        output_path=raw_short_path if add_voiceover_on_short else final_short_path,
                        vertical_916=convert_vertical_916,
                    )

                    script_text = ""
                    if add_voiceover_on_short:
                        st.write(f"🎙️ Writing & synthesizing commentary for Short #{idx}...")
                        script_text = generate_commentary_script(
                            client=client,
                            video_source_part=None,
                            duration_sec=clip_dur,
                            style_name="Sidhu Paaji Commentary",
                            voice_info=selected_voice_info,
                            context_hint=match_context,
                            moment_desc=f"{m['title']} - {m['reason']}",
                        )
                        short_voice_raw = f"generated_voice_{idx}.wav"
                        short_voice_fit = f"fitted_voice_{idx}.wav"
                        synthesize_speech_unified(client, script_text, selected_voice_info, short_voice_raw)
                        fit_and_mix_voiceover(
                            input_video=raw_short_path,
                            raw_voice_path=short_voice_raw,
                            fitted_voice_path=short_voice_fit,
                            output_video=final_short_path,
                            target_duration=clip_dur,
                            base_speed=voice_speed,
                            auto_fit=auto_fit_audio,
                        )

                    generated_shorts_info.append({
                        "index": idx,
                        "title": m["title"],
                        "start": st_t,
                        "end": end_t,
                        "reason": m["reason"],
                        "script": script_text,
                        "path": final_short_path,
                    })

                status.update(label=f"✅ Successfully generated {len(generated_shorts_info)} separate Shorts!", state="complete")

            st.subheader(f"📱 Generated Shorts ({len(generated_shorts_info)} Separate Videos)")
            cols = st.columns(min(3, len(generated_shorts_info)))
            for i, info in enumerate(generated_shorts_info):
                with cols[i % len(cols)]:
                    st.markdown(f"#### #{info['index']}: {info['title']}")
                    st.caption(f"⏱️ `{info['start']:.1f}s - {info['end']:.1f}s` | {info['reason']}")
                    if info["script"]:
                        st.info(f"🗣️ **Commentary:** {info['script']}")
                    if os.path.exists(info["path"]):
                        st.video(info["path"])
                        with open(info["path"], "rb") as vf:
                            st.download_button(
                                label=f"⬇️ Download Short #{info['index']}",
                                data=vf,
                                file_name=f"short_{info['index']}.mp4",
                                mime="video/mp4",
                                key=f"dl_short_{info['index']}",
                            )

        # =========================================================================
        # MODE 2: SINGLE VIDEO DIRECT MULTIMODAL COMMENTARY & VOICEOVER HOOK
        # =========================================================================
        else:
            with st.status("Analyzing Video & Generating Scene-Synced Voiceover...", expanded=True) as status:
                video_duration = get_file_duration(temp_video)
                st.write(f"⏱️ Video Duration: **{video_duration:.2f} seconds**")

                st.write("📹 Uploading video to Gemini...")
                try:
                    video_file = client.files.upload(file=temp_video)
                except Exception as e:
                    st.error(f"Authentication or Upload Error: {e}")
                    st.stop()

                while get_file_state_str(video_file) in ["PROCESSING", "PENDING"]:
                    time.sleep(2)
                    video_file = client.files.get(name=video_file.name)

                if get_file_state_str(video_file) != "ACTIVE":
                    st.error(f"Gemini failed to process video. State: {get_file_state_str(video_file)}")
                    st.stop()

                video_part = types.Part(
                    file_data=types.FileData(file_uri=video_file.uri, mime_type=video_file.mime_type or "video/mp4"),
                    video_metadata=types.VideoMetadata(fps=2 if video_duration <= 90 else 1),
                )

                st.write("✍️ Generating scene-synced script...")
                generated_script = generate_commentary_script(
                    client=client,
                    video_source_part=video_part,
                    duration_sec=video_duration,
                    style_name=script_style,
                    voice_info=selected_voice_info,
                    context_hint=match_context,
                )

                try:
                    client.files.delete(name=video_file.name)
                except Exception:
                    pass

                st.write(f"🗣️ Synthesizing voiceover (`{selected_voice_label}`)...")
                synthesize_speech_unified(client, generated_script, selected_voice_info, script_audio)

                st.write("🎬 Mixing audio & syncing with video via FFmpeg...")
                fit_and_mix_voiceover(
                    input_video=temp_video,
                    raw_voice_path=script_audio,
                    fitted_voice_path=fitted_audio,
                    output_video=output_video,
                    target_duration=video_duration,
                    base_speed=voice_speed,
                    auto_fit=auto_fit_audio,
                )

                status.update(label="✅ Video Commentary Ready!", state="complete")

            st.subheader("📝 Generated Script")
            st.success(generated_script)

            if os.path.exists(output_video):
                st.subheader("🎬 Final Output Video")
                st.video(output_video)
                with open(output_video, "rb") as f:
                    st.download_button(
                        label="⬇️ Download Final Hooked Video",
                        data=f,
                        file_name="sidhu_commentary_output.mp4",
                        mime="video/mp4",
                    )
