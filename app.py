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
import urllib.request
import urllib.parse
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

st.set_page_config(page_title="Multimodal Video Hook Generator", layout="wide")
st.title("🎬 Direct Multimodal Video Hook Overlay (Sidhu Paaji + Exact Script B-Roll Edition)")

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
        "Custom Story Mode (Exact Script + Auto B-Roll)",
        "Sidhu Paaji Commentary (Oye Guru! Thoko Taali!)",
        "Soul Lines Paaji Mode (Hook-Hero-Roast-Closer)",
        "High-Dopamine Viral Opening",
        "Viral Explanation Mode (Hook-Scoop-Twist)",
        "Cinematic Storytelling",
        "Humorous & Punchy",
        "Explainer Hook"
    ]
)

if script_style == "Custom Story Mode (Exact Script + Auto B-Roll)":
    user_story = st.sidebar.text_area(
        "📖 Paste Your Exact Script (Spoken 100% As-Is, Zero Changes)",
        height=180,
        placeholder="Paste your exact voiceover script here. The AI will NOT change a single word — it will speak this exact script, find matching images & videos online for each point, and overlay them on your video.",
        help="Your script is used verbatim without any AI rewriting."
    )
    match_context = user_story
else:
    user_story = ""
    match_context = st.sidebar.text_area(
        "Match / player context (recommended)",
        placeholder="e.g. India vs Pakistan Asian Games final. Abhishek Sharma 61 off 28, Tilak Varma 51* off 22. India won by 19 runs.",
        help="Gemini does not identify people by face. Put the real names, teams and scores here and they will be used in the script."
    )

# --- ONLINE B-ROLL (IMAGES & VIDEOS) SIDEBAR SETTINGS ---
st.sidebar.markdown("---")
st.sidebar.subheader("🖼️ Auto B-Roll (Online Images & Videos)")
enable_broll = st.sidebar.checkbox(
    "✨ Auto-overlay online Images/Videos at exact script points",
    value=True,
    help="Finds real images & video clips online matching specific sentences in your script and overlays them at the exact timestamp."
)

broll_media_preference = st.sidebar.selectbox(
    "B-Roll Media Type",
    ["Images & Videos (Mixed)", "Images Only (Wikimedia + Pexels)", "Videos Only (Requires Pexels Key)"],
    disabled=not enable_broll
)

broll_display_style = st.sidebar.selectbox(
    "B-Roll Overlay Style",
    [
        "Top-Right Picture-in-Picture Card (Keeps Main Video Visible)",
        "Top-Center Dynamic Pop-Up Card",
        "Full-Screen Cutaway (Replaces Frame During Cue)"
    ],
    disabled=not enable_broll
)

pexels_api_key = st.sidebar.text_input(
    "Pexels API Key (Optional - for HD Stock Videos)",
    type="password",
    help="Leave blank to use free Wikimedia Commons images automatically, or enter a free key from pexels.com/api for HD B-roll videos & photos.",
    disabled=not enable_broll
)


def cleanup_temp_files():
    patterns = [
        "temp_input.mp4", "generated_voice.mp3", "fitted_voice.wav",
        "video_with_broll.mp4", "output_hooked.mp4", "broll_item_*"
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


def get_video_dimensions(file_path: str) -> tuple[int, int]:
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=s=x:p=0", file_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        w, h = res.stdout.strip().split("x")
        return int(w), int(h)
    except Exception:
        return 720, 1280


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


# --- ONLINE B-ROLL SEARCH & DOWNLOAD FUNCTIONS ---
def download_url_to_file(url: str, dest_path: str) -> bool:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HookGenerator/1.0"}
        )
        with urllib.request.urlopen(req, timeout=12) as resp, open(dest_path, "wb") as out:
            out.write(resp.read())
        return os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000
    except Exception:
        return False


