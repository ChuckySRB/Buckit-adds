#!/usr/bin/env python3
"""
Buckit - Brain's External RAM  ·  Promo Video Generator v8
───────────────────────────────────────────────────────────
  • 2-scene dialogue: busy_user123 <-> buckit conversation
  • Scene 1: Dark purple bg / lighter purple text (problem)
  • Scene 2: Light green bg / dark green text (inverted, solution)
  • Different colors per speaker (user vs buckit)
  • RAM loading bar animation for user lines
  • Glitch transition between scenes
  • CRT scanlines
  • Real tactile keyboard sounds + enter sound
  • Last slide: BUCKIT_TEXT.png + subtitle + QR + blinking text
  • Outputs: 9:16 (stories) + 4:5 (feed)
"""

import os, gc, math, wave, random
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import VideoClip, AudioFileClip

# -- Paths --
FONT_BOLD = "C:/Windows/Fonts/consolab.ttf"
FONT_REG  = "C:/Windows/Fonts/consola.ttf"
BUCKIT_TEXT_PATH = "assets/BUCKIT_TEXT.png"
QR_PATH   = "assets/GooglePlayQR.png"
SOUND_DIR = "assets/sounds"
OUTPUT_DIR = "output"

FPS         = 30
PRE_PAUSE   = 0.45
POST_HOLD   = 0.85
GLITCH_DUR  = 0.35
LOGO_DUR    = 8.0
SR          = 44100

# -- Scene 1: Dark purple terminal (the problem) --
SCENE1_BG          = (28, 15, 52)        # dark purple
SCENE1_USER_TEXT   = (180, 155, 235)     # lighter purple for user
SCENE1_USER_PROMPT = (110, 85, 170)      # mid purple prompt
SCENE1_BOT_TEXT    = (255, 220, 80)      # warm yellow for buckit
SCENE1_BOT_PROMPT  = (180, 150, 50)      # dim yellow prompt
SCENE1_CURSOR      = (180, 155, 235)
SCENE1_HIGHLIGHT   = (255, 204, 0)
SCENE1_RAM_FG      = (255, 80, 80)       # red for "full" RAM bar
SCENE1_RAM_DIM     = (70, 50, 95)        # dim bar background

# -- Scene 2: Green terminal inverted (medium green bg, dark green text) --
SCENE2_BG          = (0, 140, 75)        # v2 prompt green as bg
SCENE2_USER_TEXT   = (4, 14, 10)         # v2 dark edge color as text
SCENE2_USER_PROMPT = (8, 50, 30)         # slightly lighter dark green
SCENE2_BOT_TEXT    = (220, 255, 60)      # bright yellow-green for buckit
SCENE2_BOT_PROMPT  = (150, 190, 40)      # dimmer yellow-green
SCENE2_CURSOR      = (4, 14, 10)
SCENE2_HIGHLIGHT   = (255, 220, 0)       # yellow highlight
SCENE2_RAM_FG      = (4, 14, 10)         # dark green RAM bar
SCENE2_RAM_DIM     = (0, 100, 55)

# -- Logo slide --
LOGO_BG         = (18, 15, 48)
LOGO_SUB_CLR    = (200, 195, 230)
LOGO_BADGE_CLR  = (255, 220, 80)        # yellow for blinking text

SCENE_THEMES = [
    {"bg": SCENE1_BG,
     "user_text": SCENE1_USER_TEXT, "user_prompt": SCENE1_USER_PROMPT,
     "bot_text": SCENE1_BOT_TEXT, "bot_prompt": SCENE1_BOT_PROMPT,
     "cursor": SCENE1_CURSOR, "highlight": SCENE1_HIGHLIGHT,
     "ram_fg": SCENE1_RAM_FG, "ram_dim": SCENE1_RAM_DIM},
    {"bg": SCENE2_BG,
     "user_text": SCENE2_USER_TEXT, "user_prompt": SCENE2_USER_PROMPT,
     "bot_text": SCENE2_BOT_TEXT, "bot_prompt": SCENE2_BOT_PROMPT,
     "cursor": SCENE2_CURSOR, "highlight": SCENE2_HIGHLIGHT,
     "ram_fg": SCENE2_RAM_FG, "ram_dim": SCENE2_RAM_DIM},
]

