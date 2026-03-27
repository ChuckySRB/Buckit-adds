#!/usr/bin/env python3
"""
Buckit – Brain's External RAM  ·  Promo Video Generator v3
───────────────────────────────────────────────────────────
v3 improvements over v2:
  1. Ken Burns slow zoom throughout each scene
  2. Better keyboard thock sound (richer, with room tone)
  3. Visual emphasis pulse on "Buck it" in scenes 3-4
  4. Scene energy escalation (subtle → bold across scenes)
  5. Polished end card with bounce/scale logo animation
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
LOGO_DUR     = 3.8       # total logo scene duration
SR           = 44100

PROMPT = "buckit~ > "

LINES = [
    "Good idea...",
    "...wrong time?",
    "Buck it in now...",
    "...Buck it out later!",
]

# ── Scene themes with escalation built in ──────────────────────
# Scenes 1-2 (problem) are muted; 3-4 (solution) are bolder/brighter.
# Each theme also has a glow_intensity multiplier and zoom_speed.
THEMES = [
    {   # 1 — muted teal · quiet inspiration
        "bg_c": (10, 32, 24),  "bg_e": (3, 12, 8),
        "prompt": (0, 110, 60), "text": (0, 210, 115),
        "glow": (0, 150, 75),   "cursor": (0, 210, 115),
        "glow_intensity": 30,    "zoom_range": (1.0, 1.025),
    },
    {   # 2 — muted amber · quiet doubt
        "bg_c": (38, 20, 10),  "bg_e": (16, 7, 3),
        "prompt": (160, 100, 30), "text": (225, 170, 50),
        "glow": (180, 120, 20),   "cursor": (225, 170, 50),
        "glow_intensity": 35,     "zoom_range": (1.0, 1.03),
    },
    {   # 3 — vivid navy · bold decision (Buckit blue)
        "bg_c": (16, 28, 65),  "bg_e": (5, 10, 25),
        "prompt": (60, 130, 220), "text": (100, 200, 255),
        "glow": (50, 140, 245),   "cursor": (100, 200, 255),
        "glow_intensity": 50,     "zoom_range": (1.0, 1.04),
    },
    {   # 4 — vivid purple/gold · bold confidence
        "bg_c": (38, 22, 65),  "bg_e": (14, 8, 25),
        "prompt": (200, 160, 40), "text": (255, 225, 65),
        "glow": (230, 190, 35),   "cursor": (255, 225, 65),
        "glow_intensity": 60,     "zoom_range": (1.0, 1.05),
    },
]

OUTPUTS = {
    "story_9x16":   (1080, 1920),
    "standard_4x3": (1440, 1080),
    "portrait_3x4": (1080, 1440),
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Sound v3 — richer thock + subtle room tone
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _base_thock():
    """Rich mechanical keyboard thock with proper resonance."""
    dur = 0.085  # slightly longer for fuller sound
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False, dtype=np.float32)

    # sharp attack, two-stage decay (fast initial + slow tail)
    attack = 1 - np.exp(-t * 6000)
    decay = 0.7 * np.exp(-t * 55) + 0.3 * np.exp(-t * 25)
    env = attack * decay

    # tonal body — lower fundamental for deeper "thock"
    f0 = np.float32(195)
    body  = np.sin(2 * np.pi * f0 * t) * 0.45
    body += np.sin(2 * np.pi * f0 * 1.5 * t) * 0.20   # fifth harmonic
    body += np.sin(2 * np.pi * f0 * 2.0 * t) * 0.08   # octave

    # mid-range "clack" presence
    mid = np.sin(2 * np.pi * 950 * t) * 0.18 * np.exp(-t * 110)
    mid += np.sin(2 * np.pi * 1400 * t) * 0.10 * np.exp(-t * 160)

    # initial transient — filtered noise burst (~4ms)
    noise = np.random.randn(n).astype(np.float32)
    # bandpass-ish: lowpass then subtract very-low
    k_lp = np.ones(4, dtype=np.float32) / 4
    k_hp = np.ones(20, dtype=np.float32) / 20
    noise_lp = np.convolve(noise, k_lp, mode="same")
    noise_hp = np.convolve(noise, k_hp, mode="same")
    noise_bp = noise_lp - noise_hp
    trans = noise_bp * np.exp(-t * 380) * 0.25

    # high-frequency "tick" detail
    tick = np.sin(2 * np.pi * 3200 * t) * 0.06 * np.exp(-t * 250)
    tick += np.sin(2 * np.pi * 5500 * t) * 0.03 * np.exp(-t * 400)

    raw = (body + mid + tick) * env + trans

    # room reverb (longer IR for more space)
    rn = int(SR * 0.04)
    ir = np.exp(-np.linspace(0, 5, rn, dtype=np.float32)) * 0.15
    ir[0] = 1.0
    # add a couple of early reflections
    ref1 = int(SR * 0.008)
    ref2 = int(SR * 0.018)
    if ref1 < rn:
        ir[ref1] += 0.06
    if ref2 < rn:
        ir[ref2] += 0.03
    raw = np.convolve(raw, ir)[:n]

    pk = np.max(np.abs(raw))
    return (raw / pk * 0.55).astype(np.float32) if pk > 0 else raw


_THOCK_BASE = _base_thock()


def _pitch_shift(base, factor):
    n = len(base)
    new_n = max(1, int(n / factor))
    idx = np.linspace(0, n - 1, new_n).astype(int)
    return base[idx]


def _room_tone(n_samples):
    """Very subtle low-frequency room hum."""
    t = np.linspace(0, n_samples / SR, n_samples, endpoint=False, dtype=np.float32)
    tone = np.sin(2 * np.pi * 55 * t) * 0.004
    tone += np.random.randn(n_samples).astype(np.float32) * 0.002
    # smooth it
    k = np.ones(100, dtype=np.float32) / 100
    tone = np.convolve(tone, k, mode="same")
    return tone


def build_audio(total_dur, ks_times):
    n = int(total_dur * SR)
    audio = _room_tone(n)
    for kt in ks_times:
        pm = random.uniform(0.86, 1.16)
        vl = random.uniform(0.80, 1.0)
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
        # find "Buck it" position for emphasis timing
        buck_idx = line.find("Buck it")
        buck_done_t = None
        if buck_idx >= 0:
            buck_end = buck_idx + len("Buck it")
            if buck_end - 1 < len(ct):
                buck_done_t = ts + ct[buck_end - 1]
        scenes.append(dict(idx=i, line=line, theme=THEMES[i],
                           ct=ct, start=s_start, ts=ts, te=te, end=s_end,
                           buck_done_t=buck_done_t))
        t = s_end
    logo_start = t + 0.06
    total = logo_start + LOGO_DUR
    return scenes, ks, logo_start, total


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


def _vignette_gradient(W, H, cc, ce):
    cx, cy = np.float32(W / 2), np.float32(H / 2)
    mr = np.float32(math.hypot(cx, cy))
    x_dist2 = (np.arange(W, dtype=np.float32) - cx) ** 2
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


def _ease_out_back(t):
    """Overshoot ease-out for bouncy animation. t in [0,1]."""
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * ((t - 1) ** 3) + c1 * ((t - 1) ** 2)


def _ease_out_cubic(t):
    return 1 - (1 - t) ** 3


def _apply_zoom(frame_arr, W, H, zoom):
    """Crop centre of zoomed frame. Works on numpy array via PIL."""
    if zoom <= 1.001:
        return frame_arr
    img = Image.fromarray(frame_arr)
    zw, zh = int(W * zoom), int(H * zoom)
    img = img.resize((zw, zh), Image.BILINEAR)
    left = (zw - W) // 2
    top  = (zh - H) // 2
    img = img.crop((left, top, left + W, top + H))
    result = np.asarray(img).copy()
    del img
    return result


def render_typing(W, H, bg, theme, typed, cursor_on, fsz,
                  glow_mult=1.0, brightness_boost=0):
    """Render one typing frame.
    glow_mult: multiplier on glow intensity (for emphasis pulse).
    brightness_boost: 0-80 additive brightness (for emphasis flash).
    """
    frame = bg.copy()

    # apply brightness boost if any (emphasis flash)
    if brightness_boost > 0:
        frame = np.minimum(
            frame.astype(np.uint16) + brightness_boost, 255
        ).astype(np.uint8)

    img = Image.fromarray(frame)
    draw = ImageDraw.Draw(img)
    mf = _font(fsz)
    cursor_ch = "\u2588" if cursor_on else " "
    full = PROMPT + typed + cursor_ch

    bb = mf.getbbox(full)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    tx, ty = (W - tw) // 2, (H - th) // 2

    # glow via offset draws — intensity scales with theme + emphasis
    gc_ = theme["glow"]
    base_alpha = int(theme["glow_intensity"] * glow_mult)
    base_alpha = min(base_alpha, 120)
    offsets = [(-3, 0), (3, 0), (0, -3), (0, 3),
               (-2, -2), (2, 2), (-2, 2), (2, -2)]
    for dx, dy in offsets:
        draw.text((tx + dx, ty + dy), full, fill=(*gc_, base_alpha), font=mf)

    # prompt dim
    draw.text((tx, ty), PROMPT, fill=theme["prompt"], font=mf)
    # typed text bright
    pbb = mf.getbbox(PROMPT)
    pw = pbb[2] - pbb[0] if pbb else 0
    draw.text((tx + pw, ty), typed + cursor_ch, fill=theme["text"], font=mf)

    result = np.asarray(img).copy()
    del img, draw
    return result


def render_logo(W, H, t_in, logo_img, logo_bg):
    """Animated end card: bounce-in logo, staggered text reveals."""
    img = Image.fromarray(logo_bg.copy()).convert("RGBA")
    draw = ImageDraw.Draw(img)

    # timing: logo bounces in 0→0.7s, title at 0.5s, subtitle at 0.8s, badge at 1.1s
    logo_anim_dur = 0.7
    title_start = 0.5
    sub_start = 0.8
    badge_start = 1.1

    # ── logo with bounce scale ──
    if logo_img is not None:
        lsz_base = min(W, H) // 3
        if t_in < logo_anim_dur:
            progress = t_in / logo_anim_dur
            scale = _ease_out_back(progress)
            opacity = _ease_out_cubic(min(progress * 2, 1.0))
        else:
            scale = 1.0
            opacity = 1.0

        lsz = max(1, int(lsz_base * scale))
        lr = logo_img.resize((lsz, lsz), Image.LANCZOS).convert("RGBA")
        a = lr.split()[3].point(lambda p: int(p * opacity))
        lr.putalpha(a)
        lx = (W - lsz) // 2
        ly_base = (H - lsz_base) // 2 - int(H * 0.10)
        ly = ly_base + (lsz_base - lsz) // 2  # keep centred during scale
        img.paste(lr, (lx, ly), lr)
        del lr, a
    else:
        lsz_base, lx, ly_base = 0, W // 2, H // 2

    def _fade_color(c, start_t):
        if t_in < start_t:
            return (0, 0, 0, 0)
        progress = min((t_in - start_t) / 0.4, 1.0)
        alpha = _ease_out_cubic(progress)
        return tuple(int(x * alpha) for x in c) + (255,)

    # ── "Buckit" title ──
    tf = _font(int(min(W, H) * 0.085))
    title = "Buckit"
    bb = tf.getbbox(title)
    t_y = ly_base + lsz_base + int(H * 0.025)
    draw.text(((W - (bb[2] - bb[0])) // 2, t_y), title,
              fill=_fade_color((255, 220, 55), title_start), font=tf)

    # ── subtitle ──
    sf = _font(int(min(W, H) * 0.030), bold=False)
    sub = "Brain's External RAM"
    bb2 = sf.getbbox(sub)
    sy = t_y + int(H * 0.065)
    draw.text(((W - (bb2[2] - bb2[0])) // 2, sy), sub,
              fill=_fade_color((170, 160, 190), sub_start), font=sf)

    # ── Google Play badge text ──
    gf = _font(int(min(W, H) * 0.022), bold=False)
    g = "Available on Google Play"
    bb3 = gf.getbbox(g)
    gy = sy + int(H * 0.055)
    draw.text(((W - (bb3[2] - bb3[0])) // 2, gy), g,
              fill=_fade_color((120, 115, 140), badge_start), font=gf)

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

    print("    building backgrounds...")
    bgs = []
    for th in THEMES:
        bgs.append(_vignette_gradient(W, H, th["bg_c"], th["bg_e"]))
        gc.collect()
    logo_bg = _vignette_gradient(W, H, (24, 18, 48), (8, 5, 18))
    gc.collect()
    print("    rendering frames...")

    frame_n = [0]

    def _scene_frame(si, t):
        sc = scenes[si]
        th = sc["theme"]
        line, ct = sc["line"], sc["ct"]

        # determine typed text
        if t < sc["ts"]:
            typed = ""
        elif t >= sc["te"]:
            typed = line
        else:
            elapsed = t - sc["ts"]
            n = sum(1 for c in ct if c <= elapsed)
            typed = line[:n]

        cur = True if t < sc["te"] else (int(t / CURSOR_BLINK) % 2 == 0)

        # ── Ken Burns zoom ──
        scene_dur = sc["end"] - sc["start"]
        progress = (t - sc["start"]) / scene_dur if scene_dur > 0 else 0
        z_lo, z_hi = th["zoom_range"]
        zoom = z_lo + (z_hi - z_lo) * progress

        # ── "Buck it" emphasis pulse (scenes 3-4) ──
        glow_mult = 1.0
        brightness_boost = 0
        zoom_bump = 0.0
        if sc["buck_done_t"] is not None and t >= sc["buck_done_t"]:
            dt = t - sc["buck_done_t"]
            if dt < 0.5:
                # sharp rise (0→0.15s), smooth decay (0.15→0.5s)
                if dt < 0.15:
                    pulse = math.sin(dt / 0.15 * math.pi / 2)
                else:
                    pulse = math.exp(-(dt - 0.15) * 5)
                glow_mult = 1.0 + pulse * 1.5       # glow flares up
                brightness_boost = int(pulse * 40)   # subtle flash
                zoom_bump = pulse * 0.025            # slight zoom punch

        zoom += zoom_bump

        frame = render_typing(W, H, bgs[si], th, typed, cur, fsz,
                              glow_mult, brightness_boost)
        frame = _apply_zoom(frame, W, H, zoom)
        return frame

    def make_frame(t):
        frame_n[0] += 1
        if frame_n[0] % 90 == 0:
            gc.collect()

        # crossfade zones
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
    print("  Buckit - Brain's External RAM  |  Promo v3")
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
