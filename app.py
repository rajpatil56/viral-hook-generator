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

st.set_page_config(page_title="Multimodal Video Hook & Highlight Clipper", layout="wide")
st.title("🎬 Direct Multimodal Video Hook & Auto Highlight Short Maker")

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
        "Auto Highlight Clipper (Cut & Join Best Moments into 1 Short)",
        "Sidhu Paaji Commentary (Oye Guru! Thoko Taali!)",
        "Soul Lines Paaji Mode (Hook-Hero-Roast-Closer)",
        "High-Dopamine Viral Opening",
        "Viral Explanation Mode (Hook-Scoop-Twist)",
        "Cinematic Storytelling",
        "Humorous & Punchy",
        "Explainer Hook"
    ]
)

highlight_clipper_mode = (script_style == "Auto Highlight Clipper (Cut & Join Best Moments into 1 Short)")

if highlight_clipper_mode:
    st.sidebar.markdown("---")
    st.sidebar.subheader("✂️ Highlight Clipper Settings")
    target_short_duration = st.sidebar.slider(
        "🎯 Target Joined Short Length (seconds)",
        min_value=10,
        max_value=60,
        value=20,
        step=5,
        help="Total length of all exciting moments combined into one single Short."
    )
    clipper_audio_mode = st.sidebar.radio(
        "🔊 Audio for Joined Short",
        [
            "Keep Original Video Audio Only (Pure Cut & Join, No Voiceover)",
            "Add AI Voiceover on Joined Short (Sidhu Paaji Style)",
        ]
    )
    add_voiceover_on_short = clipper_audio_mode.startswith("Add AI Voiceover")
else:
    target_short_duration = 20
    add_voiceover_on_short = True

selected_voice_label = st.sidebar.selectbox(
    "Voice Model & Language",
    list(VOICE_OPTIONS.keys()),
    disabled=(highlight_clipper_mode and not add_voiceover_on_short)
)
selected_voice_info = VOICE_OPTIONS[selected_voice_label]

voice_speed = st.sidebar.slider(
    "⚡ Voice Delivery Speed Multiplier",
    min_value=0.85,
    max_value=1.50,
    value=1.00,
    step=0.05,
    help="1.00x is natural synced speed.",
    disabled=(highlight_clipper_mode and not add_voiceover_on_short)
)

auto_fit_audio = st.sidebar.checkbox(
    "🔄 Auto-fit voice duration to match full video",
    value=True,
    help="Stretches or compresses the audio slightly so the voiceover starts at 0s and finishes right as the video ends.",
    disabled=(highlight_clipper_mode and not add_voiceover_on_short)
)

match_context = st.sidebar.text_area(
    "Match / Video Context (Optional)",
    placeholder="e.g. Focus on sixes, wickets, and celebrations. India vs Pakistan final.",
    help="Tell the AI what kind of moments you want prioritized or player names for commentary."
)


def cleanup_temp_files():
    patterns = [
        "temp_input.mp4", "generated_voice.mp3", "fitted_voice.wav",
        "joined_highlights.mp4", "output_hooked.mp4",
        "highlight_part_*.mp4", "highlight_list.txt"
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


async def synthesize_voice(text: str, voice: str, output_path: str, rate: str = "+0%", pitch: str = "+15Hz"):
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)


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


