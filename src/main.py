"""TCA R04 public-safe Windows T0 harness. No confidential episode content.
Tone is TEST ONLY; Kokoro is required for real spoken narration.
"""
import argparse, hashlib, json, math, os, shutil, subprocess, sys, threading, wave
from pathlib import Path

SCENE_IDS = [f"C{i:02d}" for i in range(1, 20)]
TEST_LINE = ("This is a neutral technical demonstration of scene number {n}. "
             "The claimed statement is not evidence and this demonstration is not an approved documentary.")
def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1048576), b""):
            h.update(b)
    return h.hexdigest()
def fail(msg):
    raise RuntimeError(msg)
def root():
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
def ffmpeg_exe():
    from imageio_ffmpeg import get_ffmpeg_exe
    p = get_ffmpeg_exe()
    if not Path(p).is_file(): fail("FFMPEG_NOT_PACKAGED")
    return str(p)
def execute(cmd):
    p = subprocess.run([str(x) for x in cmd], capture_output=True, text=True, errors="replace")
    if p.returncode: fail("COMMAND_FAILED " + str(p.returncode) + " " + " ".join(map(str, cmd[:4])) + "\n" + p.stderr[-3000:])
    return p.stdout
def srt_time(t):
    n = round(t * 1000)
    return f"{n//3600000:02d}:{n//60000%60:02d}:{n//1000%60:02d},{n%1000:03d}"
def get_scenes(script):
    if script:
        d = json.loads(Path(script).read_text(encoding="utf-8"))
        d = d.get("scenes", d)
        if isinstance(d, list): d = {f"C{i:02}": item for i, item in enumerate(d, 1)}
    else:
        d = {sid: TEST_LINE.format(n=i) for i, sid in enumerate(SCENE_IDS, 1)}
    if set(d) != set(SCENE_IDS) or any(not isinstance(d[k], str) or not d[k].strip() for k in SCENE_IDS):
        fail("SCRIPT_REQUIRES_EXACTLY_19_NONEMPTY_SCENES")
    return d
def tone_wav(path, seconds=1.0):
    rate = 24000
    import struct
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        block = bytearray()
        for i in range(round(rate * seconds)):
            amplitude = int(2600 * math.sin(2 * math.pi * 250 * i / rate))
            block.extend(struct.pack("<h", amplitude))
        w.writeframes(block)
    return seconds
def render(out, script=None, mode="tone", voice="am_michael", model_dir=None):
    from PIL import Image, ImageDraw
    from imageio_ffmpeg import get_ffmpeg_exe
    if mode not in ("tone", "kokoro"): fail("UNKNOWN_AUDIO_MODE")
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    scenes = get_scenes(script)
    ff = ffmpeg_exe()
    mdir = Path(model_dir).resolve() if model_dir else root() / "model"
    model = mdir / "kokoro-v1.0.onnx"; voices = mdir / "voices-v1.0.bin"
    kokoro = None
    if mode == "kokoro":
        if not model.is_file() or not voices.is_file(): fail("KOKORO_MODEL_OR_VOICES_MISSING")
        from kokoro_onnx import Kokoro
        kokoro = Kokoro(str(model), str(voices))
        if voice not in kokoro.get_voices(): fail("VOICE_UNAVAILABLE_" + voice)
    timestamps = []; elapsed = 0.0
    count_rendered = count_cached = count_tts = 0
    for idx, sid in enumerate(SCENE_IDS, 1):
        folder = out / "SCENES"; folder.mkdir(exist_ok=True)
        png = folder / f"{sid}.png"; wav = folder / f"{sid}.wav"
        mp4 = folder / f"{sid}.mp4"; cp = folder / f"{sid}.json"
        img = Image.new("RGB", (1920, 1080), (14, 19 + idx % 4 * 8, 35))
        draw = ImageDraw.Draw(img)
        draw.rectangle((80, 94, 1840, 980), outline=(105, 123, 146), width=5)
        draw.text((128, 220), f"TECHNICAL TEST - {sid} / 19", fill=(242, 243, 245), stroke_width=0)
        draw.text((128, 360), "NOT A DOCUMENTARY / NOT VERIFIED EVIDENCE", fill=(208, 182, 123))
        draw.text((128, 500), f"AUDIO MODE: {mode.upper()}", fill=(179, 195, 212))
        img.save(png)
        audio_identity = hashlib.sha256((sid + scenes[sid] + mode + voice + (sha(model) if mode == "kokoro" else "")).encode()).hexdigest()
        meta = folder / f"{sid}.audio.json"
        cached_audio = False
        if meta.exists() and wav.exists():
            try:
                prev = json.loads(meta.read_text())
                cached_audio = prev["input"] == audio_identity and prev["wav"] == sha(wav)
            except (KeyError, ValueError, OSError): pass
        if not cached_audio:
            if mode == "tone":
                tone_wav(wav)
            else:
                import soundfile as sf
                samples, rate = kokoro.create(scenes[sid], voice=voice, speed=1.0, lang="en-us")
                if not len(samples): fail(f"EMPTY_KOKORO_AUDIO_{sid}")
                sf.write(str(wav), samples, rate)
            meta.write_text(json.dumps({"input": audio_identity, "wav": sha(wav)}))
            count_tts += 1
        with wave.open(str(wav), "rb") as w:
            duration = w.getnframes() / w.getframerate()
        if duration <= 0: fail(f"EMPTY_WAV_{sid}")
        timestamps.append((elapsed, elapsed + duration, scenes[sid] if mode == "kokoro" else f"TEST TONE - {sid}"))
        elapsed += duration
        digest = hashlib.sha256((sha(wav) + sha(png) + "v3").encode()).hexdigest()
        cached = False
        if mp4.exists() and cp.exists():
            try:
                info = json.loads(cp.read_text())
                cached = info["input"] == digest and info["mp4"] == sha(mp4)
            except (KeyError, ValueError, OSError): pass
        if cached: count_cached += 1
        else:
            tmp = folder / f"{sid}.temporary.mp4"
            execute([ff, "-hide_banner", "-loglevel", "error", "-y", "-loop", "1", "-framerate", "2",
                     "-i", png, "-i", wav, "-t", f"{duration:.6f}", "-r", "2",
                     "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p",
                     "-c:a", "aac", "-ar", "24000", "-b:a", "96k", "-movflags", "+faststart", tmp])
            os.replace(tmp, mp4)
            cp.write_text(json.dumps({"input": digest, "mp4": sha(mp4), "scene": sid}, indent=2))
            count_rendered += 1
    srt = out / "technical_subtitles.srt"
    srt.write_text("\n".join([f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{t}\n"
                              for i, (a,b,t) in enumerate(timestamps, 1)]), encoding="utf-8")
    join = out / "SCENES" / "concat.ffconcat"
    join.write_text("ffconcat version 1.0\n" + "".join(f"file '{sid}.mp4'\n" for sid in SCENE_IDS), encoding="utf-8")
    fused = out / "without_subtitles.mp4"
    execute([ff, "-hide_banner", "-loglevel", "error", "-y", "-safe", "0", "-i", join, "-c", "copy", fused])
    mp4 = out / "TCA_R04_TECHNICAL_TEST_NOT_FILM.mp4"
    execute([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", fused, "-i", srt,
             "-map", "0:v:0", "-map", "0:a:0", "-map", "1:0", "-c:v", "copy", "-c:a", "copy",
             "-c:s", "mov_text", "-movflags", "+faststart", mp4])
    execute([ff, "-hide_banner", "-loglevel", "error", "-xerror", "-i", mp4, "-f", "null", "-"])
    qa = {"status": "TECHNICAL_TEST_NOT_PRODUCTION", "scenes": 19, "source": "PUBLIC_NEUTRAL_FIXTURE" if not script else "LOCAL_USER_SCRIPT",
          "audio_mode": mode, "voice": voice if mode == "kokoro" else None,
          "wav_created_or_rebuilt": count_tts, "rendered": count_rendered, "resume_skipped": count_cached,
          "duration_seconds_audio": elapsed, "mp4": str(mp4), "mp4_sha256": sha(mp4),
          "decode": "PASS", "subtitle_timing": "PER_SCENE_ACTUAL_WAV_SAMPLE_COUNT",
          "windows_10_compatibility": "NOT_VERIFIED_BY_WINDOWS_SERVER_CI", "rights": "UNKNOWN"}
    (out / "QA.json").write_text(json.dumps(qa, indent=2), encoding="utf-8")
    return qa
