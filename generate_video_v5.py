#!/usr/bin/env python3
"""
Buckit – Brain's External RAM  ·  Promo Video Generator v5
───────────────────────────────────────────────────────────
Tech-Noir / Cyberpunk terminal aesthetic:
  • 2-scene structure: Problem (2 lines) → Solution (2 lines)
  • Terminal glitch transition (RGB split + scanline jitter)
  • CRT scanlines + vignette
  • Brand colors: Navy bg, white text, yellow "Buck it" highlight
  • Real tactile keyboard sounds + enter sound
  • Human-like pacing: fast bursts + thinking pauses
  • Block cursor blinking at 2Hz
  • Outputs: 9:16 (stories) + 4:5 (feed)
"""

import os, gc, math, wave, random
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import VideoClip, AudioFileClip

# ── Paths ──────────────────────────────────────────────────────
FONT_BOLD = "C:/Windows/Fonts/consolab.ttf"
FONT_REG  = "C:/Windows/Fonts/consola.ttf"
LOGO_PATH = "assets/BuckitLogoTransparent.png"
SOUND_DIR = "assets/sounds"
OUTPUT_DIR = "output"

FPS         = 30
PRE_PAUSE   = 0.45       # pause before first line of each scene
POST_HOLD   = 0.85       # hold after last line typed
GLITCH_DUR  = 0.30       # terminal glitch between scenes
LOGO_DUR    = 3.5
SR          = 44100

# ── Brand colours ──────────────────────────────────────────────
BG_COLOR        = (20, 17, 59)     # #14113B navy
TEXT_COLOR       = (225, 225, 235)  # off-white
HIGHLIGHT_COLOR  = (255, 204, 0)   # #FFCC00 Buckit yellow
PROMPT_COLOR     = (85, 80, 145)   # dim purple
CURSOR_COLOR     = (225, 225, 235)
LOGO_BG_COLOR    = (14, 11, 38)

PROMPT = "buckit~ > "

# ── 2-scene structure ─────────────────────────────────────────
SCENE_DEFS = [
    {   # Scene 1: THE PROBLEM
        "lines": [
            {"text": "Good idea...",              "highlights": []},
            {"text": "...wrong time? :/",         "highlights": []},
        ],
        "typing_cps": [10, 8.5],       # fast burst, then slightly slower
        "inter_line_pause": 0.55,       # thinking pause before line 2
    },
    {   # Scene 2: THE SOLUTION
        "lines": [
            {"text": "Buck it in now... >>",      "highlights": [(0, 7)]},
            {"text": "...Buck it out later! :)",   "highlights": [(3, 10)]},
        ],
        "typing_cps": [10.5, 9],
        "inter_line_pause": 0.50,
    },
]