def extract_best_highlight_moments(client, video_file, video_duration: float, target_total_sec: int, context_hint: str) -> list[dict]:
    """Watches the video and returns non-overlapping start/end timestamps of the most exciting moments."""
    # Sampling fps: 2fps for clips <=2 min, 1fps for longer videos
    sample_fps = 2 if video_duration <= 120 else 1
    video_part = types.Part(
        file_data=types.FileData(file_uri=video_file.uri, mime_type=video_file.mime_type or "video/mp4"),
        video_metadata=types.VideoMetadata(fps=sample_fps),
    )

    desired_total = min(float(target_short_duration), max(5.0, video_duration * 0.85))
    num_clips = max(2, min(8, int(round(desired_total / 3.5))))

    prompt = f"""
    You are an expert viral video and sports highlight editor.
    Watch this {video_duration:.1f}-second video carefully.
    Find the {num_clips} MOST INTERESTING, HIGH-IMPACT, EXCITING moments in the video (e.g. peak action, big shots, wickets, goals, celebrations, emotional reactions, crowd roars, or key visual turning points).
    User hint/focus: {context_hint or "Pick the most exciting peak action moments."}

    CRITICAL RULES:
    1. Every timestamp MUST be strictly between 0.0 and {video_duration:.1f} seconds (in float seconds, e.g. 4.5, 18.2).
    2. Each individual clip should be between 2.0 and 6.0 seconds long.
    3. The sum of all clip durations should be approximately {desired_total:.1f} seconds.
    4. Keep clips in chronological order (`start` < `end`, and non-overlapping).
    5. Return ONLY a raw JSON list of objects with these exact keys:
    [
      {{
        "start": 3.5,
        "end": 7.0,
        "reason": "Brief description of what exciting thing happens in this clip"
      }}
    ]
    Output ONLY valid JSON, no markdown fences, no extra text.
    """

    try:
        resp = generate_content_with_retry(
            client,
            model="gemini-3.6-flash",
            contents=[video_part, prompt],
            config=types.GenerateContentConfig(temperature=0.2)
        )
        raw = (resp.text or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
        items = json.loads(raw)

        # Clean, sort, and de-overlap clips
        cleaned = []
        for item in items:
            st_t = max(0.0, parse_timestamp_to_seconds(item.get("start", 0.0)))
            end_t = min(video_duration, parse_timestamp_to_seconds(item.get("end", st_t + 3.0)))
            if end_t - st_t >= 1.2:
                cleaned.append({
                    "start": round(st_t, 2),
                    "end": round(end_t, 2),
                    "reason": str(item.get("reason", "Highlight moment")).strip()
                })

        cleaned.sort(key=lambda x: x["start"])
        merged = []
        last_end = 0.0
        running_dur = 0.0
        for c in cleaned:
            st_t = max(c["start"], last_end)
            end_t = c["end"]
            if end_t - st_t >= 1.2:
                if running_dur + (end_t - st_t) > desired_total + 4.0 and len(merged) >= 2:
                    break
                merged.append({
                    "start": round(st_t, 2),
                    "end": round(end_t, 2),
                    "reason": c["reason"]
                })
                last_end = end_t
                running_dur += (end_t - st_t)

        if merged:
            return merged
    except Exception:
        pass

    # Fallback if parsing fails: pick Beginning, Middle, and Climax segments
    seg = min(4.0, video_duration / 3.0)
    return [
        {"start": 0.0, "end": round(seg, 2), "reason": "Opening highlight"},
        {"start": round(video_duration * 0.45, 2), "end": round(video_duration * 0.45 + seg, 2), "reason": "Mid-video peak action"},
        {"start": round(max(0.0, video_duration - seg), 2), "end": round(video_duration, 2), "reason": "Climax moment"},
    ]


def cut_and_join_highlights_ffmpeg(input_video: str, moments: list[dict], output_joined: str) -> bool:
    """Cuts each highlight segment cleanly and stitches them into a single seamless MP4 Short (zero captions)."""
    if not moments:
        return False

    input_has_audio = has_audio_stream(input_video)
    part_files = []

    for idx, m in enumerate(moments):
        st_t = m["start"]
        dur = round(m["end"] - m["start"], 2)
        if dur <= 0.5:
            continue
        part_path = f"highlight_part_{idx}.mp4"

        if input_has_audio:
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(st_t),
                "-t", str(dur),
                "-i", input_video,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-ar", "48000", "-ac", "2",
                part_path
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(st_t),
                "-t", str(dur),
                "-i", input_video,
                "-f", "lavfi", "-t", str(dur), "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-ar", "48000", "-ac", "2",
                "-shortest",
                part_path
            ]

        subprocess.run(cmd, capture_output=True, check=True)
        if os.path.exists(part_path):
            part_files.append(part_path)

    if not part_files:
        return False

    list_path = "highlight_list.txt"
    with open(list_path, "w", encoding="utf-8") as f:
        for p in part_files:
            f.write(f"file '{p}'\n")

    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_path,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "48000", "-ac", "2",
        output_joined
    ], capture_output=True, check=True)

    return os.path.exists(output_joined)


