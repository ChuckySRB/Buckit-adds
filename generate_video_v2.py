#!/usr/bin/env python3
"""
Buckit – Brain's External RAM  ·  Promo Video Generator v2
───────────────────────────────────────────────────────────
Clean full-screen typing.  No terminal chrome.  Natural rhythm.
Satisfying thock sounds.  Smooth crossfades.  Logo end card.
"""

import os, gc, math, wave, random
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import VideoClip, AudioFileClip

# ── Paths ──────────────────────────────────────────────────────
FONT_BOLD = "C:/Windows/Fonts/consolab.ttf"
FONT_REG  = "C:/Windows/Fonts/consola.ttf"
LOGO_PATH = "assets/BuckitLogoTransparent.png"
OUTPUT_DIR = "output"

FPS          = 30
BASE_CPS     = 7.0
PRE_PAUSE    = 0.55
POST_HOLD    = 0.95
XFADE        = 0.15
CURSOR_BLINK = 0.42
LOGO_FADE    = 0.6
LOGO_HOLD    = 3.0
SR           = 44100

PROMPT = "buckit~ > "

LINES = [
    "Good idea...",
    "...wrong time?",
    "Buck it in now...",
    "...Buck it out later!",
]

THEMES = [
    {"bg_c": (12, 38, 28), "bg_e": (4, 14, 10),
     "prompt": (0, 140, 75), "text": (0, 255, 140),
     "glow": (0, 180, 90), "cursor": (0, 255, 140)},
    {"bg_c": (45, 24, 12), "bg_e": (20, 8, 4),
     "prompt": (190, 120, 35), "text": (255, 195, 60),
     "glow": (200, 140, 25), "cursor": (255, 195, 60)},
    {"bg_c": (14, 24, 58), "bg_e": (4, 8, 22),
     "prompt": (50, 110, 200), "text": (90, 185, 255),
     "glow": (40, 110, 220), "cursor": (90, 185, 255)},
    {"bg_c": (32, 18, 58), "bg_e": (12, 6, 22),
     "prompt": (180, 140, 35), "text": (255, 220, 60),
     "glow": (200, 170, 25), "cursor": (255, 220, 60)},
]

OUTPUTS = {
    "story_9x16":   (1080, 1920),
    "standard_4x3": (1440, 1080),
    "portrait_3x4": (1080, 1440),
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Sound  –  pre-generate one base thock, pitch-shift per key
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _base_thock():
    dur = 0.072
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False, dtype=np.float32)
    env = (1 - np.exp(-t * 5000)) * np.exp(-t * 48)
    f0 = np.float32(240)
    body = np.sin(2 * np.pi * f0 * t) * 0.55
    body += np.sin(2 * np.pi * f0 * 1.5 * t) * 0.18
    mid = np.sin(2 * np.pi * 1100 * t) * 0.22 * np.exp(-t * 130)
    noise = np.random.randn(n).astype(np.float32)
    k = np.ones(6, dtype=np.float32) / 6
    noise = np.convolve(noise, k, mode="same")
    trans = noise * np.exp(-t * 450) * 0.28
    tick = np.sin(2 * np.pi * 3600 * t) * 0.08 * np.exp(-t * 280)
    raw = (body + mid + tick) * env + trans
    # tiny reverb
    rn = int(SR * 0.02)
    ir = np.exp(-np.linspace(0, 5, rn, dtype=np.float32)) * 0.10
    ir[0] = 1.0
    raw = np.convolve(raw, ir)[:n]
    pk = np.max(np.abs(raw))
    return (raw / pk * 0.58).astype(np.float32) if pk > 0 else raw


# generate once at module level
_THOCK_BASE = _base_thock()


def _pitch_shift(base, factor):
    """Simple pitch shift via resampling."""
    n = len(base)
    new_n = int(n / factor)
    idx = np.linspace(0, n - 1, new_n).astype(int)
    return base[idx]


