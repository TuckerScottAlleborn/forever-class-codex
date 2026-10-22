"""Turns script.md into a chaptered podcast MP3 with Piper TTS.

  python podcast/build.py

Uses the Piper venv and voice that the /yt skill installs in %LOCALAPPDATA%\\yt-skill
(rebuild with `intro.py --setup` from that skill). Writes podcast/forever-class-codex.mp3:
mono speech, loudness-normalized, one ID3 chapter per "## " heading in script.md,
with ../og.png as cover art.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "script.md"
OUT = HERE / "forever-class-codex.mp3"
COVER = HERE.parent / "og.png"

TTS_HOME = Path(os.environ.get("LOCALAPPDATA", "")) / "yt-skill"
PIPER_PY = TTS_HOME / "piper-venv" / "Scripts" / "python.exe"
VOICE = TTS_HOME / "voices" / "en_US-lessac-medium.onnx"

LENGTH_SCALE = 1.04     # >1 is slower; a touch slower reads better for long listening
SENTENCE_GAP = 0.32     # seconds
PARAGRAPH_GAP = 0.85
CHAPTER_GAP = 1.1       # silence either side of the chapter chime


def parse(path: Path):
    chapters, cur = [], None
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8")):
        block = block.strip()
        if not block:
            continue
        if block.startswith("## "):
            title, _, rest = block.partition("\n")
            cur = {"title": title[3:].strip(), "paras": []}
            chapters.append(cur)
            block = rest.strip()
            if not block:
                continue
        cur["paras"].append(" ".join(block.split()))
    return chapters


def worker(job_file: str) -> int:
    """Runs under the Piper venv: synthesizes every chapter into one WAV and records chapter starts."""
    import math
    import wave
    from piper import PiperVoice
    try:
        from piper import SynthesisConfig
        cfg = SynthesisConfig(length_scale=LENGTH_SCALE)
    except ImportError:
        cfg = None

    job = json.loads(Path(job_file).read_text(encoding="utf-8"))
    voice = PiperVoice.load(job["model"])
    sr = voice.config.sample_rate

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

    starts, total = [], 0
    with wave.open(job["wav"], "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)

        def put(b):
            nonlocal total
            wav.writeframes(b)
            total += len(b) // 2

        put(silence(0.5))
        for ci, ch in enumerate(job["chapters"]):
            if ci:
                put(silence(CHAPTER_GAP)); put(chime()); put(silence(CHAPTER_GAP))
            starts.append(total / sr)
            for pi, para in enumerate(ch["paras"]):
                if pi:
                    put(silence(PARAGRAPH_GAP))
                first = True
                chunks = voice.synthesize(para, syn_config=cfg) if cfg else voice.synthesize(para)
                for chunk in chunks:  # one chunk per sentence
                    if not first:
                        put(silence(SENTENCE_GAP))
                    first = False
                    put(chunk.audio_int16_bytes)
            print(f"  {ch['title']}: done at {total / sr / 60:.1f} min", flush=True)
        put(silence(1.5))
    Path(job["starts"]).write_text(json.dumps({"starts": starts, "end": total / sr}), encoding="utf-8")
    return 0


def main() -> int:
    if not (PIPER_PY.exists() and VOICE.exists()):
        raise SystemExit(f"Piper not found in {TTS_HOME}; run the yt skill's `intro.py --setup` first")
    chapters = parse(SCRIPT)
    words = sum(len(p.split()) for c in chapters for p in c["paras"])
    print(f"{len(chapters)} chapters, {words} words")

    with tempfile.TemporaryDirectory(prefix="codex-podcast-") as td:
        td = Path(td)
        job = {"model": str(VOICE), "wav": str(td / "speech.wav"), "starts": str(td / "starts.json"),
               "chapters": chapters}
        (td / "job.json").write_text(json.dumps(job), encoding="utf-8")
        subprocess.run([str(PIPER_PY), str(Path(__file__).resolve()), "--worker", str(td / "job.json")], check=True)
        timing = json.loads((td / "starts.json").read_text(encoding="utf-8"))

        meta = [";FFMETADATA1", "title=Forever Class Codex", "artist=Forever Class Codex",
                "album=Forever Class Codex", "genre=Podcast", "date=2026",
                "comment=How WoW: Forever changes the nine Alliance classes compared with Vanilla."]
        starts = timing["starts"] + [timing["end"]]
        for i, ch in enumerate(chapters):
            meta += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(starts[i] * 1000)}",
                     f"END={int(starts[i + 1] * 1000)}", f"title={ch['title']}"]
        (td / "meta.txt").write_text("\n".join(meta) + "\n", encoding="utf-8")

        cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(td / "speech.wav"), "-i", str(td / "meta.txt")]
        if COVER.exists():
            cmd += ["-i", str(COVER), "-map", "2:v", "-c:v", "copy", "-disposition:v", "attached_pic",
                    "-metadata:s:v", "title=Album cover", "-metadata:s:v", "comment=Cover (front)"]
        cmd += ["-map", "0:a", "-map_metadata", "1", "-map_chapters", "1",
                "-af", "highpass=f=70,loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "44100", "-ac", "1",
                "-c:a", "libmp3lame", "-b:a", "96k", "-id3v2_version", "3", str(OUT)]
        subprocess.run(cmd, check=True)

    mins = timing["end"] / 60
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB, {int(mins)}:{int(mins % 1 * 60):02d})")
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        sys.exit(worker(sys.argv[2]))
    sys.exit(main())
