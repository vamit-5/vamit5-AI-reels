"""
UZIVO generisanje preko Higgsfield DoP Standard modela (bolji kvalitet,
skuplji od Lite -- vraceno na ovaj tok po zahtevu, jer gotovi Drive klipovi
nisu davali dovoljno preciznu vezu sa sadrzajem skripte).

Za svaki segment (grupu recenica), Claude prvo smisli video prompt koji
DOSLOVNO prati sta se u tom delu prica (lib/edu_content.py), pa se taj
prompt salje Higgsfield-u da generise sliku+video. Svi segmenti se spajaju
u jedan kontinuiran "silent" video fajl koji tacno pokriva celu duzinu
audio naracije.
"""
import json
import os
import subprocess

from lib import video

MIN_SEGMENT_SECONDS = 2.0


def _ffprobe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def _segment_time_windows(sentences: list[str], segments: list[dict], audio_dur: float):
    char_counts = [len(s) for s in sentences]
    total_chars = sum(char_counts) or 1

    windows = []
    for seg in segments:
        seg_chars = sum(char_counts[seg["start"]:seg["end"] + 1])
        windows.append((seg_chars / total_chars) * audio_dur)

    durations = [max(MIN_SEGMENT_SECONDS, d) for d in windows]
    scale = audio_dur / sum(durations)
    final_durations = [d * scale for d in durations]

    timings, t = [], 0.0
    for d in final_durations:
        timings.append((t, t + d))
        t += d
    return timings


def build_segmented_video(sentences: list[str], segments: list[dict],
                           audio_dur: float, out_path: str, tmp_dir: str) -> str:
    timings = _segment_time_windows(sentences, segments, audio_dur)

    clip_paths = []
    for i, (seg, (start, end)) in enumerate(zip(segments, timings)):
        target_dur = end - start
        raw_clip = os.path.join(tmp_dir, f"edu_raw_{i}.mp4")
        video.generate_episode_video(
            seg["video_prompt_english"], seg["video_prompt_english"], raw_clip
        )
        print(f"Segment {i}: generisan preko DoP Standard")

        clip_dur = _ffprobe_duration(raw_clip)
        loops_needed = max(1, int(target_dur // clip_dur) + 1)
        fitted_clip = os.path.join(tmp_dir, f"edu_fitted_{i}.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-stream_loop", str(loops_needed - 1), "-i", raw_clip,
             "-t", str(target_dur), "-an", "-c:v", "libx264", "-preset", "veryfast",
             "-r", "30", fitted_clip],
            check=True, capture_output=True,
        )
        clip_paths.append(fitted_clip)

    concat_list_path = os.path.join(tmp_dir, "concat_list.txt")
    with open(concat_list_path, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p}'\n")

    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path,
         "-c:v", "libx264", "-preset", "veryfast", out_path],
        check=True, capture_output=True,
    )
    return out_path
