import os
import re
import json
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
st.title("🎬 Frame-Synced Multimodal Video Hook & Voiceover Studio")

# Sidebar Configuration
st.sidebar.header("⚙️ Settings")
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

selected_voice_label = st.sidebar.selectbox("🎙️ Voice Model & Language", list(VOICE_OPTIONS.keys()))
selected_voice_info = VOICE_OPTIONS[selected_voice_label]

script_style = st.sidebar.selectbox(
    "🎨 Hook / Script Style",
    [
        "Sidhu Paaji Commentary (Oye Guru! Thoko Taali)",
        "Soul Lines Paaji Mode (Hook-Hero-Roast-Closer)",
        "High-Dopamine Viral Opening", 
        "Viral Explanation Mode (Hook-Scoop-Twist)", 
        "Cinematic Storytelling", 
        "Humorous & Punchy", 
        "Explainer Hook"
    ]
)

st.sidebar.divider()
sync_mode = st.sidebar.radio(
    "🎯 Audio-Video Sync Mode",
    [
        "Timestamped Beat Sync (Locks voice lines to exact scene timestamps)",
        "Exact Duration Lock (Stretches/fits 1 continuous script to exact video length)"
    ],
    index=0,
    help="Timestamped Beat Sync ensures the voice never talks about a scene before it actually happens on screen."
)

auto_adjust_video_speed = st.sidebar.checkbox(
    "🎞️ Allow slight video speed adjustment if voice is too long",
    value=False,
    help="If checked, slightly slows down the video instead of rushing the voice when the script has too many words."
)


