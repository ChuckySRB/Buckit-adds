#!/usr/bin/env python3
"""
Buckit – Brain's External RAM  ·  Promo Video Generator v4
───────────────────────────────────────────────────────────
v4: Real tactile keyboard sounds, clean text (no outline),
    flat dark backgrounds, bigger text, dynamic zoom tracking
    typed word, smooth slide transitions, faster pacing.
"""

import os, gc, math, wave, random, struct
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import VideoClip, AudioFileClip

# ── Paths ──────────────────────────────────────────────────────
FONT_BOLD = "C:/Windows/Fonts/consolab.ttf"
FONT_REG  = "C:/Windows/Fonts/consola.ttf"
LOGO_PATH = "assets/BuckitLogoTransparent.png"
SOUND_DIR = "assets/sounds"
OUTPUT_DIR = "output"

FPS          = 30
BASE_CPS     = 7.5        # slightly faster
PRE_PAUSE    = 0.40       # shorter wait before typing
POST_HOLD    = 0.70       # shorter hold after done
XFADE        = 0.20       # slide transition duration
CURSOR_BLINK = 0.40
LOGO_DUR     = 3.5
SR           = 44100

PROMPT = "buckit~ > "

LINES = [
    "Good idea...",
    "...wrong time?",
    "Buck it in now...",
    "...Buck it out later!",
]

# ── Scene themes: flat backgrounds, escalating energy ──────────
THEMES = [
    {   # 1 — dark teal, muted
        "bg": (8, 22, 18),
        "prompt": (0, 100, 55), "text": (0, 200, 110),
        "cursor": (0, 200, 110),
        "zoom_range": (1.0, 1.03),
    },
    {   # 2 — dark warm, muted
        "bg": (28, 14, 8),
        "prompt": (150, 95, 28), "text": (220, 165, 45),
        "cursor": (220, 165, 45),
        "zoom_range": (1.0, 1.035),
    },
    {   # 3 — deep navy, vivid (Buckit blue)
        "bg": (10, 16, 42),
        "prompt": (55, 120, 210), "text": (95, 195, 255),
        "cursor": (95, 195, 255),
        "zoom_range": (1.0, 1.045),
    },
    {   # 4 — deep purple, bold gold
        "bg": (25, 14, 42),
        "prompt": (190, 150, 35), "text": (255, 220, 60),
        "cursor": (255, 220, 60),
        "zoom_range": (1.0, 1.055),
    },
]