# --- MAIN PAGE EXECUTION ---
uploaded_file = st.file_uploader("Upload MP4 Video File", type=["mp4"])

if uploaded_file is not None:
    temp_video = "temp_input.mp4"
    script_audio = "generated_voice.mp3"
    fitted_audio = "fitted_voice.wav"
    joined_highlights = "joined_highlights.mp4"
    output_video = "output_hooked.mp4"

    with open(temp_video, "wb") as f:
        f.write(uploaded_file.getbuffer())

    st.video(temp_video)

    btn_label = (
        "✂️ Find Best Moments, Cut & Join into 1 Short"
        if highlight_clipper_mode
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
        # MODE 1: AUTO HIGHLIGHT CLIPPER (FIND BEST MOMENTS, CUT & JOIN INTO 1 SHORT)
        # =========================================================================
        if highlight_clipper_mode:
            with st.status("Scanning Video for Most Interesting Moments & Joining into 1 Short...", expanded=True) as status:
                orig_duration = get_file_duration(temp_video)
                st.write(f"⏱️ Original Video Duration: **{orig_duration:.2f} seconds**")

                st.write("📹 Uploading video to Gemini to detect peak action & highlight timestamps...")
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

                st.write(f"🔎 Identifying the best moments (Target Short length: ~**{target_short_duration}s**)...")
                moments = extract_best_highlight_moments(
                    client, video_file, orig_duration, target_short_duration, match_context
                )

                try:
                    client.files.delete(name=video_file.name)
                except Exception:
                    pass

                st.write(f"✂️ Found **{len(moments)}** highlight moments! Cutting & joining clips via FFmpeg (No captions):")
                for i, m in enumerate(moments, start=1):
                    clip_len = m["end"] - m["start"]
                    st.write(f"  • **Clip {i} [{m['start']}s – {m['end']}s]** ({clip_len:.1f}s): {m['reason']}")

                if not cut_and_join_highlights_ffmpeg(temp_video, moments, joined_highlights):
                    st.error("Failed to cut and join highlight segments.")
                    st.stop()

                short_duration = get_file_duration(joined_highlights)
                st.write(f"✅ Joined Highlight Short Duration: **{short_duration:.2f} seconds**")

                # Option A: Pure Cut & Join (Keep Original Video Audio, No Voiceover, No Captions)
                if not add_voiceover_on_short:
                    os.replace(joined_highlights, output_video)
                    status.update(label="✨ Best Moments Cut & Joined into 1 Short Successfully!", state="complete", expanded=False)

                # Option B: Overlay AI Voiceover on the newly joined Highlight Short
                else:
                    target_lang = selected_voice_info["lang"]
                    script_type = selected_voice_info["script_type"]
                    target_words = max(10, int(short_duration * 2.4 * voice_speed))

                    st.write(f"🤖 Writing Sidhu Paaji commentary synced to your new {short_duration:.1f}s Highlight Short...")
                    moments_summary = "\n".join(
                        f"- Clip {i+1} ({m['end'] - m['start']:.1f}s): {m['reason']}"
                        for i, m in enumerate(moments)
                    )
                    style_guide = get_sidhu_style_guide(lang_note=script_type)
                    phrase_rule = "FOR THIS SHORT, build the script around these phrases (use at least 3): " + " | ".join(random.sample(CORE_PHRASES, 4))

                    prompt = f"""
                    You are a master viral video scriptwriter writing as Navjot Singh Sidhu (Sidhu Paaji) doing live commentary.
                    Below is the exact sequence of highlight clips joined into a {short_duration:.1f}-second Short:
                    {moments_summary}

                    USER CONTEXT: {match_context or "none provided"}
                    {style_guide}
                    {phrase_rule}

                    CRITICAL LANGUAGE & TIMING CONSTRAINTS:
                    1. Write the ENTIRE script natively in {target_lang} using standard {script_type}.
                    2. Write approximately **{target_words} words** so it covers the {short_duration:.1f}s Short at 1x speed.
                    3. Output ONLY the plain script text. No markdown, no timestamps, no labels.
                    """
                    resp = generate_content_with_retry(
                        client,
                        model="gemini-3.6-flash",
                        contents=[prompt],
                        config=types.GenerateContentConfig(temperature=1.1, top_p=0.95)
                    )
                    creative_script = (resp.text or "").strip()
                    st.markdown(f"**Generated Highlight Voiceover ({target_lang}):**\n> {creative_script}")

                    if selected_voice_info["engine"] == "gemini":
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
                            st.error("Gemini failed to return audio data.")
                            st.stop()
                    else:
                        asyncio.run(synthesize_voice(
                            text=creative_script,
                            voice=selected_voice_info["code"],
                            output_path=script_audio,
                            rate=selected_voice_info.get("rate", "+0%"),
                            pitch=selected_voice_info.get("pitch", "+15Hz")
                        ))

                    audio_duration = get_file_duration(script_audio)
                    if auto_fit_audio:
                        final_tempo = max(0.85, min(audio_duration / short_duration, 1.35))
                    else:
                        final_tempo = voice_speed

                    audio_filter = (
                        f"atempo={final_tempo},"
                        f"loudnorm=I=-14.0:TP=-1.5:LRA=11,"
                        f"apad=whole_dur={short_duration}"
                    )
                    subprocess.run([
                        "ffmpeg", "-y", "-i", script_audio,
                        "-filter:a", audio_filter,
                        "-t", str(short_duration),
                        "-ar", "48000", "-ac", "2",
                        fitted_audio
                    ], capture_output=True, check=True)

                    subprocess.run([
                        "ffmpeg", "-y",
                        "-i", joined_highlights,
                        "-i", fitted_audio,
                        "-c:v", "copy",
                        "-c:a", "aac",
                        "-ar", "48000", "-ac", "2",
                        "-map", "0:v:0", "-map", "1:a:0",
                        "-t", str(short_duration),
                        output_video
                    ], check=True)

                    status.update(label="✨ Best Moments Joined & Voiceover Overlaid!", state="complete", expanded=False)

            st.subheader("🔥 Final Joined Highlight Short")
            st.video(output_video)
            with open(output_video, "rb") as f_dl:
                st.download_button("⬇️ Download Joined Highlight Short (MP4)", data=f_dl, file_name="highlight_short.mp4", mime="video/mp4")

        # =========================================================================
        # MODE 2: STANDARD FULL-VIDEO VOICEOVER MODES (SIDHU PAAJI, SOUL LINES, ETC.)
        # =========================================================================
        else:
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

                sidhu_mode = script_style.startswith("Sidhu Paaji")
                target_lang = selected_voice_info["lang"]
                script_type = selected_voice_info["script_type"]
                target_words = max(12, int(video_duration * 2.4 * voice_speed))

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

                # 3a. PASS 1 - watch the video frame-by-frame
                st.write("👀 Pass 1: watching the video frame-by-frame (2 fps)...")
                video_part = types.Part(
                    file_data=types.FileData(file_uri=video_file.uri, mime_type=video_file.mime_type or "video/mp4"),
                    video_metadata=types.VideoMetadata(fps=2),
                )
                watch_prompt = f"""
                Watch this {video_duration:.1f}-second video carefully. Produce a timestamped log, one line per ~1-2 seconds, in English:
                [mm:ss] what is visibly happening (action, camera shot, crowd, stands, trophy, scoreboard, gestures, emotion).
                ALSO list every piece of READABLE text you can see: jersey names/numbers, banners, posters, scoreboard, captions, sponsor/venue boards.
                Rules: describe only what is visible. Do NOT identify any person from their face or looks. If a person is not named by readable
                text or by this user context, call them "unidentified player/fan/person".
                User context (may name teams/players/scores): {match_context or "none provided"}
                Output only the log.
                """
                try:
                    watch = generate_content_with_retry(
                        client,
                        model="gemini-3.6-flash",
                        contents=[video_part, watch_prompt],
                        config=types.GenerateContentConfig(temperature=0.2)
                    )
                    visual_log = (watch.text or "").strip()
                except Exception as err:
                    st.error(f"Video analysis failed: {err}")
                    st.stop()
                with st.expander("🔎 What the AI saw in your video"):
                    st.text(visual_log)

                # 3b. PASS 2 - write a fresh script from the log + context
                used = st.session_state.setdefault("used_scripts", [])
                if sidhu_mode:
                    persona = "You are a master viral video scriptwriter writing as Navjot Singh Sidhu (Sidhu Paaji) doing live cricket commentary."
                    phrase_rule = "FOR THIS VIDEO, build the script around these phrases (use at least 3): " + " | ".join(random.sample(CORE_PHRASES, 4))
                else:
                    persona = "You are a master viral video scriptwriter."
                    phrase_rule = (
                        "Do NOT use Sidhu Paaji's style or his catchphrases (no 'ओए गुरु', 'ठोको ताली', 'चक दे फट्टे', "
                        "'छा गया मुंडा', etc.). Follow ONLY the style guide below."
                    )

                prompt = f"""
                {persona}
                Below is a timestamped description of a {video_duration:.1f}-second video. Write a voiceover that matches what happens in THIS video, in order.

                VISUAL LOG:
                {visual_log}

                USER CONTEXT (source of truth for real names / teams / scores): {match_context or "none provided"}

                NAMING RULES: Use a player's/team's real name ONLY if it appears in the user context or as readable text in the log.
                Never guess a name from a face. If no name is known, say "यह खिलाड़ी", "ये मुंडा", "भारत की टीम", "स्टेडियम" etc. Never invent scores/stats.

                {style_guide}

                {phrase_rule}
                Reference at least 2 concrete things from the visual log (a gesture, banner, crowd moment, trophy, etc.).
                Do NOT reuse wording from earlier scripts: {" || ".join(u[:80] for u in used[-5:]) or "none yet"}

                CRITICAL LANGUAGE & TIMING CONSTRAINTS:
                1. Write the ENTIRE script natively in {target_lang} using standard {script_type}.
                2. Write approximately **{target_words} words** so it covers the whole video at 1x speed.
                3. Output ONLY the plain script text. No markdown, no timestamps, no labels.
                """

                try:
                    response = generate_content_with_retry(
                        client,
                        model="gemini-3.6-flash",
                        contents=[prompt],
                        config=types.GenerateContentConfig(temperature=1.2, top_p=0.95)
                    )
                except Exception as err:
                    st.error(f"Error generating script with gemini-3.6-flash: {err}")
                    st.stop()

                try:
                    client.files.delete(name=video_file.name)
                except Exception:
                    pass

                creative_script = response.text.strip() if response.text else ""
                if creative_script:
                    st.session_state.setdefault("used_scripts", []).append(creative_script)
                if not creative_script:
                    st.error("Generated script was empty. Please try again.")
                    st.stop()

                st.markdown(f"**Generated Script ({target_lang}):**\n> {creative_script}")

                # 4. Clean Audio Voice Synthesis Path
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

                status.update(label="✨ Hook Successfully Overlaid (100% Video Preserved)!", state="complete", expanded=False)

            st.subheader("🔥 Final Video Output")
            st.video(output_video)
            with open(output_video, "rb") as f_dl:
                st.download_button("⬇️ Download Hooked Video (MP4)", data=f_dl, file_name="hooked_video.mp4", mime="video/mp4")
