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
st.title("🎬 Direct Multimodal Video Hook & Free Auto-Video Generator")

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

script_style = st.sidebar.selectbox(
    "Hook / Script Style",
    [
        "Custom Story Mode (Exact Script + Free Auto Video)",
        "Sidhu Paaji Commentary (Oye Guru! Thoko Taali!)",
        "Soul Lines Paaji Mode (Hook-Hero-Roast-Closer)",
        "High-Dopamine Viral Opening",
        "Viral Explanation Mode (Hook-Scoop-Twist)",
        "Cinematic Storytelling",
        "Humorous & Punchy",
        "Explainer Hook"
    ]
)

custom_story_mode = (script_style == "Custom Story Mode (Exact Script + Free Auto Video)")

if not custom_story_mode:
    auto_fit_audio = st.sidebar.checkbox(
        "🔄 Auto-fit voice duration to match full video",
        value=True,
        help="Stretches or compresses the audio slightly so the voiceover starts at 0s and finishes right as the video ends."
    )
    user_story = ""
    match_context = st.sidebar.text_area(
        "Match / player context (recommended)",
        placeholder="e.g. India vs Pakistan Asian Games final. Abhishek Sharma 61 off 28, Tilak Varma 51* off 22. India won by 19 runs.",
        help="Gemini does not identify people by face. Put the real names, teams and scores here and they will be used in the script."
    )
else:
    auto_fit_audio = False
    user_story = st.sidebar.text_area(
        "📖 Paste Your Exact Script (No Video Upload Needed!)",
        height=180,
        placeholder="Paste your exact voiceover script here. The AI will speak your script 100% as-is and automatically build a full HD vertical video using free online photos, Wikimedia videos & AI visuals!",
        help="Your script is spoken verbatim and converted into a full vertical video without needing any video upload or paid keys."
    )
    match_context = st.sidebar.text_input(
        "🔍 Optional Topic / Visual Hint (Helps find exact real photos)",
        placeholder="e.g. Rohit Sharma, India vs Australia Cricket World Cup",
    )

# --- 100% FREE HD VISUALS SIDEBAR SETTINGS ---
st.sidebar.markdown("---")
st.sidebar.subheader("🖼️ Free HD Auto-Visuals (No Key Needed)")

if custom_story_mode:
    enable_broll = True
    st.sidebar.success("✨ **Direct Script-to-Video Mode:** Automatically fetches real photos/videos from Wikipedia + Wikimedia Commons + Free HD AI visuals with smooth Ken Burns zoom motion.")
else:
    enable_broll = st.sidebar.checkbox(
        "✨ Auto-overlay free online Images/Videos at exact script points",
        value=True,
        help="Finds real photos, Wikimedia videos & HD visuals matching specific sentences in your script and overlays them at the exact timestamp."
    )

free_visual_source = st.sidebar.selectbox(
    "Free Visual Source Priority",
    [
        "Smart Mix (Real Wikipedia/Wikimedia Photos & Videos + Free AI HD Scenes)",
        "Real Photos & Videos Only (Wikipedia + Wikimedia Commons)",
        "100% AI Generated HD Vertical Scenes (Free Pollinations Flux)"
    ],
    disabled=not enable_broll
)

if not custom_story_mode:
    broll_display_style = st.sidebar.selectbox(
        "B-Roll Overlay Style",
        [
            "Top-Right Picture-in-Picture Card (Keeps Main Video Visible)",
            "Top-Center Dynamic Pop-Up Card",
            "Full-Screen Cutaway (Replaces Frame During Cue)"
        ],
        disabled=not enable_broll
    )
else:
    broll_display_style = "Full-Screen Cutaway (Replaces Frame During Cue)"


def cleanup_temp_files():
    patterns = [
        "temp_input.mp4", "generated_voice.mp3", "fitted_voice.wav",
        "video_with_broll.mp4", "output_hooked.mp4", "broll_item_*",
        "broll_seg_*", "broll_seg_list.txt"
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


# --- 100% FREE, NO-API-KEY HIGH-QUALITY MEDIA FETCHERS ---
def download_url_to_file(url: str, dest_path: str, timeout: int = 15) -> bool:
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest_path, "wb") as out:
            out.write(resp.read())
        return os.path.exists(dest_path) and os.path.getsize(dest_path) > 2500
    except Exception:
        return False