OUTPUTS = {
    "story_9x16":   (1080, 1920),
    "standard_4x3": (1440, 1080),
    "portrait_3x4": (1080, 1440),
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Sound — real tactile samples
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _load_mp3_as_array(path):
    """Load mp3 via moviepy, return mono float32 array at SR."""
    clip = AudioFileClip(path)
    # get raw audio frames
    frames = []
    for chunk in clip.iter_frames(fps=SR, dtype="float32"):
        frames.append(chunk)
    clip.close()
    arr = np.concatenate(frames)
    if arr.ndim == 2:
        arr = arr.mean(axis=1)  # stereo → mono
    return arr.astype(np.float32)


def _load_sounds():
    """Load all tactile sound variants."""
    keys = []
    for i in range(1, 5):
        p = os.path.join(SOUND_DIR, f"tactile{i}.mp3")
        if os.path.exists(p):
            keys.append(_load_mp3_as_array(p))
    space = None
    sp = os.path.join(SOUND_DIR, "tactile_space.mp3")
    if os.path.exists(sp):
        space = _load_mp3_as_array(sp)
    return keys, space


print("  Loading tactile sounds...")
_KEY_SOUNDS, _SPACE_SOUND = _load_sounds()
print(f"    {len(_KEY_SOUNDS)} key variants loaded")


def build_audio(total_dur, keystroke_events):
    """keystroke_events: list of (time, char)"""
    n = int(total_dur * SR)
    audio = np.zeros(n, dtype=np.float32)
    for kt, ch in keystroke_events:
        if ch == " " and _SPACE_SOUND is not None:
            snd = _SPACE_SOUND.copy()
        elif _KEY_SOUNDS:
            snd = random.choice(_KEY_SOUNDS).copy()
        else:
            continue
        # slight pitch variation via resampling
        factor = random.uniform(0.92, 1.08)
        if abs(factor - 1.0) > 0.02:
            new_n = max(1, int(len(snd) / factor))
            idx = np.linspace(0, len(snd) - 1, new_n).astype(int)
            snd = snd[idx]
        vol = random.uniform(0.75, 1.0)
        snd *= vol
        p = int(kt * SR)
        e = min(p + len(snd), n)
        if p < n:
            audio[p:e] += snd[:e - p]
    # normalize peak to 0.85
    pk = np.max(np.abs(audio))
    if pk > 0:
        audio = audio / pk * 0.85
    return np.clip(audio, -1, 1)


def save_wav(data, path):
    pcm = (data * 32767).astype(np.int16)
    with wave.open(path, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Typing rhythm
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _char_times(line):
    times = [0.0]
    base = 1.0 / BASE_CPS
    for i in range(len(line) - 1):
        ch = line[i]
        d = base
        if ch == "." and i + 1 < len(line) and line[i + 1] == ".":
            d *= random.uniform(0.40, 0.65)
        elif ch == " ":
            d *= random.uniform(1.2, 1.6)
        elif ch in ".!?":
            d *= random.uniform(1.3, 1.8)
        else:
            d *= random.uniform(0.7, 1.2)
        times.append(times[-1] + d)
    return times


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Timeline
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def plan():
    scenes, ks_events = [], []
    t = 0.0
    for i, line in enumerate(LINES):
        ct = _char_times(line)
        td = ct[-1] + 1.0 / BASE_CPS
        s_start = t
        ts = t + PRE_PAUSE
        te = ts + td
        s_end = te + POST_HOLD
        for ci, c in enumerate(ct):
            ks_events.append((ts + c, line[ci]))
        scenes.append(dict(idx=i, line=line, theme=THEMES[i],
                           ct=ct, start=s_start, ts=ts, te=te, end=s_end))
        t = s_end
    logo_start = t + 0.05
    total = logo_start + LOGO_DUR
    return scenes, ks_events, logo_start, total


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Rendering
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


def _flat_bg(W, H, color):
    """Simple flat colour background — no gradient artifacts."""
    bg = np.empty((H, W, 3), dtype=np.uint8)
    bg[:, :, 0] = color[0]
    bg[:, :, 1] = color[1]
    bg[:, :, 2] = color[2]
    return bg


def _fit_font(W, text, ratio=0.94):
    """Find biggest font size that fits text in ratio*W."""
    tw_target = int(W * ratio)
    lo, hi, best = 20, 250, 40
    while lo <= hi:
        mid = (lo + hi) // 2
        bb = _font(mid).getbbox(text)
        tw = bb[2] - bb[0] if bb else mid * len(text)
        if tw <= tw_target:
            best = mid; lo = mid + 1
        else:
            hi = mid - 1
    return best


def _ease_out_cubic(t):
    return 1 - (1 - t) ** 3


def _ease_out_back(t):
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * ((t - 1) ** 3) + c1 * ((t - 1) ** 2)


def _ease_in_out_cubic(t):
    if t < 0.5:
        return 4 * t * t * t
    else:
        return 1 - ((-2 * t + 2) ** 3) / 2


def _apply_zoom(frame_arr, W, H, zoom, cx_offset=0, cy_offset=0):
    """Zoom into frame with optional centre offset for tracking."""
    if zoom <= 1.001 and abs(cx_offset) < 1 and abs(cy_offset) < 1:
        return frame_arr
    img = Image.fromarray(frame_arr)
    zw, zh = int(W * zoom), int(H * zoom)
    img = img.resize((zw, zh), Image.BILINEAR)
    # offset the crop centre
    cx = zw // 2 + int(cx_offset * zoom)
    cy = zh // 2 + int(cy_offset * zoom)
    # clamp
    left = max(0, min(cx - W // 2, zw - W))
    top  = max(0, min(cy - H // 2, zh - H))
    img = img.crop((left, top, left + W, top + H))
    result = np.asarray(img).copy()
    del img
    return result


def render_typing(W, H, bg, theme, typed, cursor_on, fsz):
    """Clean render: flat bg + prompt + typed text. No outline, no glow."""
    frame = bg.copy()
    img = Image.fromarray(frame)
    draw = ImageDraw.Draw(img)
    mf = _font(fsz)
    cursor_ch = "\u2588" if cursor_on else " "
    full = PROMPT + typed + cursor_ch

    bb = mf.getbbox(full)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    tx, ty = (W - tw) // 2, (H - th) // 2

    # prompt in dim colour
    draw.text((tx, ty), PROMPT, fill=theme["prompt"], font=mf)
    # typed text + cursor in bright colour
    pbb = mf.getbbox(PROMPT)
    pw = pbb[2] - pbb[0] if pbb else 0
    draw.text((tx + pw, ty), typed + cursor_ch, fill=theme["text"], font=mf)

    result = np.asarray(img).copy()
    del img, draw
    return result


def _get_typed_text_x_range(W, typed, fsz):
    """Get horizontal pixel range of just the typed text (excluding prompt)."""
    mf = _font(fsz)
    full_with_cursor = PROMPT + typed + "\u2588"
    full_bb = mf.getbbox(full_with_cursor)
    full_w = full_bb[2] - full_bb[0] if full_bb else 0
    prompt_bb = mf.getbbox(PROMPT)
    prompt_w = prompt_bb[2] - prompt_bb[0] if prompt_bb else 0
    typed_bb = mf.getbbox(typed + "\u2588") if typed else None
    typed_w = typed_bb[2] - typed_bb[0] if typed_bb else 0

    # text is centred: tx = (W - full_w) // 2
    tx = (W - full_w) // 2
    # typed text starts at tx + prompt_w
    typed_start_x = tx + prompt_w
    typed_end_x = typed_start_x + typed_w
    typed_cx = (typed_start_x + typed_end_x) // 2
    return typed_cx


def render_logo(W, H, t_in, logo_img, logo_bg):
    """Bounce-in logo, staggered text."""
    img = Image.fromarray(logo_bg.copy()).convert("RGBA")
    draw = ImageDraw.Draw(img)

    logo_anim_dur = 0.6
    title_start = 0.4
    sub_start = 0.7
    badge_start = 1.0

    if logo_img is not None:
        lsz_base = min(W, H) // 3
        if t_in < logo_anim_dur:
            p = t_in / logo_anim_dur
            scale = _ease_out_back(p)
            opacity = _ease_out_cubic(min(p * 2, 1.0))
        else:
            scale, opacity = 1.0, 1.0
        lsz = max(1, int(lsz_base * scale))
        lr = logo_img.resize((lsz, lsz), Image.LANCZOS).convert("RGBA")
        a = lr.split()[3].point(lambda p: int(p * opacity))
        lr.putalpha(a)
        lx = (W - lsz) // 2
        ly_base = (H - lsz_base) // 2 - int(H * 0.10)
        ly = ly_base + (lsz_base - lsz) // 2
        img.paste(lr, (lx, ly), lr)
        del lr, a
    else:
        lsz_base, ly_base = 0, H // 2

    def _fade(c, start_t):
        if t_in < start_t:
            return (0, 0, 0, 0)
        p = min((t_in - start_t) / 0.35, 1.0)
        a = _ease_out_cubic(p)
        return tuple(int(x * a) for x in c) + (255,)

    tf = _font(int(min(W, H) * 0.085))
    title = "Buckit"
    bb = tf.getbbox(title)
    t_y = ly_base + lsz_base + int(H * 0.025)
    draw.text(((W - (bb[2] - bb[0])) // 2, t_y), title,
              fill=_fade((255, 220, 55), title_start), font=tf)

    sf = _font(int(min(W, H) * 0.030), bold=False)
    sub = "Brain's External RAM"
    bb2 = sf.getbbox(sub)
    sy = t_y + int(H * 0.065)
    draw.text(((W - (bb2[2] - bb2[0])) // 2, sy), sub,
              fill=_fade((180, 170, 200), sub_start), font=sf)

    gf = _font(int(min(W, H) * 0.022), bold=False)
    g = "Available on Google Play"
    bb3 = gf.getbbox(g)
    gy = sy + int(H * 0.055)
    draw.text(((W - (bb3[2] - bb3[0])) // 2, gy), g,
              fill=_fade((130, 125, 150), badge_start), font=gf)

    result = np.asarray(img.convert("RGB")).copy()
    del img, draw
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Slide transition helper
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _slide_transition(fa, fb, progress, W, H, direction="left"):
    """Smooth slide: outgoing slides out, incoming slides in.
    progress: 0→1. Uses ease_in_out for smooth acceleration."""
    p = _ease_in_out_cubic(progress)
    offset = int(W * p)
    out = np.zeros((H, W, 3), dtype=np.uint8)
    if direction == "left":
        # fa slides left, fb slides in from right
        if W - offset > 0:
            out[:, :W - offset] = fa[:, offset:]
        if offset > 0:
            out[:, W - offset:] = fb[:, :offset]
    else:
        # fa slides right, fb slides in from left
        if W - offset > 0:
            out[:, offset:] = fa[:, :W - offset]
        if offset > 0:
            out[:, :offset] = fb[:, W - offset:]
    return out


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Video generation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# alternate slide directions for variety
SLIDE_DIRS = ["left", "left", "left"]  # between scenes 1→2, 2→3, 3→4


def generate(name, W, H):
    print(f"\n  [{name}] {W}x{H} ...")
    scenes, ks_events, logo_start, total = plan()

    try:
        logo_img = Image.open(LOGO_PATH).convert("RGBA")
    except Exception:
        logo_img = None

    longest = PROMPT + max(LINES, key=len) + "\u2588"
    fsz = _fit_font(W, longest, 0.94)
    print(f"    font: {fsz}px  duration: {total:.1f}s  frames: {int(total * FPS)}")

    # flat backgrounds
    bgs = [_flat_bg(W, H, th["bg"]) for th in THEMES]
    logo_bg_color = (14, 10, 30)
    logo_bg = _flat_bg(W, H, logo_bg_color)

    frame_n = [0]

    def _scene_frame(si, t, apply_zoom_effect=True):
        sc = scenes[si]
        th = sc["theme"]
        line, ct = sc["line"], sc["ct"]

        if t < sc["ts"]:
            typed = ""
        elif t >= sc["te"]:
            typed = line
        else:
            elapsed = t - sc["ts"]
            n = sum(1 for c in ct if c <= elapsed)
            typed = line[:n]

        cur = True if t < sc["te"] else (int(t / CURSOR_BLINK) % 2 == 0)

        frame = render_typing(W, H, bgs[si], th, typed, cur, fsz)

        if apply_zoom_effect and typed:
            # Ken Burns base zoom
            scene_dur = sc["end"] - sc["start"]
            progress = (t - sc["start"]) / scene_dur if scene_dur > 0 else 0
            z_lo, z_hi = th["zoom_range"]
            zoom = z_lo + (z_hi - z_lo) * progress

            # dynamic tracking: offset towards the cursor/latest typed char
            typed_cx = _get_typed_text_x_range(W, typed, fsz)
            screen_cx = W // 2
            # smooth offset towards where typing is happening
            cx_off = (typed_cx - screen_cx) * 0.15  # subtle tracking

            frame = _apply_zoom(frame, W, H, zoom, cx_off, 0)

        return frame

    def make_frame(t):
        frame_n[0] += 1
        if frame_n[0] % 100 == 0:
            gc.collect()

        # slide transition zones between scenes
        for i in range(len(scenes) - 1):
            fs = scenes[i]["end"] - XFADE
            fe = scenes[i]["end"]
            if fs <= t < fe:
                progress = (t - fs) / XFADE
                fa = _scene_frame(i, fe - 0.001, apply_zoom_effect=False)
                fb = _scene_frame(i + 1, scenes[i + 1]["start"], apply_zoom_effect=False)
                direction = SLIDE_DIRS[i] if i < len(SLIDE_DIRS) else "left"
                return _slide_transition(fa, fb, progress, W, H, direction)

        # normal scene
        for i, sc in enumerate(scenes):
            s = sc["start"]
            e = sc["end"] - (XFADE if i < len(scenes) - 1 else 0)
            if s <= t < e:
                return _scene_frame(i, t)
            if i == len(scenes) - 1 and e <= t < sc["end"]:
                return _scene_frame(i, t)

        # logo end card
        if t >= logo_start:
            t_in = t - logo_start
            return render_logo(W, H, t_in, logo_img, logo_bg)

        return np.zeros((H, W, 3), dtype=np.uint8)

    video = VideoClip(make_frame, duration=total).with_fps(FPS)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    wav = os.path.join(OUTPUT_DIR, f"_tmp_{name}.wav")
    save_wav(build_audio(total, ks_events), wav)
    video = video.with_audio(AudioFileClip(wav))

    out = os.path.join(OUTPUT_DIR, f"buckit_promo_{name}.mp4")
    video.write_videofile(out, fps=FPS, codec="libx264", audio_codec="aac",
                          preset="medium", bitrate="5000k", logger="bar")
    try:
        os.remove(wav)
    except OSError:
        pass

    del bgs, logo_bg, video
    gc.collect()
    print(f"    -> {out}")
    return out


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("=" * 50)
    print("  Buckit - Brain's External RAM  |  Promo v4")
    print("=" * 50)
    results = []
    for name, (w, h) in OUTPUTS.items():
        results.append(generate(name, w, h))
        gc.collect()
    print("\n" + "=" * 50)
    print("  Done!")
    for r in results:
        print(f"    {r}")
    print("=" * 50)


if __name__ == "__main__":
    random.seed(42)
    np.random.seed(42)
    main()