OUTPUTS = {
    "story_9x16": (1080, 1920),
    "feed_4x5":   (1080, 1350),
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Sound — tactile samples + enter
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _load_mp3(path):
    clip = AudioFileClip(path)
    frames = list(clip.iter_frames(fps=SR, dtype="float32"))
    clip.close()
    arr = np.concatenate(frames)
    if arr.ndim == 2:
        arr = arr.mean(axis=1)
    return arr.astype(np.float32)


def _load_sounds():
    keys = []
    for i in range(1, 5):
        p = os.path.join(SOUND_DIR, f"tactile{i}.mp3")
        if os.path.exists(p):
            keys.append(_load_mp3(p))
    space = enter = None
    sp = os.path.join(SOUND_DIR, "tactile_space.mp3")
    if os.path.exists(sp):
        space = _load_mp3(sp)
    ep = os.path.join(SOUND_DIR, "tactile_enter.mp3")
    if os.path.exists(ep):
        enter = _load_mp3(ep)
    return keys, space, enter


print("  Loading sounds...")
_KEY_SOUNDS, _SPACE_SOUND, _ENTER_SOUND = _load_sounds()
print(f"    {len(_KEY_SOUNDS)} key + space + enter loaded")


def _pitch_shift(snd, factor):
    n = len(snd)
    new_n = max(1, int(n / factor))
    return snd[np.linspace(0, n - 1, new_n).astype(int)]


def build_audio(total_dur, ks_events):
    """ks_events: list of (time, char_or_'enter')"""
    n = int(total_dur * SR)
    audio = np.zeros(n, dtype=np.float32)
    for kt, ch in ks_events:
        if ch == "enter" and _ENTER_SOUND is not None:
            snd = _ENTER_SOUND.copy() * random.uniform(0.7, 0.9)
        elif ch == " " and _SPACE_SOUND is not None:
            snd = _SPACE_SOUND.copy() * random.uniform(0.75, 1.0)
        elif _KEY_SOUNDS:
            snd = random.choice(_KEY_SOUNDS).copy()
            snd = _pitch_shift(snd, random.uniform(0.92, 1.08))
            snd *= random.uniform(0.75, 1.0)
        else:
            continue
        p = int(kt * SR)
        e = min(p + len(snd), n)
        if p < n:
            audio[p:e] += snd[:e - p]
    pk = np.max(np.abs(audio))
    if pk > 0:
        audio = audio / pk * 0.82
    return np.clip(audio, -1, 1)


def save_wav(data, path):
    pcm = (data * 32767).astype(np.int16)
    with wave.open(path, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Typing rhythm — fast bursts with variation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _char_times(line, cps):
    """Natural typing: fast in word middles, pauses at boundaries."""
    times = [0.0]
    base = 1.0 / cps
    for i in range(len(line) - 1):
        ch = line[i]
        d = base
        # First 2 chars type slightly slower (starting up)
        if i < 2:
            d *= random.uniform(1.3, 1.6)
        elif ch == "." and i + 1 < len(line) and line[i + 1] == ".":
            d *= random.uniform(0.40, 0.60)    # ellipsis dots fast
        elif ch == " ":
            d *= random.uniform(1.15, 1.5)     # word boundary
        elif ch in ".!?:":
            d *= random.uniform(1.2, 1.7)      # punctuation
        elif ch in ">/<":
            d *= random.uniform(0.5, 0.75)     # special chars fast
        else:
            d *= random.uniform(0.70, 1.15)    # normal variation
        times.append(times[-1] + d)
    return times


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Timeline planner
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def plan():
    phases = []
    ks_events = []
    t = 0.0

    for si, sdef in enumerate(SCENE_DEFS):
        scene_start = t
        lines_info = []

        for li, ldef in enumerate(sdef["lines"]):
            text = ldef["text"]
            cps = sdef["typing_cps"][li]

            if li == 0:
                type_start = t + PRE_PAUSE
            else:
                # thinking pause, then enter
                t += sdef["inter_line_pause"]
                ks_events.append((t, "enter"))
                type_start = t + 0.08  # tiny gap after enter

            ct = _char_times(text, cps)
            type_end = type_start + ct[-1] + 1.0 / cps

            for ci, c_t in enumerate(ct):
                ks_events.append((type_start + c_t, text[ci]))

            lines_info.append({
                "text": text,
                "highlights": ldef.get("highlights", []),
                "type_start": type_start,
                "type_end": type_end,
                "ct": ct,
            })
            t = type_end

        scene_end = t + POST_HOLD
        phases.append({"type": "scene", "idx": si, "start": scene_start,
                        "end": scene_end, "lines": lines_info})
        t = scene_end

        # glitch between scenes
        if si < len(SCENE_DEFS) - 1:
            phases.append({"type": "glitch", "start": t, "end": t + GLITCH_DUR,
                           "from_idx": si, "to_idx": si + 1})
            t += GLITCH_DUR

    # logo
    logo_start = t + 0.05
    phases.append({"type": "logo", "start": logo_start, "end": logo_start + LOGO_DUR})
    total = logo_start + LOGO_DUR

    return phases, ks_events, total


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Rendering helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_font_cache = {}

def _font(sz, bold=True):
    key = (sz, bold)
    if key not in _font_cache:
        try:
            _font_cache[key] = ImageFont.truetype(FONT_BOLD if bold else FONT_REG, sz)
        except Exception:
            _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]


def _flat_bg_vignette(W, H, color):
    """Flat bg with subtle CRT vignette (row-by-row, memory-safe)."""
    cx, cy = np.float32(W / 2), np.float32(H / 2)
    mr = np.float32(math.hypot(cx, cy))
    x2 = (np.arange(W, dtype=np.float32) - cx) ** 2
    bg = np.empty((H, W, 3), dtype=np.uint8)
    for y in range(H):
        d = np.sqrt(x2 + np.float32((y - cy) ** 2)) / mr
        factor = np.clip(1.0 - d * 0.28, 0.6, 1.0)
        for ch in range(3):
            bg[y, :, ch] = (np.float32(color[ch]) * factor).astype(np.uint8)
    return bg


def _fit_font(W, text, ratio=0.94):
    lo, hi, best = 20, 250, 40
    while lo <= hi:
        mid = (lo + hi) // 2
        bb = _font(mid).getbbox(text)
        tw = bb[2] - bb[0] if bb else mid * len(text)
        if tw <= int(W * ratio):
            best = mid; lo = mid + 1
        else:
            hi = mid - 1
    return best


def _ease_out_back(t):
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * ((t - 1) ** 3) + c1 * ((t - 1) ** 2)


def _ease_out_cubic(t):
    return 1 - (1 - t) ** 3


def _colored_segments(visible, highlights):
    """Split visible text into (text, color) segments."""
    if not highlights or not visible:
        return [(visible, TEXT_COLOR)]
    colors = [TEXT_COLOR] * len(visible)
    for s, e in highlights:
        for i in range(max(0, s), min(e, len(visible))):
            colors[i] = HIGHLIGHT_COLOR
    segs, i = [], 0
    while i < len(visible):
        c = colors[i]
        j = i + 1
        while j < len(visible) and colors[j] == c:
            j += 1
        segs.append((visible[i:j], c))
        i = j
    return segs


def _apply_crt_scanlines(frame):
    """CRT scanlines: darken every 3rd row."""
    frame[2::3] = (frame[2::3].astype(np.uint16) * 218 >> 8).astype(np.uint8)
    return frame


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Scene rendering
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def render_scene(W, H, bg, phase, t, fsz, x_start):
    """Render a scene at time t. Two lines, left-aligned, vertically centred."""
    # Determine what's visible
    vis_lines = []   # (text, n_typed, highlights)
    cursor_li = -1

    for li, ln in enumerate(phase["lines"]):
        if t >= ln["type_start"]:
            if t < ln["type_end"]:
                elapsed = t - ln["type_start"]
                n = sum(1 for c in ln["ct"] if c <= elapsed)
            else:
                n = len(ln["text"])
            vis_lines.append((ln["text"], n, ln["highlights"]))
            cursor_li = len(vis_lines) - 1
        elif t >= ln["type_start"] - 0.08 and li > 0:
            # Line just appeared (after enter) but typing hasn't started
            vis_lines.append((ln["text"], 0, ln["highlights"]))
            cursor_li = len(vis_lines) - 1

    if not vis_lines:
        # Pre-pause: show empty prompt with blinking cursor
        vis_lines = [("", 0, [])]
        cursor_li = 0

    # Is cursor currently in a typing phase?
    is_typing = any(ln["type_start"] <= t < ln["type_end"] for ln in phase["lines"])
    cursor_on = True if is_typing else (int(t * 4) % 2 == 0)  # 2Hz blink

    # Render
    frame = bg.copy()
    img = Image.fromarray(frame)
    draw = ImageDraw.Draw(img)
    mf = _font(fsz)

    # Vertical layout
    test_bb = mf.getbbox("Mg|")
    line_h = test_bb[3] - test_bb[1]
    line_spacing = int(line_h * 1.7)
    max_lines = 2
    total_block_h = line_h + (max_lines - 1) * line_spacing
    y_start = (H - total_block_h) // 2

    for vi, (text, n_typed, highlights) in enumerate(vis_lines):
        y = y_start + vi * line_spacing
        x = x_start

        # Draw prompt
        draw.text((x, y), PROMPT, fill=PROMPT_COLOR, font=mf)
        pbb = mf.getbbox(PROMPT)
        px = x + (pbb[2] - pbb[0])

        # Draw typed text with colour segments
        visible = text[:n_typed]
        for seg_text, seg_color in _colored_segments(visible, highlights):
            draw.text((px, y), seg_text, fill=seg_color, font=mf)
            sbb = mf.getbbox(seg_text)
            px += sbb[2] - sbb[0]

        # Cursor
        if vi == cursor_li:
            c_ch = "\u2588" if cursor_on else " "
            draw.text((px, y), c_ch, fill=CURSOR_COLOR, font=mf)

    result = np.asarray(img).copy()
    del img, draw
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Glitch transition
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _glitch(frame, intensity):
    """RGB split + horizontal scanline jitter + brightness flicker."""
    h, w = frame.shape[:2]
    out = frame.copy()
    shift = max(1, int(intensity * 18))

    # RGB chromatic aberration
    if shift < w:
        out[:, :-shift, 0] = frame[:, shift:, 0]     # red ← left
        out[:, shift:, 2]  = frame[:, :-shift, 2]     # blue → right

    # Scanline displacement
    n_lines = max(1, int(intensity * 12))
    for _ in range(n_lines):
        y = random.randint(0, h - 1)
        band = random.randint(1, max(1, int(intensity * 8)))
        off = random.randint(-int(intensity * 30), int(intensity * 30))
        y2 = min(y + band, h)
        if 0 < abs(off) < w:
            row_block = out[y:y2].copy()
            if off > 0:
                out[y:y2, off:] = row_block[:, :-off]
                out[y:y2, :off] = 0
            else:
                out[y:y2, :off] = row_block[:, -off:]
                out[y:y2, off:] = 0

    # Brightness flicker
    flicker = np.float32(1.0 + (random.random() - 0.5) * intensity * 0.7)
    out = np.clip(out.astype(np.float32) * flicker, 0, 255).astype(np.uint8)

    return out


def render_glitch(frame_a, frame_b, progress, W, H):
    """Glitch transition: scene A → scene B over progress 0→1."""
    # Intensity peaks at midpoint
    intensity = math.sin(progress * math.pi)

    # Crossfade with glitch
    alpha = int(min(progress * 1.8, 1.0) * 255)  # fast crossfade in first half
    blended = ((frame_a.astype(np.uint16) * (255 - alpha)
              + frame_b.astype(np.uint16) * alpha) >> 8).astype(np.uint8)

    return _glitch(blended, intensity)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Logo end card
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def render_logo(W, H, t_in, logo_img, logo_bg):
    img = Image.fromarray(logo_bg.copy()).convert("RGBA")
    draw = ImageDraw.Draw(img)

    logo_dur = 0.6
    title_t, sub_t, badge_t = 0.4, 0.7, 1.0

    if logo_img is not None:
        lsz_base = min(W, H) // 3
        if t_in < logo_dur:
            p = t_in / logo_dur
            scale = _ease_out_back(p)
            op = _ease_out_cubic(min(p * 2, 1.0))
        else:
            scale, op = 1.0, 1.0
        lsz = max(1, int(lsz_base * scale))
        lr = logo_img.resize((lsz, lsz), Image.LANCZOS).convert("RGBA")
        a = lr.split()[3].point(lambda p: int(p * op))
        lr.putalpha(a)
        lx = (W - lsz) // 2
        ly_base = (H - lsz_base) // 2 - int(H * 0.10)
        ly = ly_base + (lsz_base - lsz) // 2
        img.paste(lr, (lx, ly), lr)
        del lr, a
    else:
        lsz_base, ly_base = 0, H // 2

    def _f(c, st):
        if t_in < st:
            return (0, 0, 0, 0)
        p = min((t_in - st) / 0.35, 1.0)
        a = _ease_out_cubic(p)
        return tuple(int(x * a) for x in c) + (255,)

    tf = _font(int(min(W, H) * 0.085))
    bb = tf.getbbox("Buckit")
    ty = ly_base + lsz_base + int(H * 0.025)
    draw.text(((W - (bb[2] - bb[0])) // 2, ty), "Buckit",
              fill=_f((255, 220, 55), title_t), font=tf)

    sf = _font(int(min(W, H) * 0.030), bold=False)
    bb2 = sf.getbbox("Brain's External RAM")
    sy = ty + int(H * 0.065)
    draw.text(((W - (bb2[2] - bb2[0])) // 2, sy), "Brain's External RAM",
              fill=_f((180, 170, 200), sub_t), font=sf)

    gf = _font(int(min(W, H) * 0.022), bold=False)
    bb3 = gf.getbbox("Available on Google Play")
    gy = sy + int(H * 0.055)
    draw.text(((W - (bb3[2] - bb3[0])) // 2, gy), "Available on Google Play",
              fill=_f((130, 125, 150), badge_t), font=gf)

    result = np.asarray(img.convert("RGB")).copy()
    del img, draw
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Video generation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate(name, W, H):
    print(f"\n  [{name}] {W}x{H} ...")
    phases, ks_events, total = plan()

    try:
        logo_img = Image.open(LOGO_PATH).convert("RGBA")
    except Exception:
        logo_img = None

    # Font size: fit longest possible display line
    all_texts = [PROMPT + l["text"] + "\u2588"
                 for sd in SCENE_DEFS for l in sd["lines"]]
    longest = max(all_texts, key=len)
    fsz = _fit_font(W, longest, 0.94)

    # Compute x_start: left-align all lines, centre the block
    mf = _font(fsz)
    longest_bb = mf.getbbox(longest)
    longest_w = longest_bb[2] - longest_bb[0]
    x_start = (W - longest_w) // 2

    print(f"    font: {fsz}px  duration: {total:.1f}s  frames: {int(total * FPS)}")

    # Backgrounds
    print("    building backgrounds...")
    scene_bg = _flat_bg_vignette(W, H, BG_COLOR)
    logo_bg = _flat_bg_vignette(W, H, LOGO_BG_COLOR)
    gc.collect()

    # Pre-build scene phase lookup
    scene_phases = [p for p in phases if p["type"] == "scene"]

    # Cache last/first frames for glitch (computed lazily)
    _glitch_cache = {}

    frame_n = [0]

    def _get_scene_frame(si, t):
        return render_scene(W, H, scene_bg, scene_phases[si], t, fsz, x_start)

    def make_frame(t):
        frame_n[0] += 1
        if frame_n[0] % 120 == 0:
            gc.collect()

        for phase in phases:
            if phase["start"] <= t < phase["end"]:
                if phase["type"] == "scene":
                    frame = _get_scene_frame(phase["idx"], t)
                    return _apply_crt_scanlines(frame)

                elif phase["type"] == "glitch":
                    progress = (t - phase["start"]) / GLITCH_DUR
                    fi, ti = phase["from_idx"], phase["to_idx"]
                    # Get end frame of outgoing scene + start frame of incoming
                    fa = _get_scene_frame(fi, scene_phases[fi]["end"] - 0.001)
                    fb = _get_scene_frame(ti, scene_phases[ti]["start"])
                    frame = render_glitch(fa, fb, progress, W, H)
                    del fa, fb
                    return _apply_crt_scanlines(frame)

                elif phase["type"] == "logo":
                    t_in = t - phase["start"]
                    return render_logo(W, H, t_in, logo_img, logo_bg)

        return np.zeros((H, W, 3), dtype=np.uint8)

    video = VideoClip(make_frame, duration=total).with_fps(FPS)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    wav = os.path.join(OUTPUT_DIR, f"_tmp_{name}.wav")
    save_wav(build_audio(total, ks_events), wav)
    video = video.with_audio(AudioFileClip(wav))

    out = os.path.join(OUTPUT_DIR, f"buckit_promo_{name}.mp4")

    # Try GPU encoding, fall back to libx264
    codec = "libx264"
    try:
        import subprocess
        r = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True)
        if "h264_nvenc" in r.stdout:
            codec = "h264_nvenc"
            print(f"    using GPU encoder: {codec}")
    except Exception:
        pass

    video.write_videofile(out, fps=FPS, codec=codec, audio_codec="aac",
                          preset="medium", bitrate="5000k", logger="bar")
    try:
        os.remove(wav)
    except OSError:
        pass

    del video
    gc.collect()
    print(f"    -> {out}")
    return out


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("=" * 52)
    print("  Buckit - Brain's External RAM  |  Promo v5")
    print("=" * 52)
    results = []
    for name, (w, h) in OUTPUTS.items():
        results.append(generate(name, w, h))
        gc.collect()
    print("\n" + "=" * 52)
    print("  Done!")
    for r in results:
        print(f"    {r}")
    print("=" * 52)


if __name__ == "__main__":
    random.seed(42)
    np.random.seed(42)
    main()
