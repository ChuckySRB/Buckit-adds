#!/usr/bin/env python3
"""
Buckit - Brain's External RAM  ·  Promo Video Generator v6
───────────────────────────────────────────────────────────
  • 2-scene dialogue: user <-> buckit conversation
  • Scene 1: Dark blue bg / light blue text (problem)
  • Scene 2: Light mint-green bg / dark green text (solution) — inverted feel
  • Glitch transition between scenes
  • CRT scanlines
  • Real tactile keyboard sounds + enter sound
  • Last slide: brand colors, QR code, no black
  • Outputs: 9:16 (stories) + 4:5 (feed)
"""

import os, gc, math, wave, random
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import VideoClip, AudioFileClip

# -- Paths --
FONT_BOLD = "C:/Windows/Fonts/consolab.ttf"
FONT_REG  = "C:/Windows/Fonts/consola.ttf"
LOGO_PATH = "assets/BuckitLogoTransparent.png"
QR_PATH   = "assets/GooglePlayQR.png"
SOUND_DIR = "assets/sounds"
OUTPUT_DIR = "output"

FPS         = 30
PRE_PAUSE   = 0.45
POST_HOLD   = 0.85
GLITCH_DUR  = 0.35
LOGO_DUR    = 3.5
SR          = 44100

# -- Scene color themes --
# Scene 1: Dark terminal — dark blue bg, light blue/cyan text
SCENE1_BG       = (15, 20, 55)       # deep navy
SCENE1_TEXT     = (140, 200, 255)     # light blue
SCENE1_PROMPT   = (60, 75, 130)      # dim blue-purple
SCENE1_CURSOR   = (140, 200, 255)
SCENE1_HIGHLIGHT = (255, 204, 0)     # Buckit yellow

# Scene 2: Light terminal — mint/green bg, dark green text
SCENE2_BG       = (195, 235, 210)    # soft mint green
SCENE2_TEXT     = (20, 70, 40)       # dark forest green
SCENE2_PROMPT   = (90, 150, 110)     # mid green
SCENE2_CURSOR   = (20, 70, 40)
SCENE2_HIGHLIGHT = (200, 130, 0)     # warm amber for "Buck it" on light bg

# Logo slide — brand themed, no black
LOGO_BG         = (18, 15, 48)       # deep purple-navy
LOGO_TITLE_CLR  = (255, 220, 55)     # Buckit yellow
LOGO_SUB_CLR    = (180, 175, 210)    # soft lavender
LOGO_BADGE_CLR  = (140, 135, 170)    # muted purple
LOGO_LINK_CLR   = (120, 180, 255)    # soft blue for link

SCENE_THEMES = [
    {"bg": SCENE1_BG, "text": SCENE1_TEXT, "prompt": SCENE1_PROMPT,
     "cursor": SCENE1_CURSOR, "highlight": SCENE1_HIGHLIGHT},
    {"bg": SCENE2_BG, "text": SCENE2_TEXT, "prompt": SCENE2_PROMPT,
     "cursor": SCENE2_CURSOR, "highlight": SCENE2_HIGHLIGHT},
]

# -- Dialogue prompts --
USER_PROMPT   = "you> "
BUCKIT_PROMPT = "buckit> "

# -- 2-scene dialogue structure --
# Alternating user/buckit lines with emoji responses
SCENE_DEFS = [
    {   # Scene 1: THE PROBLEM — dark terminal
        "lines": [
            {"text": "Good idea!",       "highlights": [], "who": "user"},
            {"text": "(* - *)b",          "highlights": [], "who": "buckit"},
            {"text": "But wrong time...", "highlights": [], "who": "user"},
            {"text": ":/",                "highlights": [], "who": "buckit"},
        ],
        "typing_cps": [10, 14, 8.5, 14],
        "inter_line_pause": [0.35, 0.30, 0.45],
    },
    {   # Scene 2: THE SOLUTION — light terminal
        "lines": [
            {"text": "Buck it in now! >>",      "highlights": [(0, 7)], "who": "buckit"},
            {"text": "O_O!",                     "highlights": [],       "who": "user"},
            {"text": "Buck it out later! :D",    "highlights": [(0, 7)], "who": "buckit"},
            {"text": "(^ o ^)/ !!",              "highlights": [],       "who": "user"},
        ],
        "typing_cps": [10.5, 16, 9, 16],
        "inter_line_pause": [0.30, 0.35, 0.25],
    },
]