def gui():
    import tkinter as tk
    from tkinter import filedialog
    app = tk.Tk(); app.title("TCA R04 - Technical Producer T0"); app.geometry("620x320")
    tk.Label(app, text="TCA R04 - ENGINE TEST", font=("Arial", 16, "bold")).pack(pady=12)
    selected = tk.StringVar(value="No custom script - neutral technical fixture")
    status = tk.StringVar(value="Kokoro model and voices must be present. No paid service.")
    voice = tk.StringVar(value="am_michael")
    def pick():
        p = filedialog.askopenfilename(title="Select 19-scene JSON", filetypes=[("JSON", "*.json")])
        if p: selected.set(p)
    tk.Button(app, text="LOAD SCRIPT (JSON)", command=pick).pack()
    tk.OptionMenu(app, voice, "am_michael", "am_adam").pack()
    tk.Label(app, textvariable=selected, wraplength=590).pack()
    tk.Label(app, textvariable=status, wraplength=590).pack(pady=8)
    button = tk.Button(app, text="START - CREATE NEW MP4", width=32, height=2)
    def start():
        button.config(state="disabled"); status.set("Rendering - see OUTPUT folder")
        def worker():
            try:
                script = selected.get() if Path(selected.get()).is_file() else None
                result = render(root() / "OUTPUT", script=script, mode="kokoro", voice=voice.get())
                msg = "DONE: " + result["mp4"]
            except Exception as exc:
                msg = "BLOCKED: " + str(exc)
            app.after(0, lambda: (status.set(msg), button.config(state="normal")))
        threading.Thread(target=worker, daemon=True).start()
    button.config(command=start); button.pack(pady=6)
    tk.Label(app, text="Technical preview only. Never includes private film scripts.", wraplength=590).pack()
    app.mainloop()
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ci-smoke", action="store_true")
    p.add_argument("--ci-kokoro", action="store_true")
    p.add_argument("--voice", default="am_michael", choices=["am_michael","am_adam"])
    p.add_argument("--script")
    p.add_argument("--out")
    p.add_argument("--model-dir")
    args = p.parse_args()
    if args.ci_smoke or args.ci_kokoro:
        q = render(args.out or (root() / "OUTPUT"), script=args.script,
                   mode="kokoro" if args.ci_kokoro else "tone", voice=args.voice, model_dir=args.model_dir)
        print(json.dumps(q, ensure_ascii=False))
    else: gui()
if __name__ == "__main__": main()
