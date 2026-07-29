"""
Sastavlja finalni Reels klip:
1. Odredjuje trajanje audio naracije
2. Petlja/sece video da pokrije trajanje audija
3. Nalepljuje SAMO hook (kratak, 1-2 recenice) kao providan PNG overlay,
   pozicioniran ISPOD sredine kadra (ne preko celog videa), sa senkom i
   konturom oko slova radi citljivosti umesto pune pozadinske trake
4. Na poslednjih nekoliko sekundi (CTA momenat) prikazuje VAMIT-5 app
   mockup sliku (transparentna, sa Cloudinary-ja) na sredini-dole kadra
5. Overlay PNG-ovi + audio spajaju se preko ffmpeg-a u finalni mp4
"""
import json
import os
import subprocess
import urllib.request

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1080, 1920
FONT_PATH = os.environ.get("CAPTION_FONT_PATH", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
LOGO_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "vamit5_logo.png")

MOCKUP_IMAGE_URL = (
    "https://res.cloudinary.com/dqqljgtna/image/upload/v1778767942/"
    "VAMIT-5-removebg-preview_2_uvii77.png"
)
MOCKUP_DISPLAY_SECONDS = 3.5
MOCKUP_WIDTH = 620


def _ffprobe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def _wrap_text(draw, text, font, max_width):
    words = text.split()
    lines, current = [], ""
    for w in words:
        trial = (current + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def _draw_text_with_shadow(draw, xy, text, font, fill=(255, 255, 255, 255)):
    x, y = xy
    for dx, dy in ((3, 3), (-2, 2), (2, -2), (-2, -2)):
        draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, 200))
    draw.text((x, y), text, font=font, fill=fill, stroke_width=3, stroke_fill=(0, 0, 0, 255))


def _make_hook_overlay(hook_text: str, out_png: str):
    """Samo kratak hook, pozicioniran ISPOD sredine kadra, bez pune pozadine."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font = ImageFont.truetype(FONT_PATH, 58)
    max_width = WIDTH - 140
    lines = _wrap_text(draw, hook_text.upper(), font, max_width)

    line_height = 70
    block_height = line_height * len(lines)
    top = int(HEIGHT * 0.58)

    y = top
    for line in lines:
        lw = draw.textlength(line, font=font)
        _draw_text_with_shadow(draw, ((WIDTH - lw) / 2, y), line, font, fill=(150, 230, 150, 255))
        y += line_height

    img.save(out_png)
    return out_png, top + block_height


def _fetch_mockup(tmp_dir: str) -> str | None:
    try:
        req = urllib.request.Request(
            MOCKUP_IMAGE_URL,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        raw_path = os.path.join(tmp_dir, "mockup_raw.png")
        with urllib.request.urlopen(req, timeout=30) as resp, open(raw_path, "wb") as f:
            f.write(resp.read())

        img = Image.open(raw_path).convert("RGBA")
        ratio = MOCKUP_WIDTH / img.width
        img = img.resize((MOCKUP_WIDTH, int(img.height * ratio)))
        resized_path = os.path.join(tmp_dir, "mockup.png")
        img.save(resized_path)
        return resized_path
    except Exception:
        return None


def assemble(raw_video_path: str, audio_path: str, hook_text: str,
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

    hook_png, _ = _make_hook_overlay(hook_text, os.path.join(tmp_dir, "hook.png"))
    mockup_path = _fetch_mockup(tmp_dir)

    inputs = ["-i", looped_video, "-i", hook_png]
    if mockup_path:
        inputs += ["-i", mockup_path]
    inputs += ["-i", audio_path]
    audio_input_index = 3 if mockup_path else 2

    base_scale = (
        f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT}[base];[base][1:v]overlay=0:0[with_hook]"
    )

    if mockup_path:
        mockup_start = max(0.0, audio_dur - MOCKUP_DISPLAY_SECONDS)
        mockup_y = int(HEIGHT * 0.70)
        filter_complex = (
            f"{base_scale};"
            f"[with_hook][2:v]overlay=(main_w-overlay_w)/2:{mockup_y}:"
            f"enable='gte(t,{mockup_start})'[outv]"
        )
    else:
        filter_complex = f"{base_scale.replace('[with_hook]', '[outv]')}"

    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", filter_complex,
           "-map", "[outv]", "-map", f"{audio_input_index}:a",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-c:a", "aac", "-b:a", "160k", "-shortest", out_path]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path
