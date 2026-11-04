"""Synthesize narration sections with Gemini TTS. Key comes from the GEMINI_API_KEY env var.

usage: python bench/tts_narration.py narration.json out_dir [model] [voice]
"""
import base64, json, os, sys, time, urllib.error, urllib.request, wave
from pathlib import Path

key = os.environ["GEMINI_API_KEY"]
src, out = Path(sys.argv[1]), Path(sys.argv[2])
model = sys.argv[3] if len(sys.argv) > 3 else "gemini-2.5-flash-preview-tts"
voice = sys.argv[4] if len(sys.argv) > 4 else "Charon"
out.mkdir(parents=True, exist_ok=True)
STYLE = "Say in a calm, confident narrator voice: "

for name, text in json.loads(src.read_text(encoding="utf-8")).items():
    body = {"contents": [{"parts": [{"text": STYLE + text}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": key})
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.loads(r.read())
            pcm = base64.b64decode(data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
            break
        except (urllib.error.HTTPError, KeyError, urllib.error.URLError) as e:
            msg = e.read().decode(errors="replace")[:300] if isinstance(e, urllib.error.HTTPError) else repr(e)
            print(name, "attempt", attempt, "failed:", msg)
            time.sleep(25)
    else:
        sys.exit(f"{name}: TTS failed")
    with wave.open(str(out / f"{name}.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
    print(name, round(len(pcm) / 48000, 2), "s", flush=True)
    time.sleep(float(os.environ.get("TTS_GAP", "0")))