def cleanup_temp_files():
    patterns = [
        "temp_input.mp4", "generated_voice.*", "fitted_voice.wav",
        "beat_*.wav", "beat_*.mp3", "output_hooked.mp4"
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


def get_file_state_str(file_obj):
    state = getattr(file_obj, "state", None)
    if hasattr(state, "name"):
        return state.name
    return str(state).upper()


def build_atempo_filter(tempo: float) -> str:
    """Builds a safe FFmpeg atempo chain for any speed between 0.5x and 3.0x."""
    tempo = max(0.5, min(tempo, 3.0))
    filters = []
    while tempo > 2.0:
        filters.append("atempo=2.0")
        tempo /= 2.0
    while tempo < 0.5:
        filters.append("atempo=0.5")
        tempo /= 0.5
    filters.append(f"atempo={tempo:.4f}")
    return ",".join(filters)


def save_gemini_audio_properly(raw_bytes: bytes, output_wav_path: str):
    if isinstance(raw_bytes, str):
        raw_bytes = base64.b64decode(raw_bytes)

    if raw_bytes[:4] == b"RIFF":
        with open(output_wav_path, "wb") as f:
            f.write(raw_bytes)
    else:
        with wave.open(output_wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(raw_bytes)


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
    if hasattr(client, "interactions"):
        for tts_model in ["gemini-3.8-flash-tts", "gemini-3.1-flash-tts-preview"]:
            try:
                interaction = client.interactions.create(
                    model=tts_model,
                    input=[{
                        "type": "user_input",
                        "content": [{"type": "text", "text": text}]
                    }],
                    response_format={"type": "audio"},
                    generation_config={"speech_config": [{"voice": voice_name}]}
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

    raise RuntimeError(f"Gemini TTS synthesis failed. Last error: {last_error}")


async def synthesize_edge_voice(text: str, voice: str, output_path: str):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


def synthesize_any_voice(client, text: str, voice_info: dict, base_filename: str) -> str:
    """Synthesizes speech using selected engine, trims dead silence at edges, and returns clean WAV path."""
    raw_path = f"{base_filename}_raw.wav" if voice_info["engine"] == "gemini" else f"{base_filename}_raw.mp3"
    trimmed_wav = f"{base_filename}_clean.wav"

    if voice_info["engine"] == "gemini":
        synthesize_gemini_voice(client, text, voice_info["code"], raw_path)
    else:
        asyncio.run(synthesize_edge_voice(text, voice_info["code"], raw_path))

    # Strip leading/trailing silence so audio starts on the exact frame without lag
    subprocess.run([
        "ffmpeg", "-y", "-i", raw_path,
        "-af", "silenceremove=start_periods=1:start_silence=0.05:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_silence=0.05:start_threshold=-45dB,areverse",
        "-ar", "24000", "-ac", "1",
        trimmed_wav
    ], capture_output=True, check=True)

    return trimmed_wav


uploaded_file = st.file_uploader("Upload MP4 Video File", type=["mp4"])

if uploaded_file is not None:
    temp_video = "temp_input.mp4"
    fitted_audio = "fitted_voice.wav"
    output_video = "output_hooked.mp4"

    with open(temp_video, "wb") as f:
        f.write(uploaded_file.getbuffer())

    st.video(temp_video)

    if st.button("🚀 Analyze Video & Overlay Frame-Synced Voiceover", type="primary", use_container_width=True):
        api_key = (gemini_api_key or os.environ.get("GEMINI_API_KEY", "")).strip()
        if not api_key:
            st.error("Please enter your Gemini API Key in the sidebar.")
            st.stop()

        cleanup_temp_files()
        with open(temp_video, "wb") as f:
            f.write(uploaded_file.getbuffer())

        client = genai.Client(
            api_key=api_key,
            http_options={"api_version": "v1beta"}
        )

        with st.status("Analyzing Video Timestamps & Building Synced Audio...", expanded=True) as status:

            # 1. Video Duration
            video_duration = get_file_duration(temp_video)
            st.write(f"⏱️ Video Duration: **{video_duration:.2f} seconds**")

            # 2. Upload Video to Gemini File API
            st.write("📹 Uploading video to Gemini for frame-accurate visual timeline analysis...")
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

            target_lang = selected_voice_info["lang"]
            script_type = selected_voice_info["script_type"]

            # =========================================================================
            # MODE A: TIMESTAMPED BEAT-BY-BEAT SYNC (LOCKS VOICE TO EXACT VIDEO MOMENTS)
            # =========================================================================
            if "Timestamped Beat Sync" in sync_mode:
                num_beats = max(2, min(5, int(round(video_duration / 4.0))))
                st.write(f"🤖 Gemini is mapping **{num_beats} visual time-segments** in **{target_lang}** so voice never outruns the video...")

                prompt = f"""
                You are an expert viral video commentator synchronizing a voiceover to a {video_duration:.1f}-second video.
                Watch the exact visual timeline of this video and divide it into {num_beats} sequential time segments covering 0.0 to {video_duration:.1f} seconds.
                
                Style: {script_style}
                Language Requirement: Write EVERY spoken line natively in {target_lang} using {script_type}.

                CRITICAL SYNC RULES:
                1. Each segment's spoken text MUST describe ONLY what is happening on screen during that specific `start_sec` to `end_sec` window! Do NOT spoil future actions early!
                2. Keep each segment's text concise: strictly ~2.2 words per second of that segment's duration so the voice sounds natural and un-rushed.
                3. Output ONLY valid JSON in this exact format:
                [
                  {{
                    "start_sec": 0.0,
                    "end_sec": {round(video_duration / num_beats, 1)},
                    "visual_action": "What happens on screen right now",
                    "spoken_text": "Spoken line in {target_lang}"
                  }}
                ]
                """

                response = None
                last_script_err = None
                for vision_model in ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-2.5-flash"]:
                    try:
                        response = generate_content_with_retry(
                            client,
                            model=vision_model,
                            contents=[video_file, prompt],
                            config=types.GenerateContentConfig(response_mime_type="application/json")
                        )
                        break
                    except Exception as err:
                        last_script_err = err
                        continue

                try:
                    client.files.delete(name=video_file.name)
                except Exception:
                    pass

                if response is None or not response.text:
                    st.error(f"Error generating timestamped script: {last_script_err}")
                    st.stop()

                raw_json = response.text.strip()
                if raw_json.startswith("```"):
                    raw_json = raw_json.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

                beats = json.loads(raw_json)
                st.markdown("### 🕒 Frame-Synced Script Timeline")

                beat_files = []
                filter_parts = []
                mix_inputs = []

                for idx, beat in enumerate(beats):
                    start_s = max(0.0, float(beat.get("start_sec", 0.0)))
                    end_s = min(video_duration, float(beat.get("end_sec", video_duration)))
                    slot_duration = max(1.0, end_s - start_s)
                    text_line = str(beat.get("spoken_text", "")).strip()
                    visual_note = str(beat.get("visual_action", "")).strip()

                    if not text_line:
                        continue

                    st.markdown(f"- **`{start_s:.1f}s - {end_s:.1f}s`** ({visual_note}): {text_line}")

                    # Synthesize this beat
                    clean_beat_wav = synthesize_any_voice(client, text_line, selected_voice_info, f"beat_{idx}")
                    raw_beat_dur = get_file_duration(clean_beat_wav)

                    # Fit beat cleanly inside its exact time window so it never bleeds into the next scene
                    # If the audio is longer than the slot, speed it up to fit; if slightly shorter, keep natural 1.0x-1.08x pace
                    if raw_beat_dur > slot_duration * 0.96:
                        beat_tempo = raw_beat_dur / (slot_duration * 0.94)
                    else:
                        # Subtle natural energy without rushing ahead of the scene
                        beat_tempo = max(0.95, min(1.08, raw_beat_dur / (slot_duration * 0.85)))

                    atempo_str = build_atempo_filter(beat_tempo)
                    fitted_beat_wav = f"beat_{idx}_fitted.wav"
                    subprocess.run([
                        "ffmpeg", "-y", "-i", clean_beat_wav,
                        "-filter:a", atempo_str,
                        "-ar", "24000", "-ac", "1",
                        fitted_beat_wav
                    ], capture_output=True, check=True)

                    delay_ms = int(start_s * 1000)
                    beat_files.extend(["-i", fitted_beat_wav])
                    filter_parts.append(f"[{idx}:a]adelay={delay_ms}|{delay_ms}[a{idx}]")
                    mix_inputs.append(f"[a{idx}]")

                # Combine all timestamp-locked beats onto a single master audio track of exact video_duration
                amix_Script = (
                    ";".join(filter_parts)
                    + f";{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=longest:dropout_transition=0:normalize=0,apad,atrim=0:{video_duration}[aout]"
                )
                subprocess.run(
                    ["ffmpeg", "-y"] + beat_files + [
                        "-filter_complex", amix_Script,
                        "-map", "[aout]",
                        "-ar", "24000", "-ac", "1",
                        fitted_audio
                    ],
                    capture_output=True, check=True
                )

            # =========================================================================
            # MODE B: EXACT CONTINUOUS DURATION LOCK (1 SCRIPT PERFECTLY STRETCHED)
            # =========================================================================
            else:
                st.write(f"🤖 Gemini is writing a continuous **{script_style}** script calibrated for **{video_duration:.1f}s**...")
                target_words = max(8, int(video_duration * 2.4))

                prompt = f"""
                You are a master viral video content creator.
                Watch the visuals, movement, actions, and chronological order of events in this {video_duration:.1f}-second video.
                Write a continuous voiceover script in {target_lang} ({script_type}) that follows the exact chronological order of the video from start to finish.
                Style: {script_style}.
                
                CRITICAL PACING CONSTRAINT:
                - Write approximately {target_words} words so that when spoken at a natural 1.0x speed, it lasts {video_duration:.1f} seconds.
                - Output ONLY the plain spoken script in {target_lang}. No markdown, no labels.
                """

                response = None
                for vision_model in ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-2.5-flash"]:
                    try:
                        response = generate_content_with_retry(client, model=vision_model, contents=[video_file, prompt])
                        break
                    except Exception:
                        continue

                try:
                    client.files.delete(name=video_file.name)
                except Exception:
                    pass

                creative_script = response.text.strip() if (response and response.text) else ""
                if not creative_script:
                    st.error("Generated script was empty. Please try again.")
                    st.stop()

                st.markdown(f"**Generated Script ({target_lang}):**\n\n{creative_script}")

                # Synthesize single continuous voiceover and trim dead silence at edges
                clean_wav = synthesize_any_voice(client, creative_script, selected_voice_info, "generated_voice")
                audio_duration = get_file_duration(clean_wav)

                # Calculate exact ratio so audio finishes at the exact end of the video
                exact_tempo = audio_duration / (video_duration * 0.97)
                st.write(f"🎙️ Raw Voice Duration: **{audio_duration:.2f}s** ➔ Sync Ratio: **{exact_tempo:.2f}x**")

                atempo_chain = build_atempo_filter(exact_tempo)
                subprocess.run([
                    "ffmpeg", "-y", "-i", clean_wav,
                    "-filter:a", f"{atempo_chain},apad,atrim=0:{video_duration}",
                    "-ar", "24000", "-ac", "1",
                    fitted_audio
                ], capture_output=True, check=True)

            # 6. Final Mux (Never cuts video short, mutes original audio 100%)
            st.write("🎬 Locking synced voiceover track to video via FFmpeg...")
            if auto_adjust_video_speed:
                final_audio_dur = get_file_duration(fitted_audio)
                pts_ratio = final_audio_dur / video_duration
                subprocess.run([
                    "ffmpeg", "-y",
                    "-i", temp_video,
                    "-i", fitted_audio,
                    "-filter:v", f"setpts={pts_ratio:.4f}*PTS",
                    "-c:v", "libx264", "-preset", "fast",
                    "-c:a", "aac", "-b:a", "192k",
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-t", str(final_audio_dur),
                    output_video
                ], check=True)
            else:
                subprocess.run([
                    "ffmpeg", "-y",
                    "-i", temp_video,
                    "-i", fitted_audio,
                    "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k",
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-t", str(video_duration),
                    output_video
                ], check=True)

            status.update(label="✨ Video & Voiceover Perfectly Synced!", state="complete", expanded=False)

        st.subheader("🔥 Final Frame-Synced Video Output")
        st.video(output_video)
        with open(output_video, "rb") as vf:
            st.download_button(
                label="📥 Download Synced Video (MP4)",
                data=vf,
                file_name="synced_viral_short.mp4",
                mime="video/mp4",
                use_container_width=True
            )
            
               