def fetch_wikipedia_page_image(query: str, dest_path: str) -> bool:
    """Fetches high-res lead article photo directly from English Wikipedia (Great for real players, teams, stadiums, people)."""
    try:
        encoded_q = urllib.parse.quote(query)
        url = (
            f"https://en.wikipedia.org/w/api.php?action=query&generator=search"
            f"&gsrsearch={encoded_q}&gsrlimit=3&prop=pageimages"
            f"&piprop=original|thumbnail&pithumbsize=1280&format=json"
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "SoulLinesHookGenerator/2.0 (https://streamlit.io)"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        pages = data.get("query", {}).get("pages", {})
        # Sort by search index so best match comes first
        sorted_pages = sorted(pages.values(), key=lambda x: x.get("index", 99))
        for page in sorted_pages:
            img_url = page.get("original", {}).get("source") or page.get("thumbnail", {}).get("source")
            if img_url and any(img_url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                if download_url_to_file(img_url, dest_path):
                    return True
    except Exception:
        pass
    return False


def fetch_wikimedia_image(query: str, dest_path: str) -> bool:
    """Free, zero-API-key high-res image search from Wikimedia Commons."""
    try:
        encoded_q = urllib.parse.quote(query)
        url = (
            f"https://commons.wikimedia.org/w/api.php?action=query&generator=search"
            f"&gsrsearch=filetype:bitmap%20{encoded_q}&gsrlimit=6&prop=imageinfo"
            f"&iiprop=url&iiurlwidth=1280&format=json"
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "SoulLinesHookGenerator/2.0 (https://streamlit.io)"}
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


def fetch_wikimedia_video(query: str, dest_path: str) -> bool:
    """Free, zero-API-key video search from Wikimedia Commons (.webm / .mp4 clips)."""
    try:
        encoded_q = urllib.parse.quote(query)
        url = (
            f"https://commons.wikimedia.org/w/api.php?action=query&generator=search"
            f"&gsrsearch=filetype:video%20{encoded_q}&gsrlimit=4&prop=imageinfo"
            f"&iiprop=url|size&format=json"
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "SoulLinesHookGenerator/2.0 (https://streamlit.io)"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        pages = data.get("query", {}).get("pages", {})
        for _, page in pages.items():
            ii = page.get("imageinfo", [])
            if ii:
                vid_url = ii[0].get("url")
                file_size = int(ii[0].get("size", 0))
                # Only download reasonably sized clips (<25MB) so processing stays fast
                if vid_url and 10000 < file_size < 25_000_000 and any(vid_url.lower().endswith(ext) for ext in [".webm", ".mp4", ".ogv"]):
                    if download_url_to_file(vid_url, dest_path, timeout=18):
                        return True
    except Exception:
        pass
    return False


def fetch_free_ai_hd_image(visual_prompt: str, dest_path: str, seed: int = 42) -> bool:
    """100% Free, Zero-Key HD 720x1280 Vertical Scene Generator via Pollinations AI."""
    try:
        clean_prompt = (
            f"{visual_prompt}, ultra detailed cinematic sports broadcast photography, "
            f"dramatic stadium lighting, 8k resolution, photorealistic, vertical reel composition"
        )
        encoded_p = urllib.parse.quote(clean_prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_p}?width=720&height=1280&seed={seed}&nologo=true"
        return download_url_to_file(url, dest_path, timeout=20)
    except Exception:
        return False


def extract_broll_cues(client, creative_script: str, total_duration: float, context_hint: str, contiguous: bool = False) -> list[dict]:
    """Maps exact sentences/phrases of the script to timed English search queries & visual scene prompts."""
    if contiguous:
        num_cues = max(3, min(8, int(round(total_duration / 2.5))))
        timing_rule = (
            f"Split the entire {total_duration:.2f}s timeline into {num_cues} CONTIGUOUS, BACK-TO-BACK scenes "
            f"from 0.0 to {total_duration:.2f} with ZERO gaps (scene 1 starts at 0.0, scene 2 starts where scene 1 ends, "
            f"and the final scene ends at {total_duration:.2f})."
        )
    else:
        num_cues = max(1, min(5, int(total_duration // 3.0)))
        timing_rule = (
            f"Identify {num_cues} key visual moments spread across the {total_duration:.1f}s timeline. "
            f"Ensure timestamps do NOT overlap and each cue lasts 2.0 to 3.5 seconds."
        )

    cue_prompt = f"""
    You are a video director syncing online B-roll visuals to the exact points of a voiceover script.
    The total audio/video duration is {total_duration:.2f} seconds.
    Exact Voiceover Script: "{creative_script}"
    Additional Context: "{context_hint or 'none'}"

    {timing_rule}

    Return ONLY a raw JSON list of objects with these exact keys:
    [
      {{
        "start": 0.0,
        "end": 2.8,
        "wiki_entity": "exact Wikipedia article title for the real person, team, stadium, or trophy mentioned in this line (e.g. 'Rohit Sharma', 'India national cricket team', 'Wankhede Stadium')",
        "query": "specific English search query for Wikimedia Commons (e.g. 'Rohit Sharma batting', 'cricket stadium cheering')",
        "ai_scene_prompt": "vivid English visual description of this exact moment in the script for generating an HD scene (e.g. 'Indian cricketer hitting a massive six in a packed floodlit stadium, crowd roaring with Indian flags')",
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
        if not cues:
            return []

        if contiguous:
            valid_cues = []
            cur_start = 0.0
            n = len(cues)
            for i, c in enumerate(cues):
                if i == n - 1:
                    end_t = round(total_duration, 2)
                else:
                    raw_end = float(c.get("end", cur_start + (total_duration / n)))
                    end_t = round(max(cur_start + 1.0, min(total_duration - 0.5, raw_end)), 2)
                if end_t > cur_start:
                    valid_cues.append({
                        "start": round(cur_start, 2),
                        "end": end_t,
                        "wiki_entity": str(c.get("wiki_entity", "")).strip(),
                        "query": str(c.get("query", "cricket stadium")).strip(),
                        "ai_scene_prompt": str(c.get("ai_scene_prompt", "cricket match stadium action")).strip(),
                        "script_phrase": str(c.get("script_phrase", "")).strip()
                    })
                    cur_start = end_t
            return valid_cues
        else:
            valid_cues = []
            last_end = 0.2
            for c in cues:
                st_t = max(last_end, float(c.get("start", 0.5)))
                end_t = min(total_duration - 0.2, float(c.get("end", st_t + 2.5)))
                if end_t - st_t >= 1.2:
                    valid_cues.append({
                        "start": round(st_t, 2),
                        "end": round(end_t, 2),
                        "wiki_entity": str(c.get("wiki_entity", "")).strip(),
                        "query": str(c.get("query", "cricket stadium")).strip(),
                        "ai_scene_prompt": str(c.get("ai_scene_prompt", "cricket match stadium action")).strip(),
                        "script_phrase": str(c.get("script_phrase", "")).strip()
                    })
                    last_end = end_t + 0.3
            return valid_cues
    except Exception:
        if contiguous:
            return [{
                "start": 0.0,
                "end": round(total_duration, 2),
                "wiki_entity": context_hint.strip() or "India national cricket team",
                "query": context_hint.strip() or "cricket stadium crowd",
                "ai_scene_prompt": f"Dramatic scene of {context_hint.strip() or 'cricket match in packed stadium'}",
                "script_phrase": creative_script[:60]
            }]
        return []


def fetch_free_media_for_cues(cues: list[dict], source_pref: str) -> list[dict]:
    """Fetches high-resolution visuals using 100% free methods (Wikipedia API, Wikimedia Video/Image API, and Pollinations AI HD)."""
    downloaded = []
    for idx, cue in enumerate(cues):
        wiki_ent = cue.get("wiki_entity", "")
        q = cue.get("query", "")
        ai_prompt = cue.get("ai_scene_prompt", q)
        found_path = None
        found_type = None
        source_label = ""

        # Option A: Pure AI HD Scenes
        if source_pref.startswith("100% AI"):
            img_candidate = f"broll_item_{idx}.jpg"
            if fetch_free_ai_hd_image(ai_prompt, img_candidate, seed=100 + idx):
                found_path = img_candidate
                found_type = "image"
                source_label = "Free AI HD Scene"

        # Option B: Smart Mix or Real Photos/Videos First
        if not found_path:
            # 1. Try Wikimedia Commons Video clip first
            vid_candidate = f"broll_item_{idx}.webm"
            if q and fetch_wikimedia_video(q, vid_candidate):
                found_path = vid_candidate
                found_type = "video"
                source_label = f"Wikimedia Video ({q})"

        if not found_path:
            # 2. Try Wikipedia High-Res Lead Image for the exact person/team/entity
            img_candidate = f"broll_item_{idx}.jpg"
            if wiki_ent and fetch_wikipedia_page_image(wiki_ent, img_candidate):
                found_path = img_candidate
                found_type = "image"
                source_label = f"Wikipedia HD ({wiki_ent})"
            elif q and fetch_wikimedia_image(q, img_candidate):
                found_path = img_candidate
                found_type = "image"
                source_label = f"Wikimedia Commons HD ({q})"
            elif q and fetch_wikipedia_page_image(q, img_candidate):
                found_path = img_candidate
                found_type = "image"
                source_label = f"Wikipedia HD ({q})"

        # 3. Automatic HD AI Scene Fallback so NO scene is ever missing or blank!
        if not found_path:
            img_candidate = f"broll_item_{idx}.jpg"
            if fetch_free_ai_hd_image(ai_prompt, img_candidate, seed=200 + idx):
                found_path = img_candidate
                found_type = "image"
                source_label = "Free AI HD Scene"

        if found_path and found_type:
            downloaded.append({
                "path": found_path,
                "type": found_type,
                "start": cue["start"],
                "end": cue["end"],
                "query": q or wiki_ent,
                "phrase": cue["script_phrase"]
            })
            st.write(f"  ✔️ **[{cue['start']}s – {cue['end']}s]** Added **{source_label}** for *\"{cue['script_phrase']}\"*")
        else:
            st.write(f"  ⚠️ Could not fetch visual for `{q}`.")
    return downloaded


def build_standalone_video_from_brolls(downloaded_brolls: list[dict], total_duration: float, output_path: str) -> bool:
    """Builds a 720x1280 vertical MP4 video with smooth Ken Burns dynamic zoom/pan motion on every image."""
    target_w, target_h = 720, 1280
    fps = 30

    if not downloaded_brolls:
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"color=c=0x12161f:s={target_w}x{target_h}:r={fps}:d={total_duration}",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            output_path
        ], capture_output=True, check=True)
        return os.path.exists(output_path)

    segment_files = []
    n = len(downloaded_brolls)
    cur_t = 0.0

    for idx, item in enumerate(downloaded_brolls):
        if idx == n - 1:
            seg_dur = max(0.8, round(total_duration - cur_t, 2))
        else:
            planned_dur = item["end"] - item["start"]
            seg_dur = max(1.0, round(planned_dur, 2))
            if cur_t + seg_dur > total_duration - 0.5:
                seg_dur = max(0.8, round((total_duration - cur_t) / (n - idx), 2))
        cur_t += seg_dur

        seg_path = f"broll_seg_{idx}.mp4"
        frames = max(24, int(round(seg_dur * fps)))

        if item["type"] == "image":
            # Alternate smooth Ken Burns zoom-in and zoom-out across scenes for broadcast documentary feel
            if idx % 2 == 0:
                zoom_expr = "min(zoom+0.0018,1.22)"
            else:
                zoom_expr = "if(eq(on,1),1.20,max(1.0,zoom-0.0018))"

            vf_chain = (
                f"scale=1440:2560:force_original_aspect_ratio=increase,"
                f"crop=1440:2560,"
                f"zoompan=z='{zoom_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={target_w}x{target_h}:fps={fps},"
                f"setsar=1,format=yuv420p"
            )
            cmd = [
                "ffmpeg", "-y", "-i", item["path"],
                "-vf", vf_chain,
                "-t", str(seg_dur),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                "-an", seg_path
            ]
        else:
            vf_chain = (
                f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
                f"crop={target_w}:{target_h},setsar=1,fps={fps},format=yuv420p"
            )
            cmd = [
                "ffmpeg", "-y", "-stream_loop", "-1", "-t", str(seg_dur),
                "-i", item["path"],
                "-vf", vf_chain,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                "-an", seg_path
            ]

        try:
            subprocess.run(cmd, capture_output=True, check=True)
            if os.path.exists(seg_path):
                segment_files.append(seg_path)
        except Exception:
            # Fallback simple scale if zoompan fails on an unusual image format
            fallback_vf = f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h},setsar=1,fps={fps},format=yuv420p"
            try:
                subprocess.run([
                    "ffmpeg", "-y", "-loop", "1", "-t", str(seg_dur),
                    "-i", item["path"], "-vf", fallback_vf,
                    "-c:v", "libx264", "-preset", "veryfast", "-an", seg_path
                ], capture_output=True, check=True)
                if os.path.exists(seg_path):
                    segment_files.append(seg_path)
            except Exception:
                pass

    if not segment_files:
        return False

    concat_list_path = "broll_seg_list.txt"
    with open(concat_list_path, "w", encoding="utf-8") as f:
        for seg in segment_files:
            f.write(f"file '{seg}'\n")

    try:
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_list_path,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-pix_fmt", "yuv420p",
            output_path
        ], capture_output=True, check=True)
        return os.path.exists(output_path)
    except Exception:
        return False


def apply_broll_overlays_ffmpeg(base_video: str, downloaded_brolls: list[dict], output_path: str, display_style: str) -> bool:
    """Uses FFmpeg filter_complex to overlay multiple timed images/videos onto an uploaded video."""
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
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-an",
        output_path
    ])

    try:
        subprocess.run(cmd, capture_output=True, check=True)
        return os.path.exists(output_path)
    except Exception:
        return False


# --- MAIN PAGE EXECUTION ---
temp_video = "temp_input.mp4"
script_audio = "generated_voice.mp3"
fitted_audio = "fitted_voice.wav"
video_with_broll = "video_with_broll.mp4"
output_video = "output_hooked.mp4"

# MODE A: DIRECT SCRIPT-TO-VIDEO (NO VIDEO UPLOAD, NO PEXELS KEY NEEDED)
if custom_story_mode:
    st.info(
        "🎬 **Direct Script-to-Video Mode (100% Free HD Visuals):** No video upload needed! "
        "Paste your script in the sidebar and click the button below. The app speaks your exact script as-is "
        "and builds a full vertical video with dynamic zoom motion using Wikipedia HD photos, Wikimedia videos, and Free AI scenes."
    )

    if st.button("🚀 Generate Full HD Video Directly from Script"):
        api_key = (gemini_api_key or os.environ.get("GEMINI_API_KEY") or "").strip()
        if not api_key:
            st.error("Please enter your Gemini API Key in the sidebar.")
            st.stop()
        if not api_key.isascii() or len(api_key) > 100 or any(c.isspace() for c in api_key):
            st.error("The Gemini API key looks invalid. Please paste only the ~39-character key starting with 'AIza'.")
            st.stop()
        if not user_story.strip():
            st.error("Please paste your script in the sidebar 'Paste Your Exact Script' box first.")
            st.stop()

        cleanup_temp_files()
        client = genai.Client(api_key=api_key)

        with st.status("Generating Voiceover & Building HD Video from Free Online Media...", expanded=True) as status:
            creative_script = user_story.strip()
            target_lang = selected_voice_info["lang"]
            st.markdown(f"**Exact Script Used ({target_lang}):**\n> {creative_script}")

            # 1. Generate Voiceover First
            if selected_voice_info["engine"] == "gemini":
                st.write(f"🎙️ Generating AI voiceover using Gemini ({selected_voice_info['code']})...")
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
                st.write(f"🎙️ Synthesizing voiceover via Edge-TTS ({selected_voice_info['code']})...")
                asyncio.run(synthesize_voice(
                    text=creative_script,
                    voice=selected_voice_info["code"],
                    output_path=script_audio,
                    rate=rate_str,
                    pitch=pitch_str
                ))

            # 2. Apply user speed multiplier & normalize to -14.0 LUFS
            final_tempo = voice_speed
            audio_filter = f"atempo={final_tempo},loudnorm=I=-14.0:TP=-1.5:LRA=11"

            subprocess.run([
                "ffmpeg", "-y", "-i", script_audio,
                "-filter:a", audio_filter,
                "-ar", "48000", "-ac", "2",
                fitted_audio
            ], capture_output=True, check=True)

            total_duration = get_file_duration(fitted_audio)
            st.write(f"⏱️ Final Voiceover Duration: **{total_duration:.2f} seconds** (Speed: {final_tempo:.2f}x)")

            # 3. Extract contiguous scene cues & fetch free HD images/videos
            st.write("🌐 Mapping script lines to visual scenes & downloading free HD photos/videos...")
            cues = extract_broll_cues(client, creative_script, total_duration, match_context, contiguous=True)
            downloaded_brolls = fetch_free_media_for_cues(cues, free_visual_source)

            # 4. Assemble standalone vertical video with Ken Burns zoom motion
            st.write("🎞️ Rendering 720x1280 HD vertical scenes with smooth Ken Burns zoom motion...")
            if not build_standalone_video_from_brolls(downloaded_brolls, total_duration, video_with_broll):
                st.error("Failed to assemble video from online media.")
                st.stop()

            # 5. Mux voiceover audio with assembled video
            st.write("🎬 Muxing voiceover into final HD video via FFmpeg...")
            subprocess.run([
                "ffmpeg", "-y",
                "-i", video_with_broll,
                "-i", fitted_audio,
                "-c:v", "copy",
                "-c:a", "aac",
                "-ar", "48000",
                "-ac", "2",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-t", str(total_duration),
                output_video
            ], check=True)

            status.update(label="✨ Full HD Video Automatically Built from Your Script!", state="complete", expanded=False)

        st.subheader("🔥 Final Video Output")
        st.video(output_video)
        with open(output_video, "rb") as f_dl:
            st.download_button("⬇️ Download Final HD Video (MP4)", data=f_dl, file_name="auto_script_video.mp4", mime="video/mp4")

# MODE B: UPLOAD VIDEO MODES (Sidhu Paaji, Soul Lines, Viral Hook Modes)
else:
    uploaded_file = st.file_uploader("Upload MP4 Video File", type=["mp4"])

    if uploaded_file is not None:
        with open(temp_video, "wb") as f:
            f.write(uploaded_file.getbuffer())

        st.video(temp_video)

        if st.button("🚀 Analyze Video & Overlay Viral Hook"):
            api_key = (gemini_api_key or os.environ.get("GEMINI_API_KEY") or "").strip()
            if not api_key:
                st.error("Please enter your Gemini API Key in the sidebar.")
                st.stop()
            if not api_key.isascii() or len(api_key) > 100 or any(c.isspace() for c in api_key):
                st.error("The Gemini API key looks invalid. Please paste only the ~39-character key starting with 'AIza'.")
                st.stop()

            cleanup_temp_files()
            with open(temp_video, "wb") as f:
                f.write(uploaded_file.getbuffer())

            client = genai.Client(api_key=api_key)

            with st.status("Analyzing Video & Building Synced Audio + Free B-Roll Overlay...", expanded=True) as status:

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
                target_lang = selected_voice_info["lang"]
                script_type = selected_voice_info["script_type"]
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

                # 5b. Automated Free Online B-Roll Search & Timed Video Overlay
                video_source_for_mux = temp_video
                if enable_broll:
                    st.write("🌐 Finding free HD online B-roll images/videos synced to exact points in your script...")
                    cues = extract_broll_cues(client, creative_script, video_duration, match_context, contiguous=False)
                    downloaded_brolls = fetch_free_media_for_cues(cues, free_visual_source)

                    if downloaded_brolls:
                        st.write("🖼️ Overlaying fetched HD visuals at exact script timestamps via FFmpeg...")
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

                status.update(label="✨ Script, Voiceover & Free HD B-Roll Successfully Overlaid!", state="complete", expanded=False)

            st.subheader("🔥 Final Video Output")
            st.video(output_video)
            with open(output_video, "rb") as f_dl:
                st.download_button("⬇️ Download Final HD Video (MP4)", data=f_dl, file_name="hooked_video.mp4", mime="video/mp4")