def build_audio(total_dur, ks_times):
    n = int(total_dur * SR)
    audio = np.zeros(n, dtype=np.float32)
    for kt in ks_times:
        pm = random.uniform(0.88, 1.14)
        vl = random.uniform(0.82, 1.0)
        c = _pitch_shift(_THOCK_BASE, pm) * np.float32(vl)
        p = int(kt * SR)
        e = min(p + len(c), n)
        if p < n:
            audio[p:e] += c[:e - p]
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
            d *= random.uniform(0.45, 0.7)
        elif ch == " ":
            d *= random.uniform(1.25, 1.7)
        elif ch in ".!?":
            d *= random.uniform(1.4, 2.0)
        else:
            d *= random.uniform(0.7, 1.25)
        times.append(times[-1] + d)
    return times


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Timeline
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def plan():
    scenes, ks = [], []
    t = 0.0
    for i, line in enumerate(LINES):
        ct = _char_times(line)
        td = ct[-1] + 1.0 / BASE_CPS
        s_start, ts, te = t, t + PRE_PAUSE, t + PRE_PAUSE + td
        s_end = te + POST_HOLD
        for c in ct:
            ks.append(ts + c)
        scenes.append(dict(idx=i, line=line, theme=THEMES[i],
                           ct=ct, start=s_start, ts=ts, te=te, end=s_end))
        t = s_end
    logo_start = t + 0.06
    total = logo_start + LOGO_FADE + LOGO_HOLD
    return scenes, ks, logo_start, total


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Rendering  (memory-lean)
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


def _vignette_gradient(W, H, cc, ce):
    """Radial-ish vignette: cc at centre, ce at edges.
    Memory-friendly: builds row-by-row with float32."""
    cx, cy = np.float32(W / 2), np.float32(H / 2)
    mr = np.float32(math.hypot(cx, cy))
    x_dist2 = (np.arange(W, dtype=np.float32) - cx) ** 2  # (W,)
    out = np.empty((H, W, 3), dtype=np.uint8)
    for y in range(H):
        d = np.sqrt(x_dist2 + np.float32((y - cy) ** 2)) / mr
        np.clip(d, 0, 1, out=d)
        inv = 1.0 - d
        for ch in range(3):
            out[y, :, ch] = (np.float32(cc[ch]) * inv + np.float32(ce[ch]) * d).astype(np.uint8)
    return out


def _fit_font(W, text, ratio=0.90):
    tw_target = int(W * ratio)
    lo, hi, best = 20, 200, 40
    while lo <= hi:
        mid = (lo + hi) // 2
        bb = _font(mid).getbbox(text)
        tw = bb[2] - bb[0] if bb else mid * len(text)
        if tw <= tw_target:
            best = mid; lo = mid + 1
        else:
            hi = mid - 1
    return best


def render_typing(W, H, bg, theme, typed, cursor_on, fsz):
    frame = bg.copy()
    img = Image.fromarray(frame)
    draw = ImageDraw.Draw(img)
    mf = _font(fsz)
    cursor_ch = "\u2588" if cursor_on else " "
    full = PROMPT + typed + cursor_ch

    bb = mf.getbbox(full)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    tx, ty = (W - tw) // 2, (H - th) // 2

    # simple glow via offset draws
    gc_ = theme["glow"]
    for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, 1)]:
        draw.text((tx + dx, ty + dy), full, fill=(*gc_, 35), font=mf)

    # prompt dim
    draw.text((tx, ty), PROMPT, fill=theme["prompt"], font=mf)
    # typed text bright
    pbb = mf.getbbox(PROMPT)
    pw = pbb[2] - pbb[0] if pbb else 0
    draw.text((tx + pw, ty), typed + cursor_ch, fill=theme["text"], font=mf)

    result = np.asarray(img).copy()  # copy before img is deleted
    del img, draw
    return result


