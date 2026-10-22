"""Turns script.md into a chaptered podcast MP3.

  python podcast/build.py                      full episode -> audio/forever-class-codex.mp3
                                               + audio/chapters.json, and the chapter list in index.html
  python podcast/build.py --voice bm_george    pick the Kokoro voice
  python podcast/build.py --samples af_heart am_michael ...
                                               one short clip per voice -> podcast/samples/

Speech engine:
  Kokoro (default): open-weight 82M TTS, run on the CPU with kokoro-onnx. Lives in
    %LOCALAPPDATA%\\kokoro-tts (venv\\ + models\\kokoro-v1.0.onnx, models\\voices-v1.0.bin).
  Piper (--engine piper): the /yt skill's install in %LOCALAPPDATA%\\yt-skill.

Each "## Title {#id}" heading in script.md is a chapter; the id matches the section id on
the page so its play button can seek there. The MP3 is mono speech at 64 kbps (small enough
to stream on a phone), loudness-normalized, with ID3 chapters and ../og.png as cover art.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "script.md"
ROOT = HERE.parent
OUT = ROOT / "audio" / "forever-class-codex.mp3"
CHAPTERS_JSON = ROOT / "audio" / "chapters.json"
PAGE = ROOT / "index.html"
SAMPLES = HERE / "samples"
COVER = HERE.parent / "og.png"

LOCAL = Path(os.environ.get("LOCALAPPDATA", ""))
ENGINES = {
    "kokoro": dict(python=LOCAL / "kokoro-tts" / "venv" / "Scripts" / "python.exe",
                   model=LOCAL / "kokoro-tts" / "models" / "kokoro-v1.0.onnx",
                   voices=LOCAL / "kokoro-tts" / "models" / "voices-v1.0.bin",
                   default_voice="af_heart"),
    "piper": dict(python=LOCAL / "yt-skill" / "piper-venv" / "Scripts" / "python.exe",
                  model=LOCAL / "yt-skill" / "voices" / "en_US-lessac-medium.onnx",
                  voices=None, default_voice="en_US-lessac-medium"),
}

SPEED = 0.97            # Kokoro speed (<1 slower); Piper uses length_scale = 1 / SPEED
SENTENCE_GAP = 0.30     # seconds (Piper only; Kokoro paces sentences itself)
PARAGRAPH_GAP = 0.80
CHAPTER_GAP = 1.1       # silence either side of the chapter chime
END_TAIL = 0.4          # a single chapter played on the page stops this long after its last word

SAMPLE_TEXT = (
    "Paladin. Distance from Vanilla: very high. This is one of the biggest overhauls in the game. "
    "Judgment no longer consumes your Seal, and Protection finally gets a real taunt: the Judgment "
    "from Seal of Fury. Late beta also raised Righteous Fury's Holy threat from sixty percent to ninety. "
    "If you liked the idea of Vanilla Paladin, but not what happened when you tried to tank at sixty, "
    "this is the clearest play-it-again pick in Forever."
)


def parse(path: Path):
    chapters, cur = [], None
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8")):
        block = block.strip()
        if not block:
            continue
        if block.startswith("## "):
            title, _, rest = block.partition("\n")
            m = re.match(r"(.*?)\s*\{#([\w-]+)\}\s*$", title[3:].strip())
            name, cid = (m.group(1), m.group(2)) if m else (title[3:].strip(), None)
            cur = {"title": name, "id": cid or re.sub(r"\W+", "-", name.lower()).strip("-"), "paras": []}
            chapters.append(cur)
            block = rest.strip()
            if not block:
                continue
        cur["paras"].append(" ".join(block.split()))
    return chapters


# --------------------------------------------------------------------------- worker
# Runs under the engine's own venv. Writes one 16-bit mono WAV per job and the
# chapter start times.

def worker(job_file: str) -> int:
    import math
    import wave

    job = json.loads(Path(job_file).read_text(encoding="utf-8"))
    engine, voice_name = job["engine"], job["voice"]

    if engine == "kokoro":
        import numpy as np
        from kokoro_onnx import Kokoro
        kokoro = Kokoro(job["model"], job["voices"])
        sr = 24000
        lang = "en-gb" if voice_name[:1] == "b" else "en-us"

        def speak(text):
            samples, rate = kokoro.create(text, voice=voice_name, speed=job["speed"], lang=lang)
            assert rate == sr
            pcm = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
            return [(pcm * 32767).astype("<i2").tobytes()]
    else:
        from piper import PiperVoice
        try:
            from piper import SynthesisConfig
            cfg = SynthesisConfig(length_scale=1 / job["speed"])
        except ImportError:
            cfg = None
        voice = PiperVoice.load(job["model"])
        sr = voice.config.sample_rate

        def speak(text):
            chunks = voice.synthesize(text, syn_config=cfg) if cfg else voice.synthesize(text)
            out = []
            for chunk in chunks:
                if out:
                    out.append(b"\0\0" * int(sr * SENTENCE_GAP))
                out.append(chunk.audio_int16_bytes)
            return out

    def silence(sec):
        return b"\0\0" * int(sr * sec)

    def chime():
        # two soft notes, a fifth apart, with short fades
        out = bytearray()
        for freq, dur in ((587.33, 0.22), (880.0, 0.42)):
            n = int(sr * dur)
            for i in range(n):
                env = min(1.0, i / (0.01 * sr), (n - i) / (0.12 * sr))
                v = 0.16 * env * (math.sin(2 * math.pi * freq * i / sr) + 0.3 * math.sin(4 * math.pi * freq * i / sr))
                out += int(max(-1, min(1, v)) * 32767).to_bytes(2, "little", signed=True)
        return bytes(out)

    for out in job["outputs"]:
        starts, ends, total, t0 = [], [], 0, time.time()
        with wave.open(out["wav"], "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sr)

            def put(b):
                nonlocal total
                wav.writeframes(b)
                total += len(b) // 2

            put(silence(0.5))
            for ci, ch in enumerate(out["chapters"]):
                if ci:
                    put(silence(CHAPTER_GAP)); put(chime()); put(silence(CHAPTER_GAP))
                starts.append(total / sr)
                for pi, para in enumerate(ch["paras"]):
                    if pi:
                        put(silence(PARAGRAPH_GAP))
                    for b in speak(para):
                        put(b)
                ends.append(total / sr + END_TAIL)  # narration only, before the next chapter's chime
                if len(out["chapters"]) > 1:
                    print(f"  {ch['title']}: {total / sr / 60:.1f} min of audio, "
                          f"{(time.time() - t0) / 60:.1f} min elapsed", flush=True)
            put(silence(1.2))
        Path(out["starts"]).write_text(json.dumps({"starts": starts, "ends": ends, "end": total / sr}),
                                       encoding="utf-8")
    return 0


# --------------------------------------------------------------------------- driver

def run_worker(engine, voice, outputs, td: Path):
    e = ENGINES[engine]
    missing = [p for p in (e["python"], e["model"], e["voices"]) if p and not Path(p).exists()]
    if missing:
        raise SystemExit(f"{engine} is not installed (missing {missing[0]})")
    job = {"engine": engine, "voice": voice, "speed": SPEED, "model": str(e["model"]),
           "voices": str(e["voices"]) if e["voices"] else None, "outputs": outputs}
    (td / "job.json").write_text(json.dumps(job), encoding="utf-8")
    subprocess.run([str(e["python"]), str(Path(__file__).resolve()), "--worker", str(td / "job.json")], check=True)


def encode(wav: Path, out: Path, meta_lines, cover=True):
    out.parent.mkdir(parents=True, exist_ok=True)
    meta = wav.with_suffix(".meta.txt")
    meta.write_text("\n".join([";FFMETADATA1"] + meta_lines) + "\n", encoding="utf-8")
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-i", str(meta)]
    if cover and COVER.exists():
        cmd += ["-i", str(COVER), "-map", "2:v", "-c:v", "copy", "-disposition:v", "attached_pic",
                "-metadata:s:v", "title=Album cover", "-metadata:s:v", "comment=Cover (front)"]
    cmd += ["-map", "0:a", "-map_metadata", "1", "-map_chapters", "1",
            "-af", "highpass=f=70,loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "24000", "-ac", "1",
            "-c:a", "libmp3lame", "-b:a", "64k", "-id3v2_version", "3", str(out)]
    subprocess.run(cmd, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=ENGINES, default="kokoro")
    ap.add_argument("--voice")
    ap.add_argument("--samples", nargs="+", metavar="VOICE")
    a = ap.parse_args()
    voice = a.voice or ENGINES[a.engine]["default_voice"]

    with tempfile.TemporaryDirectory(prefix="codex-podcast-") as td:
        td = Path(td)
        if a.samples:
            outs = [{"wav": str(td / f"{v}.wav"), "starts": str(td / f"{v}.json"),
                     "chapters": [{"title": "Sample", "paras": [SAMPLE_TEXT]}]} for v in a.samples]
            for v, o in zip(a.samples, outs):
                run_worker(a.engine, v, [o], td)
                dest = SAMPLES / f"{v}.mp3"
                encode(Path(o["wav"]), dest, [f"title=Voice sample: {v}", "artist=Forever Class Codex"], cover=False)
                print("wrote", dest.relative_to(HERE.parent))
            return 0

        chapters = parse(SCRIPT)
        words = sum(len(p.split()) for c in chapters for p in c["paras"])
        print(f"{len(chapters)} chapters, {words} words, {a.engine} voice {voice}")
        out = {"wav": str(td / "speech.wav"), "starts": str(td / "starts.json"), "chapters": chapters}
        t0 = time.time()
        run_worker(a.engine, voice, [out], td)
        timing = json.loads(Path(out["starts"]).read_text(encoding="utf-8"))

        meta = ["title=Forever Class Codex", "artist=Forever Class Codex", "album=Forever Class Codex",
                "genre=Podcast", "date=2026",
                "comment=How WoW: Forever changes the nine Alliance classes compared with Vanilla."]
        starts = timing["starts"] + [timing["end"]]
        for i, ch in enumerate(chapters):
            meta += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(starts[i] * 1000)}",
                     f"END={int(starts[i + 1] * 1000)}", f"title={ch['title']}"]
        encode(Path(out["wav"]), OUT, meta)

    # ID3 chapters above run start to start; the page's per-chapter buttons stop at the end of the narration
    chap = {"src": OUT.relative_to(ROOT).as_posix(), "duration": round(timing["end"], 2),
            "chapters": [{"id": c["id"], "title": c["title"], "start": round(starts[i], 2),
                          "end": round(timing["ends"][i], 2)} for i, c in enumerate(chapters)]}
    CHAPTERS_JSON.write_text(json.dumps(chap, indent=1) + "\n", encoding="utf-8")
    page = PAGE.read_text(encoding="utf-8")
    block = re.compile(r'(<script type="application/json" id="podcast-data">).*?(</script>)', re.S)
    if block.search(page):
        page = block.sub(lambda m: m.group(1) + json.dumps(chap) + m.group(2), page)
        PAGE.write_text(page, encoding="utf-8", newline="\n")
        print("updated chapter list in index.html")

    mins = timing["end"] / 60
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB, {int(mins)}:{int(mins % 1 * 60):02d}) "
          f"in {(time.time() - t0) / 60:.1f} min")
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        sys.exit(worker(sys.argv[2]))
    sys.exit(main())
