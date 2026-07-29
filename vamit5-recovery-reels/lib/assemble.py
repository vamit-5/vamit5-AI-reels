"""
Sastavlja finalni Reels klip od STVARNOG snimka (sa Google Drive-a):
1. Petlja/sece video da pokrije trajanje audio naracije
2. Skida original zvuk sa videa, mesa TTS glas (pun volumen) + pozadinsku
   muziku (15-20% jacine), obe petljane po potrebi
3. Deli celu naraciju na recenice i pravi PO JEDAN caption overlay za svaku,
   sa vremenskim prozorom srazmernim duzini recenice -- caption PRATI govor
   kroz ceo video, ne stoji zamrznut na jednom hook-u
4. Poslednjih ~6 sekundi (CTA) prikazuje app mockup sliku
5. Centriran, u donjem delu (ne na samom dnu) stalni VAMIT-5 logo, sakriven
   tokom CTA mockup slike da se ne preklapaju
"""
import json
import os
import random
import subprocess
import urllib.request

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1080, 1920
FONT_PATH = os.environ.get("CAPTION_FONT_PATH", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

MOCKUP_IMAGE_URL = "https://res.cloudinary.com/dnbjvccgy/image/upload/v1785345583/IMG_0599_lkdady.png"
LOGO_IMAGE_URL = "https://res.cloudinary.com/dqqljgtna/image/upload/v1778767942/VAMIT-5-removebg-preview_2_uvii77.png"

MOCKUP_DISPLAY_SECONDS = 6.0
MOCKUP_WIDTH = 640
LOGO_WIDTH = 150
MUSIC_VOLUME = 0.18  # 18% jacine, u okviru trazenih 15-20%

GREEN = (120, 220, 120, 255)
GREEN_FILL = (60, 170, 90, 235)


def _ffprobe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def _fetch_image(url: str, out_path: str, target_width: int):
    """Vraca (path, width, height) ili None ako preuzimanje ne uspe."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp, open(out_path, "wb") as f:
            f.write(resp.read())
        img = Image.open(out_path).convert("RGBA")
        ratio = target_width / img.width
        new_size = (target_width, int(img.height * ratio))
        img = img.resize(new_size)
        img.save(out_path)
        return out_path, new_size[0], new_size[1]
    except Exception:
        return None


def _find_highlight(text: str):
    """Nadji frazu koju treba istaci zelenom pozadinom -- 'VAMIT-5' ako
    postoji u hook tekstu, inace poslednja rec."""
    upper = text.upper()
    if "VAMIT-5" in upper:
        start = upper.index("VAMIT-5")
        return text[start:start + len("VAMIT-5")]
    words = text.split()
    return words[-1] if words else ""


import re


def _split_sentences(text: str) -> list[str]:
    parts = re.findall(r"[^.!?]+[.!?]?", text)
    return [p.strip() for p in parts if p.strip()]


def _make_caption_segment(segment_text: str, out_png: str):
    segment_text = segment_text.upper().rstrip(".!?")
    highlight = _find_highlight(segment_text).upper()

    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, 46)

    # razbij tekst na reci, oznaci koje reci pripadaju highlight frazi
    words = segment_text.split()
    highlight_words = highlight.split() if highlight else []

    def is_highlight_start(i):
        if not highlight_words:
            return False
        return words[i:i + len(highlight_words)] == highlight_words

    space_w = draw.textlength(" ", font=font)
    max_line_width = WIDTH - 280

    # slaganje reci u linije
    lines, current_line, current_w = [], [], 0
    i = 0
    while i < len(words):
        if is_highlight_start(i):
            chunk = words[i:i + len(highlight_words)]
            chunk_text = " ".join(chunk)
            chunk_w = draw.textlength(chunk_text, font=font)
            if current_w + chunk_w > max_line_width and current_line:
                lines.append(current_line)
                current_line, current_w = [], 0
            current_line.append(("HL", chunk_text, chunk_w))
            current_w += chunk_w + space_w
            i += len(highlight_words)
        else:
            w = words[i]
            w_width = draw.textlength(w, font=font)
            if current_w + w_width > max_line_width and current_line:
                lines.append(current_line)
                current_line, current_w = [], 0
            current_line.append(("TXT", w, w_width))
            current_w += w_width + space_w
            i += 1
    if current_line:
        lines.append(current_line)

    line_height = 64
    pad_x, pad_y = 40, 32
    block_h = line_height * len(lines) + pad_y * 2
    block_w = min(WIDTH - 140, max(
        sum(w for _, _, w in line) + space_w * (len(line) - 1) for line in lines
    ) + pad_x * 2)

    # pomereno nize (ispod sredine), ali ne skroz na dno
    top = int(HEIGHT * 0.56)
    left = (WIDTH - block_w) // 2

    # pozadinska providna tamna kutija sa zelenim okvirom (zaobljeni uglovi)
    draw.rounded_rectangle(
        [left, top, left + block_w, top + block_h],
        radius=32, fill=(15, 15, 15, 195), outline=GREEN, width=5,
    )

    y = top + pad_y
    for line in lines:
        line_w = sum(w for _, _, w in line) + space_w * (len(line) - 1)
        x = left + (block_w - line_w) / 2
        for kind, text, w in line:
            if kind == "HL":
                draw.rounded_rectangle(
                    [x - 10, y - 6, x + w + 10, y + line_height - 20],
                    radius=14, fill=GREEN_FILL,
                )
                draw.text((x, y), text, font=font, fill=(10, 10, 10, 255))
            else:
                draw.text((x, y), text, font=font, fill=(255, 255, 255, 255),
                          stroke_width=2, stroke_fill=(0, 0, 0, 255))
            x += w + space_w
        y += line_height

    img.save(out_png)
    return out_png


MIN_SEGMENT_SECONDS = 2.0


def _segment_timings(sentences: list[str], audio_dur: float):
    """Racuna (start, end) za svaku recenicu, srazmerno njenoj duzini u
    karakterima, sa minimalnim trajanjem po segmentu da ne "trepce" prebrzo."""
    char_counts = [len(s) for s in sentences]
    total_chars = sum(char_counts) or 1
    raw_durations = [(c / total_chars) * audio_dur for c in char_counts]
    durations = [max(MIN_SEGMENT_SECONDS, d) for d in raw_durations]
    scale = audio_dur / sum(durations)
    final_durations = [d * scale for d in durations]

    timings = []
    t = 0.0
    for d in final_durations:
        timings.append((t, t + d))
        t += d
    return timings


def assemble(raw_video_path: str, audio_path: str, narration_text: str,
             out_path: str, tmp_dir: str) -> str:
    audio_dur = _ffprobe_duration(audio_path)
    video_dur = _ffprobe_duration(raw_video_path)

    looped_video = os.path.join(tmp_dir, "looped.mp4")
    loops_needed = max(1, int(audio_dur // video_dur) + 1)
    subprocess.run(
        ["ffmpeg", "-y", "-stream_loop", str(loops_needed - 1), "-i", raw_video_path,
         "-t", str(audio_dur + 0.5), "-an", "-c:v", "libx264", "-preset", "veryfast",
         looped_video],
        check=True, capture_output=True,
    )

    # caption koji PRATI govor -- podeli naraciju na recenice, svaka dobija
    # svoj overlay PNG i svoj vremenski prozor (srazmeran duzini teksta)
    sentences = _split_sentences(narration_text)
    timings = _segment_timings(sentences, audio_dur)
    segment_pngs = []
    for i, sentence in enumerate(sentences):
        png_path = os.path.join(tmp_dir, f"segment_{i}.png")
        _make_caption_segment(sentence, png_path)
        segment_pngs.append(png_path)

    mockup_result = _fetch_image(MOCKUP_IMAGE_URL, os.path.join(tmp_dir, "mockup.png"), MOCKUP_WIDTH)
    logo_result = _fetch_image(LOGO_IMAGE_URL, os.path.join(tmp_dir, "logo.png"), LOGO_WIDTH)
    mockup_path, mockup_h = (mockup_result[0], mockup_result[2]) if mockup_result else (None, 0)
    logo_path = logo_result[0] if logo_result else None

    # muzika: nasumican mp3 iz Drive foldera, vec preuzet spolja u
    # main.py kao tmp_dir/music_raw.mp3 -- ovde ga petljamo do pune
    # duzine audio naracije (kao i video)
    music_raw_path = os.path.join(tmp_dir, "music_raw.mp3")
    has_music = os.path.exists(music_raw_path)
    music_path = None
    if has_music:
        music_dur = _ffprobe_duration(music_raw_path)
        music_loops = max(1, int(audio_dur // music_dur) + 1)
        music_path = os.path.join(tmp_dir, "music_looped.m4a")
        subprocess.run(
            ["ffmpeg", "-y", "-stream_loop", str(music_loops - 1), "-i", music_raw_path,
             "-t", str(audio_dur + 0.5), "-c:a", "aac", "-b:a", "192k", music_path],
            check=True, capture_output=True,
        )

    inputs = ["-i", looped_video]
    idx = 1
    segment_indices = []
    for png_path in segment_pngs:
        inputs += ["-i", png_path]
        segment_indices.append(idx)
        idx += 1

    logo_idx = mockup_idx = music_idx = None
    if logo_path:
        inputs += ["-i", logo_path]
        logo_idx = idx
        idx += 1
    if mockup_path:
        inputs += ["-i", mockup_path]
        mockup_idx = idx
        idx += 1
    inputs += ["-i", audio_path]
    voice_idx = idx
    idx += 1
    if has_music:
        inputs += ["-i", music_path]
        music_idx = idx
        idx += 1

    filter_parts = [
        f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT}[base]",
    ]
    last_v = "base"
    for i, seg_idx in enumerate(segment_indices):
        start, end = timings[i]
        next_v = f"cap{i}"
        filter_parts.append(
            f"[{last_v}][{seg_idx}:v]overlay=0:0:enable='between(t,{start:.2f},{end:.2f})'[{next_v}]"
        )
        last_v = next_v

    mockup_start = max(0.0, audio_dur - MOCKUP_DISPLAY_SECONDS) if mockup_idx is not None else None

    if logo_idx is not None:
        # centrirano, u donjem delu ali NE na samom dnu; sakriven tokom
        # CTA mockup slike (poslednjih par sekundi) da se ne preklapaju
        logo_y = int(HEIGHT * 0.80)
        if mockup_start is not None:
            enable_expr = f":enable='lt(t,{mockup_start:.2f})'"
        else:
            enable_expr = ""
        filter_parts.append(
            f"[{last_v}][{logo_idx}:v]overlay=(main_w-overlay_w)/2:{logo_y}{enable_expr}[vlogo]"
        )
        last_v = "vlogo"

    if mockup_idx is not None:
        # IG rezervise ~320px pri dnu za caption/dugmice -- mockup mora da
        # stane IZNAD toga, racunajuci njegovu stvarnu (skaliranu) visinu
        ig_bottom_safe = 320
        mockup_y = max(int(HEIGHT * 0.42), HEIGHT - ig_bottom_safe - mockup_h)
        filter_parts.append(
            f"[{last_v}][{mockup_idx}:v]overlay=(main_w-overlay_w)/2:{mockup_y}:"
            f"enable='gte(t,{mockup_start:.2f})'[vout]"
        )
        last_v = "vout"
    else:
        filter_parts.append(f"[{last_v}]null[vout]")
        last_v = "vout"

    if has_music:
        filter_parts.append(
            f"[{music_idx}:a]volume={MUSIC_VOLUME}[music_low]"
        )
        filter_parts.append(
            f"[{voice_idx}:a][music_low]amix=inputs=2:duration=first:dropout_transition=0[aout]"
        )
        audio_map = "[aout]"
    else:
        audio_map = f"{voice_idx}:a"

    filter_complex = ";".join(filter_parts)

    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", filter_complex,
           "-map", f"[{last_v}]", "-map", audio_map,
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-c:a", "aac", "-b:a", "160k", "-t", str(audio_dur), out_path]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path