def render_logo(W, H, opacity, logo_img, logo_bg):
    img = Image.fromarray(logo_bg.copy()).convert("RGBA")
    draw = ImageDraw.Draw(img)

    if logo_img is not None:
        lsz = min(W, H) // 3
        lr = logo_img.resize((lsz, lsz), Image.LANCZOS).convert("RGBA")
        a = lr.split()[3].point(lambda p: int(p * opacity))
        lr.putalpha(a)
        lx, ly = (W - lsz) // 2, (H - lsz) // 2 - int(H * 0.10)
        img.paste(lr, (lx, ly), lr)
        del lr, a
    else:
        lsz, lx, ly = 0, W // 2, H // 2

    def _a(c):
        return tuple(int(x * opacity) for x in c) + (255,)

    tf = _font(int(min(W, H) * 0.085))
    t_ = "Buckit"
    bb = tf.getbbox(t_)
    t_y = ly + lsz + int(H * 0.025)
    draw.text(((W - (bb[2] - bb[0])) // 2, t_y), t_, fill=_a((255, 220, 55)), font=tf)

    sf = _font(int(min(W, H) * 0.030), bold=False)
    s = "Brain's External RAM"
    bb2 = sf.getbbox(s)
    sy = t_y + int(H * 0.065)
    draw.text(((W - (bb2[2] - bb2[0])) // 2, sy), s, fill=_a((170, 160, 190)), font=sf)

    gf = _font(int(min(W, H) * 0.022), bold=False)
    g = "Available on Google Play"
    bb3 = gf.getbbox(g)
    gy = sy + int(H * 0.055)
    draw.text(((W - (bb3[2] - bb3[0])) // 2, gy), g, fill=_a((120, 115, 140)), font=gf)

    result = np.asarray(img.convert("RGB")).copy()
    del img, draw
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Video generation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate(name, W, H):
    print(f"\n  [{name}] {W}x{H} ...")
    scenes, ks, logo_start, total = plan()

    try:
        logo_img = Image.open(LOGO_PATH).convert("RGBA")
    except Exception:
        logo_img = None

    longest = PROMPT + max(LINES, key=len) + "\u2588"
    fsz = _fit_font(W, longest, 0.92)
    print(f"    font: {fsz}px  duration: {total:.1f}s  frames: {int(total * FPS)}")

    # build backgrounds one at a time (row-by-row, low memory)
    print("    building backgrounds...")
    bgs = []
    for th in THEMES:
        bg = _vignette_gradient(W, H, th["bg_c"], th["bg_e"])
        bgs.append(bg)
        gc.collect()

    logo_bg = _vignette_gradient(W, H, (24, 18, 48), (8, 5, 18))
    gc.collect()
    print("    rendering frames...")

    frame_n = [0]

    def _scene_frame(si, t):
        sc = scenes[si]
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
        return render_typing(W, H, bgs[si], sc["theme"], typed, cur, fsz)

    def make_frame(t):
        frame_n[0] += 1
        if frame_n[0] % 90 == 0:
            gc.collect()

        for i in range(len(scenes) - 1):
            fs = scenes[i]["end"] - XFADE
            fe = scenes[i]["end"]
            if fs <= t < fe:
                alpha = int(((t - fs) / XFADE) * 255)
                fa = _scene_frame(i, fe - 0.001)
                fb = _scene_frame(i + 1, scenes[i + 1]["start"])
                out = ((fa.astype(np.uint16) * (255 - alpha)
                      + fb.astype(np.uint16) * alpha) >> 8).astype(np.uint8)
                del fa, fb
                return out

        for i, sc in enumerate(scenes):
            s = sc["start"]
            e = sc["end"] - (XFADE if i < len(scenes) - 1 else 0)
            if s <= t < e:
                return _scene_frame(i, t)
            if i == len(scenes) - 1 and e <= t < sc["end"]:
                return _scene_frame(i, t)

        if t >= logo_start:
            op = min((t - logo_start) / LOGO_FADE, 1.0)
            return render_logo(W, H, op, logo_img, logo_bg)

        return np.zeros((H, W, 3), dtype=np.uint8)

    video = VideoClip(make_frame, duration=total).with_fps(FPS)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    wav = os.path.join(OUTPUT_DIR, f"_tmp_{name}.wav")
    save_wav(build_audio(total, ks), wav)
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
    print("  Buckit - Brain's External RAM  |  Promo v2")
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