def fetch_pexels_video(query: str, api_key: str, dest_path: str) -> bool:
    if not api_key:
        return False
    try:
        encoded_q = urllib.parse.quote(query)
        url = f"https://api.pexels.com/videos/search?query={encoded_q}&per_page=4&orientation=portrait"
        req = urllib.request.Request(url, headers={"Authorization": api_key, "User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for video in data.get("videos", []):
            for vf in video.get("video_files", []):
                if vf.get("file_type") == "video/mp4" and int(vf.get("width", 0)) <= 1280:
                    if download_url_to_file(vf["link"], dest_path):
                        return True
    except Exception:
        pass
    return False


def fetch_pexels_image(query: str, api_key: str, dest_path: str) -> bool:
    if not api_key:
        return False
    try:
        encoded_q = urllib.parse.quote(query)
        url = f"https://api.pexels.com/v1/search?query={encoded_q}&per_page=3"
        req = urllib.request.Request(url, headers={"Authorization": api_key, "User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for photo in data.get("photos", []):
            img_url = photo.get("src", {}).get("large") or photo.get("src", {}).get("medium")
            if img_url and download_url_to_file(img_url, dest_path):
                return True
    except Exception:
        pass
    return False


def fetch_wikimedia_image(query: str, dest_path: str) -> bool:
    """Free, zero-API-key image search from Wikimedia Commons (great for real cricketers, stadiums, countries, events)."""
    try:
        encoded_q = urllib.parse.quote(query)
        url = (
            f"https://commons.wikimedia.org/w/api.php?action=query&generator=search"
            f"&gsrsearch=filetype:bitmap%20{encoded_q}&gsrlimit=5&prop=imageinfo"
            f"&iiprop=url&iiurlwidth=800&format=json"
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "SoulLinesHookGenerator/1.0 (https://streamlit.io)"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        pages = data.get("query", {}).get("pages", {})
        for _, page in pages.items():
            ii = page.get("imageinfo", [])
            if ii:
                img_url = ii[0].get("thumburl") or ii[0].get("url")
                if img_url and any(img_url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                    if download_url_to_file(img_url, dest_path):
                        return True
    except Exception:
        pass
    return False


def extract_broll_cues(client, creative_script: str, video_duration: float, context_hint: str) -> list[dict]:
    """Maps exact sentences/phrases of the script to timed English search queries for online images/videos."""
    num_cues = max(1, min(5, int(video_duration // 3.0)))
    cue_prompt = f"""
    You are a video editor syncing online B-roll images and videos to the exact points of a voiceover script.
    The total video duration is {video_duration:.1f} seconds.
    Exact Voiceover Script: "{creative_script}"
    Additional Context: "{context_hint or 'none'}"

    Break the script down chronologically into {num_cues} key visual moments.
    Calculate the exact `start` and `end` second (within 0.0 to {video_duration:.1f}) when each phrase is spoken aloud.
    Ensure timestamps do NOT overlap and each cue lasts 2.0 to 3.5 seconds.

    Return ONLY a raw JSON list of objects with these exact keys:
    [
      {{
        "start": 0.5,
        "end": 3.0,
        "query": "specific English search query for Wikimedia/Pexels matching that exact script point",
        "fallback_query": "simpler 2-word English search query",
        "script_phrase": "the exact phrase from the script being spoken at this moment"
      }}
    ]
    Output ONLY valid JSON, no markdown fences, no commentary.
    """
    try:
        resp = generate_content_with_retry(
            client,
            model="gemini-3.6-flash",
            contents=[cue_prompt],
            config=types.GenerateContentConfig(temperature=0.2)
        )
        raw_text = (resp.text or "").strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            if raw_text.lower().startswith("json"):
                raw_text = raw_text[4:].strip()
        cues = json.loads(raw_text)
        valid_cues = []
        last_end = 0.2
        for c in cues:
            st_t = max(last_end, float(c.get("start", 0.5)))
            end_t = min(video_duration - 0.2, float(c.get("end", st_t + 2.5)))
            if end_t - st_t >= 1.2:
                valid_cues.append({
                    "start": round(st_t, 2),
                    "end": round(end_t, 2),
                    "query": str(c.get("query", "cricket stadium")).strip(),
                    "fallback_query": str(c.get("fallback_query", "cricket match")).strip(),
                    "script_phrase": str(c.get("script_phrase", "")).strip()
                })
                last_end = end_t + 0.3
        return valid_cues
    except Exception:
        return []


def apply_broll_overlays_ffmpeg(base_video: str, downloaded_brolls: list[dict], output_path: str, display_style: str) -> bool:
    """Uses FFmpeg filter_complex to overlay multiple timed images/videos at their exact script timestamps."""
    if not downloaded_brolls:
        return False

    vid_w, vid_h = get_video_dimensions(base_video)
    base_dur = get_file_duration(base_video)
    cmd = ["ffmpeg", "-y", "-i", base_video]

    for item in downloaded_brolls:
        if item["type"] == "image":
            cmd.extend(["-loop", "1", "-t", str(base_dur), "-i", item["path"]])
        else:
            cmd.extend(["-stream_loop", "-1", "-t", str(base_dur), "-i", item["path"]])

    filter_parts = []
    last_label = "0:v"

    for idx, item in enumerate(downloaded_brolls, start=1):
        st_t = item["start"]
        end_t = item["end"]
        b_label = f"broll{idx}"
        out_label = f"vout{idx}"

        if display_style.startswith("Full-Screen"):
            target_w, target_h = vid_w, vid_h
            pos_expr = "0:0"
            box_filter = (
                f"[{idx}:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
                f"crop={target_w}:{target_h},setsar=1[{b_label}]"
            )
        elif display_style.startswith("Top-Center"):
            target_w = int(vid_w * 0.72)
            target_h = int(vid_h * 0.32)
            target_w -= target_w % 2
            target_h -= target_h % 2
            pos_expr = f"(W-w)/2:{int(vid_h * 0.08)}"
            box_filter = (
                f"[{idx}:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
                f"crop={target_w}:{target_h},"
                f"drawbox=x=0:y=0:w=iw:h=ih:color=white@0.9:t=6,setsar=1[{b_label}]"
            )
        else:
            target_w = int(vid_w * 0.44)
            target_h = int(vid_h * 0.28)
            target_w -= target_w % 2
            target_h -= target_h % 2
            pos_expr = f"W-w-{int(vid_w * 0.04)}:{int(vid_h * 0.06)}"
            box_filter = (
                f"[{idx}:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
                f"crop={target_w}:{target_h},"
                f"drawbox=x=0:y=0:w=iw:h=ih:color=white@0.9:t=5,setsar=1[{b_label}]"
            )

        filter_parts.append(box_filter)
        overlay_filter = (
            f"[{last_label}][{b_label}]overlay={pos_expr}:enable='between(t,{st_t},{end_t})':eof_action=pass[{out_label}]"
        )
        filter_parts.append(overlay_filter)
        last_label = out_label

    filter_complex_str = ";".join(filter_parts)
    cmd.extend([
        "-filter_complex", filter_complex_str,
        "-map", f"[{last_label}]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-an",
        output_path
    ])

    try:
        subprocess.run(cmd, capture_output=True, check=True)
        return os.path.exists(output_path)
    except Exception:
        return False


uploaded_file = st.file_uploader("Upload MP4 Video File", type=["mp4"])

if uploaded_file is not None:
    temp_video = "temp_input.mp4"
    script_audio = "generated_voice.mp3"
    fitted_audio = "fitted_voice.wav"
    video_with_broll = "video_with_broll.mp4"
    output_video = "output_hooked.mp4"

    with open(temp_video, "wb") as f:
        f.write(uploaded_file.getbuffer())

    st.video(temp_video)

    if st.button("🚀 Analyze Video & Overlay Viral Hook"):
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

        custom_story_mode = (script_style == "Custom Story Mode (Exact Script + Auto B-Roll)")
        if custom_story_mode and not user_story.strip():
            st.error("Please paste your script in the sidebar 'Paste Your Exact Script' box first.")
            st.stop()

        cleanup_temp_files()
        with open(temp_video, "wb") as f:
            f.write(uploaded_file.getbuffer())

        client = genai.Client(api_key=api_key)

        with st.status("Processing Script, Voiceover & Online B-Roll Overlays...", expanded=True) as status:

            # 1. Video Duration
            video_duration = get_file_duration(temp_video)
            st.write(f"⏱️ Video Duration: **{video_duration:.2f} seconds**")

            target_lang = selected_voice_info["lang"]
            script_type = selected_voice_info["script_type"]

            # IF CUSTOM STORY MODE: Use the user's exact script 100% verbatim without changing anything!
            if custom_story_mode:
                creative_script = user_story.strip()
                st.write("✅ Using your exact script verbatim (zero changes made).")
            else:
                # 2. Upload Video to Gemini File API for AI-Generated Modes
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
                st.write(f"🤖 Gemini 3.6 Flash is analyzing video & writing a structured **{script_style}** script in **{target_lang}**...")

                sidhu_mode = script_style.startswith("Sidhu Paaji")
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

                # 3b. PASS 2 - write the script
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

            st.markdown(f"**Script Used for Voiceover ({target_lang}):**\n> {creative_script}")

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

            # 5b. Automated Online B-Roll Search & Timed Video Overlay
            video_source_for_mux = temp_video
            if enable_broll:
                st.write("🌐 Finding online B-roll images & videos synced to exact points in your script...")
                cues = extract_broll_cues(client, creative_script, video_duration, match_context)
                downloaded_brolls = []
                p_key = (pexels_api_key or os.environ.get("PEXELS_API_KEY") or "").strip()

                for idx, cue in enumerate(cues):
                    q = cue["query"]
                    fb_q = cue["fallback_query"]
                    found_path = None
                    found_type = None

                    # 1. Try Pexels Video if user wants videos and provided a Pexels key
                    if broll_media_preference in ["Images & Videos (Mixed)", "Videos Only (Requires Pexels Key)"] and p_key:
                        vid_candidate = f"broll_item_{idx}.mp4"
                        if fetch_pexels_video(q, p_key, vid_candidate) or fetch_pexels_video(fb_q, p_key, vid_candidate):
                            found_path = vid_candidate
                            found_type = "video"

                    # 2. Try Wikimedia Commons (Free, No Key) or Pexels Image
                    if not found_path and broll_media_preference != "Videos Only (Requires Pexels Key)":
                        img_candidate = f"broll_item_{idx}.jpg"
                        if (
                            fetch_wikimedia_image(q, img_candidate)
                            or (p_key and fetch_pexels_image(q, p_key, img_candidate))
                            or fetch_wikimedia_image(fb_q, img_candidate)
                            or (p_key and fetch_pexels_image(fb_q, p_key, img_candidate))
                        ):
                            found_path = img_candidate
                            found_type = "image"

                    if found_path and found_type:
                        downloaded_brolls.append({
                            "path": found_path,
                            "type": found_type,
                            "start": cue["start"],
                            "end": cue["end"],
                            "query": q,
                            "phrase": cue["script_phrase"]
                        })
                        st.write(f"  ✔️ **[{cue['start']}s – {cue['end']}s]** Added online {found_type} for `{q}` (*\"{cue['script_phrase']}\"* )")
                    else:
                        st.write(f"  ⚠️ No online media found for `{q}` — keeping original video frame.")

                if downloaded_brolls:
                    st.write("🖼️ Overlaying fetched online images/videos at exact script timestamps via FFmpeg...")
                    if apply_broll_overlays_ffmpeg(temp_video, downloaded_brolls, video_with_broll, broll_display_style):
                        video_source_for_mux = video_with_broll

            # 6. Mux Final Audio/Video (Full Video Preserved)
            st.write("🎬 Muxing synced audio into final video via FFmpeg...")
            subprocess.run([
                "ffmpeg", "-y",
                "-i", video_source_for_mux,
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

            status.update(label="✨ Script, Voiceover & Online B-Roll Successfully Overlaid!", state="complete", expanded=False)

        st.subheader("🔥 Final Video Output")
        st.video(output_video)
