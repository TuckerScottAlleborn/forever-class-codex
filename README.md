# Forever Class Codex

A class-by-class guide to how *World of Warcraft: Forever* changes the nine Alliance classes compared with Vanilla, written for Classic veterans. Single static page: `index.html`.

Share pages for each class (`/<class>/`) carry their own Discord/Open Graph embed and forward to that section. Regenerate them, the preview images (`og.png`, `<class>/og.png`) and the icons with `python og/build.py` (needs Edge and Pillow).

## Audio version

The page has a narrated version of the codex: one MP3 at `audio/forever-class-codex.mp3`, with a
"Listen to the episode" button and a play button per class that plays just that chapter.

The narration is written for listening in `podcast/script.md`; each `## Title {#id}` heading is a
chapter whose id matches a section on the page. `python podcast/build.py` synthesizes it with
[Kokoro](https://github.com/thewh1teagle/kokoro-onnx) (voice `af_heart`, run on the CPU from
`%LOCALAPPDATA%\kokoro-tts`), encodes the MP3 with ID3 chapters, and writes the chapter timings
into `audio/chapters.json` and the `#podcast-data` block in `index.html`.
`python podcast/build.py --samples <voice> ...` renders short voice samples to `podcast/samples/`.