# -- Prompts --
USER_PROMPT   = "busy_user123> "
BUCKIT_PROMPT = "buckit> "

# -- RAM bar config --
# Shown after user lines; scene 1 shows RAM filling up, scene 2 shows RAM freeing
RAM_BAR_WIDTH = 20  # chars
RAM_DISPLAY_DUR = 0.8  # seconds the bar animates after user finishes typing

# -- 2-scene dialogue structure --
SCENE_DEFS = [
    {   # Scene 1: THE PROBLEM — dark navy
        "lines": [
            {"text": "Good idea!",        "highlights": [], "who": "user"},
            {"text": "(* - *)b",           "highlights": [], "who": "buckit"},
            {"text": "But wrong time...",  "highlights": [], "who": "user"},
            {"text": ":/",                 "highlights": [], "who": "buckit"},
        ],
        "typing_cps": [10, 14, 8.5, 14],
        "inter_line_pause": [0.35, 0.30, 0.45],
        # RAM bars after user lines (line index -> bar config)
        "ram_bars": {
            0: {"start_pct": 72, "end_pct": 85, "label": "BRAIN RAM"},
            2: {"start_pct": 85, "end_pct": 98, "label": "BRAIN RAM"},
        },
    },
    {   # Scene 2: THE SOLUTION — dark green
        "lines": [
            {"text": "Buck it in now! >>",    "highlights": [(0, 7)], "who": "buckit"},
            {"text": "O_O !",                  "highlights": [],       "who": "user"},
            {"text": "Buck it out later! :D",  "highlights": [(0, 7)], "who": "buckit"},
            {"text": "\\(^ o ^)/ !!",          "highlights": [],       "who": "user"},
        ],
        "typing_cps": [10.5, 16, 9, 16],
        "inter_line_pause": [0.30, 0.35, 0.25],
        "ram_bars": {
            1: {"start_pct": 98, "end_pct": 45, "label": "BRAIN RAM"},
            3: {"start_pct": 45, "end_pct": 12, "label": "BRAIN RAM"},
        },
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
        elif ch in ">/<()^*_\\":
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

            # If this line has a RAM bar, add extra time for animation
            has_ram = li in sdef.get("ram_bars", {})
            ram_end = type_end + RAM_DISPLAY_DUR if has_ram else type_end

            lines_info.append({
                "text": text,
                "highlights": ldef.get("highlights", []),
                "who": ldef.get("who", "user"),
                "type_start": type_start,
                "type_end": type_end,
                "ram_end": ram_end,
                "ct": ct,
                "ram_bar": sdef.get("ram_bars", {}).get(li),
            })
            t = ram_end

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
    """CRT scanlines: darken every 2nd row strongly for visible effect."""
    frame[1::2] = (frame[1::2].astype(np.uint16) * 140 >> 8).astype(np.uint8)
    return frame


def _draw_ram_bar(draw, x, y, font, progress, start_pct, end_pct, label, fg_color, dim_color):
    """Draw a terminal-style progress bar: [########    ] 92% BRAIN RAM"""
    current_pct = start_pct + (end_pct - start_pct) * progress
    current_pct = max(0, min(100, current_pct))
    filled = int(RAM_BAR_WIDTH * current_pct / 100)
    empty = RAM_BAR_WIDTH - filled

    bar_str = "[" + "#" * filled + " " * empty + "]"
    pct_str = f" {int(current_pct)}% {label}"

    # Draw bar in color
    draw.text((x, y), bar_str, fill=fg_color, font=font)
    bb = font.getbbox(bar_str)
    bx = x + (bb[2] - bb[0])
    draw.text((bx, y), pct_str, fill=dim_color, font=font)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Scene rendering
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def render_scene(W, H, bg, phase, t, fsz, x_start, theme):
    vis_lines = []
    cursor_li = -1

    for li, ln in enumerate(phase["lines"]):
        if t >= ln["type_start"]:
            if t < ln["type_end"]:
                elapsed = t - ln["type_start"]
                n = sum(1 for c in ln["ct"] if c <= elapsed)
            else:
                n = len(ln["text"])
            vis_lines.append((ln["text"], n, ln["highlights"], ln["who"], li, ln))
            cursor_li = len(vis_lines) - 1
        elif t >= ln["type_start"] - 0.08 and li > 0:
            vis_lines.append((ln["text"], 0, ln["highlights"], ln["who"], li, ln))
            cursor_li = len(vis_lines) - 1

    if not vis_lines:
        first_who = phase["lines"][0]["who"] if phase["lines"] else "user"
        vis_lines = [("", 0, [], first_who, 0, phase["lines"][0] if phase["lines"] else None)]
        cursor_li = 0

    is_typing = any(ln["type_start"] <= t < ln["type_end"] for ln in phase["lines"])
    cursor_on = True if is_typing else (int(t * 4) % 2 == 0)

    frame = bg.copy()
    img = Image.fromarray(frame)
    draw = ImageDraw.Draw(img)
    mf = _font(fsz)
    sf = _font(max(16, int(fsz * 0.65)), bold=False)  # smaller font for RAM bar

    test_bb = mf.getbbox("Mg|")
    line_h = test_bb[3] - test_bb[1]
    line_spacing = int(line_h * 1.55)
    small_bb = sf.getbbox("Mg|")
    small_h = small_bb[3] - small_bb[1]
    ram_spacing = int(small_h * 1.3)

    # Calculate total block height including RAM bars
    max_lines = len(phase["lines"])
    # Count how many RAM bars we'll show
    n_ram_bars = sum(1 for ln in phase["lines"] if ln.get("ram_bar") is not None)
    total_block_h = line_h + (max_lines - 1) * line_spacing + n_ram_bars * ram_spacing
    y_start = (H - total_block_h) // 2

    y = y_start
    for vi, (text, n_typed, highlights, who, orig_li, ln_data) in enumerate(vis_lines):
        x = x_start

        # Pick colors based on who's speaking
        if who == "buckit":
            prompt = BUCKIT_PROMPT
            prompt_color = theme["bot_prompt"]
            text_color = theme["bot_text"]
        else:
            prompt = USER_PROMPT
            prompt_color = theme["user_prompt"]
            text_color = theme["user_text"]

        draw.text((x, y), prompt, fill=prompt_color, font=mf)
        pbb = mf.getbbox(prompt)
        px = x + (pbb[2] - pbb[0])

        visible = text[:n_typed]
        for seg_text, seg_color in _colored_segments(visible, highlights,
                                                      text_color, theme["highlight"]):
            draw.text((px, y), seg_text, fill=seg_color, font=mf)
            sbb = mf.getbbox(seg_text)
            px += sbb[2] - sbb[0]

        # Cursor on current line
        if vi == cursor_li:
            c_ch = "\u2588" if cursor_on else " "
            cursor_color = theme["cursor"]
            draw.text((px, y), c_ch, fill=cursor_color, font=mf)

        y += line_spacing

        # RAM bar after this line if applicable
        if ln_data and ln_data.get("ram_bar") and t >= ln_data["type_end"]:
            ram = ln_data["ram_bar"]
            ram_progress = min((t - ln_data["type_end"]) / RAM_DISPLAY_DUR, 1.0)
            ram_progress = _ease_out_cubic(ram_progress)
            _draw_ram_bar(draw, x_start, y - line_spacing + int(line_h * 1.15),
                         sf, ram_progress,
                         ram["start_pct"], ram["end_pct"], ram["label"],
                         theme["ram_fg"], theme["ram_dim"])
            y += ram_spacing

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
#  Logo end card — BUCKIT_TEXT.png + subtitle + QR + blinking text
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def render_logo(W, H, t_in, buckit_text_img, logo_bg_arr, qr_img):
    img = Image.fromarray(logo_bg_arr.copy()).convert("RGBA")
    draw = ImageDraw.Draw(img)

    # Timing
    text_img_t = 0.3    # BUCKIT_TEXT.png appears
    sub_t = 0.6         # subtitle appears
    qr_t = 0.9          # QR code appears
    badge_t = 1.3       # blinking text appears

    # Layout: everything vertically centered
    # Estimate total block height to center it
    text_img_h = 0
    text_img_w = 0
    if buckit_text_img is not None:
        # Scale to ~60% of width
        scale = (W * 0.60) / buckit_text_img.width
        text_img_w = int(buckit_text_img.width * scale)
        text_img_h = int(buckit_text_img.height * scale)

    sf = _font(int(min(W, H) * 0.032), bold=False)
    sub_bb = sf.getbbox("Brain's External RAM")
    sub_h = sub_bb[3] - sub_bb[1]

    qr_sz = min(W, H) // 3

    gf = _font(int(min(W, H) * 0.026), bold=True)
    badge_bb = gf.getbbox("Available on Google Play")
    badge_h = badge_bb[3] - badge_bb[1]

    gap1 = int(H * 0.03)   # between logo text and subtitle
    gap2 = int(H * 0.03)   # between subtitle and QR
    gap3 = int(H * 0.025)  # between QR and badge text

    total_h = text_img_h + gap1 + sub_h + gap2 + qr_sz + gap3 + badge_h
    y_top = (H - total_h) // 2

    def _fade_alpha(start_t):
        if t_in < start_t:
            return 0.0
        return min((t_in - start_t) / 0.35, 1.0)

    # 1. BUCKIT_TEXT.png
    if buckit_text_img is not None and t_in >= text_img_t:
        a = _fade_alpha(text_img_t)
        scale_anim = _ease_out_back(min((t_in - text_img_t) / 0.5, 1.0)) if t_in < text_img_t + 0.5 else 1.0
        cur_w = max(1, int(text_img_w * scale_anim))
        cur_h = max(1, int(text_img_h * scale_anim))
        resized = buckit_text_img.resize((cur_w, cur_h), Image.LANCZOS).convert("RGBA")
        # Apply alpha
        r, g, b, ra = resized.split()
        ra = ra.point(lambda p: int(p * _ease_out_cubic(a)))
        resized.putalpha(ra)
        lx = (W - cur_w) // 2
        ly = y_top + (text_img_h - cur_h) // 2
        img.paste(resized, (lx, ly), resized)
        del resized

    cur_y = y_top + text_img_h + gap1

    # 2. Subtitle
    if t_in >= sub_t:
        a = _ease_out_cubic(_fade_alpha(sub_t))
        sub_color = tuple(int(c * a) for c in LOGO_SUB_CLR) + (int(255 * a),)
        sub_w = sub_bb[2] - sub_bb[0]
        draw.text(((W - sub_w) // 2, cur_y), "Brain's External RAM",
                  fill=sub_color, font=sf)

    cur_y += sub_h + gap2

    # 3. QR code
    if qr_img is not None and t_in >= qr_t:
        a = _ease_out_cubic(_fade_alpha(qr_t))
        qr_resized = qr_img.resize((qr_sz, qr_sz), Image.LANCZOS).convert("RGBA")
        r, g, b, qa = qr_resized.split()
        qa = qa.point(lambda p: int(p * a))
        qr_resized.putalpha(qa)
        qr_x = (W - qr_sz) // 2
        img.paste(qr_resized, (qr_x, cur_y), qr_resized)
        del qr_resized

    cur_y += qr_sz + gap3

    # 4. Blinking "Available on Google Play"
    if t_in >= badge_t:
        # Blink at ~1.5Hz
        blink_on = (int(t_in * 3) % 2 == 0)
        if blink_on:
            a = _ease_out_cubic(min((t_in - badge_t) / 0.3, 1.0))
            badge_color = tuple(int(c * a) for c in LOGO_BADGE_CLR) + (int(255 * a),)
            badge_w = badge_bb[2] - badge_bb[0]
            draw.text(((W - badge_w) // 2, cur_y), "Available on Google Play",
                      fill=badge_color, font=gf)

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
        buckit_text_img = Image.open(BUCKIT_TEXT_PATH).convert("RGBA")
    except Exception:
        buckit_text_img = None

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
    # Also consider RAM bar text width
    ram_text = "[" + "#" * RAM_BAR_WIDTH + "] 100% BRAIN RAM"
    all_texts.append(ram_text)
    longest = max(all_texts, key=len)
    fsz = _fit_font(W, longest, 0.94)

    mf = _font(fsz)
    longest_bb = mf.getbbox(longest)
    longest_w = longest_bb[2] - longest_bb[0]
    x_start = (W - longest_w) // 2

    print(f"    font: {fsz}px  duration: {total:.1f}s  frames: {int(total * FPS)}")

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
                    return render_logo(W, H, t_in, buckit_text_img, logo_bg, qr_img)

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
    print("  Buckit - Brain's External RAM  |  Promo v8")
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
