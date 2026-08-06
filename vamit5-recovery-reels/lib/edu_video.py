"""
NOVA VERZIJA: umesto da generise AI video UZIVO preko Higgsfield API-ja
(skupo, cesto nerealisticno), sada BIRA gotove, unapred napravljene
klipove iz Google Drive "AI klipovi" foldera (napravljeni preko pravog
higgsfield.ai sajta, realisticniji kvalitet, jednom placeno kroz
kredite koje vec imas).

Za svaki segment (grupu recenica) bira SLEDECI klip u rotaciji (bez
ponavljanja UNUTAR jednog Reel-a), petlja/sece ga na tacno dodeljeno
trajanje, i spaja SVE segmente u jedan kontinuiran "silent" video fajl
koji tacno pokriva celu duzinu audio naracije.
"""
import json
import os
import subprocess

from lib import gdrive

MIN_SEGMENT_SECONDS = 2.0


def _ffprobe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def _segment_time_windows(sentences: list[str], boundaries: list[list[int]], audio_dur: float):
    """Racuna (start, end) sekunde za svaki segment, srazmerno ukupnom broju
    karaktera recenica koje taj segment pokriva."""
    char_counts = [len(s) for s in sentences]
    total_chars = sum(char_counts) or 1

    windows = []
    for start, end in boundaries:
        seg_chars = sum(char_counts[start:end + 1])
        windows.append((seg_chars / total_chars) * audio_dur)

    durations = [max(MIN_SEGMENT_SECONDS, d) for d in windows]
    scale = audio_dur / sum(durations)
    final_durations = [d * scale for d in durations]

    timings, t = [], 0.0
    for d in final_durations:
        timings.append((t, t + d))
        t += d
    return timings


def build_segmented_video(sentences: list[str], boundaries: list[list[int]],
                           audio_dur: float, folder_id: str, last_video_id: str | None,
                           out_path: str, tmp_dir: str):
    """Vraca (out_path, novi_last_video_id)."""
    timings = _segment_time_windows(sentences, boundaries, audio_dur)
    segment_count = len(boundaries)

    videos, _ = gdrive.list_files(folder_id)
    if not videos:
        raise RuntimeError(
            "Nema nijednog klipa u AI klipovi Drive folderu -- prvo treba "
            "generisati/dodati pocetnu seriju klipova."
        )

    picked = gdrive.pick_sequence(videos, last_video_id, segment_count)

    clip_paths = []
    for i, ((start, end), video_item) in enumerate(zip(timings, picked)):
        target_dur = end - start
        raw_clip = os.path.join(tmp_dir, f"edu_raw_{i}.mp4")
        gdrive.download_file(video_item["id"], raw_clip)
        print(f"Segment {i}: {video_item['name']}")

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

    new_last_video_id = picked[-1]["id"]
    return out_path, new_last_video_id