OUTPUTS = {
    "story_9x16": (1080, 1920),
    "feed_4x5":   (1080, 1350),
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Sound
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
#  Typing rhythm
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _char_times(line, cps):
    times = [0.0]
    base = 1.0 / cps
    for i in range(len(line) - 1):
        ch = line[i]
        d = base
        if i < 2:
            d *= random.uniform(1.3, 1.6)
        elif ch == "." and i + 1 < len(line) and line[i + 1] == ".":
            d *= random.uniform(0.40, 0.60)
        elif ch == " ":
            d *= random.uniform(1.15, 1.5)
        elif ch in ".!?:":
            d *= random.uniform(1.2, 1.7)
        elif ch in ">/<()^*_":
            d *= random.uniform(0.5, 0.75)
        else:
            d *= random.uniform(0.70, 1.15)
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
                pause = sdef["inter_line_pause"][li - 1]
                t += pause
                ks_events.append((t, "enter"))
                type_start = t + 0.08

            ct = _char_times(text, cps)
            type_end = type_start + ct[-1] + 1.0 / cps

            for ci, c_t in enumerate(ct):
                ks_events.append((type_start + c_t, text[ci]))

            lines_info.append({
                "text": text,
                "highlights": ldef.get("highlights", []),
                "who": ldef.get("who", "user"),
                "type_start": type_start,
                "type_end": type_end,
                "ct": ct,
            })
            t = type_end

        scene_end = t + POST_HOLD
        phases.append({"type": "scene", "idx": si, "start": scene_start,
                        "end": scene_end, "lines": lines_info})
        t = scene_end

        if si < len(SCENE_DEFS) - 1:
            phases.append({"type": "glitch", "start": t, "end": t + GLITCH_DUR,
                           "from_idx": si, "to_idx": si + 1})
            t += GLITCH_DUR

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


def _flat_bg(W, H, color):
    """Truly flat solid background — no gradient, no vignette."""
    bg = np.empty((H, W, 3), dtype=np.uint8)
    bg[:, :, 0] = color[0]
    bg[:, :, 1] = color[1]
    bg[:, :, 2] = color[2]
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


def _colored_segments(visible, highlights, text_color, highlight_color):
    """Split visible text into (text, color) segments."""
    if not highlights or not visible:
        return [(visible, text_color)]
    colors = [text_color] * len(visible)
    for s, e in highlights:
        for i in range(max(0, s), min(e, len(visible))):
            colors[i] = highlight_color
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

def render_scene(W, H, bg, phase, t, fsz, x_start, theme):
    """Render a scene at time t. Multiple dialogue lines, left-aligned, vertically centred."""
    vis_lines = []
    cursor_li = -1

    for li, ln in enumerate(phase["lines"]):
        if t >= ln["type_start"]:
            if t < ln["type_end"]:
                elapsed = t - ln["type_start"]
                n = sum(1 for c in ln["ct"] if c <= elapsed)
            else:
                n = len(ln["text"])
            vis_lines.append((ln["text"], n, ln["highlights"], ln["who"]))
            cursor_li = len(vis_lines) - 1
        elif t >= ln["type_start"] - 0.08 and li > 0:
            vis_lines.append((ln["text"], 0, ln["highlights"], ln["who"]))
            cursor_li = len(vis_lines) - 1

    if not vis_lines:
        first_who = phase["lines"][0]["who"] if phase["lines"] else "user"
        vis_lines = [("", 0, [], first_who)]
        cursor_li = 0

    is_typing = any(ln["type_start"] <= t < ln["type_end"] for ln in phase["lines"])
    cursor_on = True if is_typing else (int(t * 4) % 2 == 0)

    frame = bg.copy()
    img = Image.fromarray(frame)
    draw = ImageDraw.Draw(img)
    mf = _font(fsz)

    test_bb = mf.getbbox("Mg|")
    line_h = test_bb[3] - test_bb[1]
    line_spacing = int(line_h * 1.55)
    max_lines = len(phase["lines"])
    total_block_h = line_h + (max_lines - 1) * line_spacing
    y_start = (H - total_block_h) // 2

    for vi, (text, n_typed, highlights, who) in enumerate(vis_lines):
        y = y_start + vi * line_spacing
        x = x_start

        # Draw prompt based on who's typing
        prompt = BUCKIT_PROMPT if who == "buckit" else USER_PROMPT
        draw.text((x, y), prompt, fill=theme["prompt"], font=mf)
        pbb = mf.getbbox(prompt)
        px = x + (pbb[2] - pbb[0])

        # Draw typed text with colour segments
        visible = text[:n_typed]
        for seg_text, seg_color in _colored_segments(visible, highlights,
                                                      theme["text"], theme["highlight"]):
            draw.text((px, y), seg_text, fill=seg_color, font=mf)
            sbb = mf.getbbox(seg_text)
            px += sbb[2] - sbb[0]

        # Cursor
        if vi == cursor_li:
            c_ch = "\u2588" if cursor_on else " "
            draw.text((px, y), c_ch, fill=theme["cursor"], font=mf)

    result = np.asarray(img).copy()
    del img, draw
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Glitch transition
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _glitch(frame, intensity):
    h, w = frame.shape[:2]
    out = frame.copy()
    shift = max(1, int(intensity * 18))

    if shift < w:
        out[:, :-shift, 0] = frame[:, shift:, 0]
        out[:, shift:, 2]  = frame[:, :-shift, 2]

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

    flicker = np.float32(1.0 + (random.random() - 0.5) * intensity * 0.7)
    out = np.clip(out.astype(np.float32) * flicker, 0, 255).astype(np.uint8)

    return out


def render_glitch(frame_a, frame_b, progress, W, H):
    intensity = math.sin(progress * math.pi)
    alpha = int(min(progress * 1.8, 1.0) * 255)
    blended = ((frame_a.astype(np.uint16) * (255 - alpha)
              + frame_b.astype(np.uint16) * alpha) >> 8).astype(np.uint8)
    return _glitch(blended, intensity)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Logo end card — no black, QR code
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def render_logo(W, H, t_in, logo_img, logo_bg_arr, qr_img):
    img = Image.fromarray(logo_bg_arr.copy()).convert("RGBA")
    draw = ImageDraw.Draw(img)

    logo_dur = 0.6
    title_t, sub_t, badge_t, qr_t = 0.4, 0.7, 1.0, 1.2

    # Layout: logo at top area, text below, QR at bottom
    logo_area_top = int(H * 0.08)

    if logo_img is not None:
        lsz_base = min(W, H) // 4
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
        ly = logo_area_top + (lsz_base - lsz) // 2
        img.paste(lr, (lx, ly), lr)
        del lr, a
        text_top = logo_area_top + lsz_base + int(H * 0.03)
    else:
        text_top = int(H * 0.30)

    def _fade(color, start_t):
        if t_in < start_t:
            return tuple(color) + (0,)
        p = min((t_in - start_t) / 0.35, 1.0)
        a = int(_ease_out_cubic(p) * 255)
        return tuple(color) + (a,)

    # Title: "Buckit"
    tf = _font(int(min(W, H) * 0.085))
    bb = tf.getbbox("Buckit")
    ty = text_top
    draw.text(((W - (bb[2] - bb[0])) // 2, ty), "Buckit",
              fill=_fade(LOGO_TITLE_CLR, title_t), font=tf)

    # Subtitle
    sf = _font(int(min(W, H) * 0.032), bold=False)
    bb2 = sf.getbbox("Brain's External RAM")
    sy = ty + int(H * 0.07)
    draw.text(((W - (bb2[2] - bb2[0])) // 2, sy), "Brain's External RAM",
              fill=_fade(LOGO_SUB_CLR, sub_t), font=sf)

    # "Available on Google Play"
    gf = _font(int(min(W, H) * 0.024), bold=False)
    bb3 = gf.getbbox("Available on Google Play")
    gy = sy + int(H * 0.06)
    draw.text(((W - (bb3[2] - bb3[0])) // 2, gy), "Available on Google Play",
              fill=_fade(LOGO_BADGE_CLR, badge_t), font=gf)

    # QR code
    if qr_img is not None:
        qr_sz = min(W, H) // 4
        qr_y = gy + int(H * 0.06)
        if t_in >= qr_t:
            p = min((t_in - qr_t) / 0.4, 1.0)
            a_val = int(_ease_out_cubic(p) * 255)
            qr_resized = qr_img.resize((qr_sz, qr_sz), Image.LANCZOS).convert("RGBA")
            # Set alpha
            r, g, b, qa = qr_resized.split()
            qa = qa.point(lambda x: int(x * a_val / 255))
            qr_resized.putalpha(qa)
            qr_x = (W - qr_sz) // 2
            img.paste(qr_resized, (qr_x, qr_y), qr_resized)
            del qr_resized

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

    try:
        qr_img = Image.open(QR_PATH).convert("RGBA")
    except Exception:
        qr_img = None

    # Font size: fit longest possible display line (with prompt)
    all_texts = []
    for sd in SCENE_DEFS:
        for l in sd["lines"]:
            prompt = BUCKIT_PROMPT if l.get("who") == "buckit" else USER_PROMPT
            all_texts.append(prompt + l["text"] + "\u2588")
    longest = max(all_texts, key=len)
    fsz = _fit_font(W, longest, 0.94)

    mf = _font(fsz)
    longest_bb = mf.getbbox(longest)
    longest_w = longest_bb[2] - longest_bb[0]
    x_start = (W - longest_w) // 2

    print(f"    font: {fsz}px  duration: {total:.1f}s  frames: {int(total * FPS)}")

    # Backgrounds — flat, no vignette
    print("    building backgrounds...")
    scene_bgs = [_flat_bg(W, H, theme["bg"]) for theme in SCENE_THEMES]
    logo_bg = _flat_bg(W, H, LOGO_BG)
    gc.collect()

    scene_phases = [p for p in phases if p["type"] == "scene"]

    frame_n = [0]

    def _get_scene_frame(si, t):
        return render_scene(W, H, scene_bgs[si], scene_phases[si], t, fsz,
                           x_start, SCENE_THEMES[si])

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
                    fa = _get_scene_frame(fi, scene_phases[fi]["end"] - 0.001)
                    fb = _get_scene_frame(ti, scene_phases[ti]["start"])
                    frame = render_glitch(fa, fb, progress, W, H)
                    del fa, fb
                    return _apply_crt_scanlines(frame)

                elif phase["type"] == "logo":
                    t_in = t - phase["start"]
                    return render_logo(W, H, t_in, logo_img, logo_bg, qr_img)

        return np.zeros((H, W, 3), dtype=np.uint8)

    video = VideoClip(make_frame, duration=total).with_fps(FPS)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    wav = os.path.join(OUTPUT_DIR, f"_tmp_{name}.wav")
    save_wav(build_audio(total, ks_events), wav)
    video = video.with_audio(AudioFileClip(wav))

    out = os.path.join(OUTPUT_DIR, f"buckit_promo_{name}.mp4")

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
    print("  Buckit - Brain's External RAM  |  Promo v6")
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
