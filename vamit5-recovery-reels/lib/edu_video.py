"""
Za svaki segment (grupu recenica) generise AI video preko Higgsfield-a
(video.generate_episode_video), petlja/sece ga na tacno dodeljeno trajanje,
i spaja SVE segmente u jedan kontinuirani "silent" video fajl koji tacno
pokriva celu duzinu audio naracije.

STROGA ZABRANA DUPLIKATA: posle svakog preuzimanja, proverava se da li je
fajl BIT-PO-BIT identican nekom vec preuzetom klipu U ISTOM VIDEU. Ako
jeste, generise se ponovo (nov nasumican seed) dok ne bude razlicit,
najvise MAX_DEDUP_RETRIES puta.
"""
import hashlib
import json
import os
import subprocess

from lib import video

MIN_SEGMENT_SECONDS = 2.0
MAX_DEDUP_RETRIES = 4


def _ffprobe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _segment_time_windows(sentences: list[str], segments: list[dict], audio_dur: float):
    """Racuna (start, end) sekunde za svaki segment, srazmerno ukupnom broju
    karaktera recenica koje taj segment pokriva."""
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
    seen_hashes = set()
    for i, (seg, (start, end)) in enumerate(zip(segments, timings)):
        target_dur = end - start
        raw_clip = os.path.join(tmp_dir, f"edu_raw_{i}.mp4")

        for retry in range(MAX_DEDUP_RETRIES + 1):
            video.generate_episode_video(
                seg["video_prompt_english"], seg["video_prompt_english"], raw_clip
            )
            file_hash = _file_hash(raw_clip)
            if file_hash not in seen_hashes:
                seen_hashes.add(file_hash)
                break
            print(f"UPOZORENJE: segment {i} identican prethodnom klipu -- "
                  f"generisem ponovo (pokusaj {retry + 1}/{MAX_DEDUP_RETRIES})")
        else:
            print(f"UPOZORENJE: segment {i} i dalje duplikat posle "
                  f"{MAX_DEDUP_RETRIES} pokusaja, nastavljam sa poslednjom verzijom")

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

    # spoji sve segmente redom preko ffmpeg concat demuxer-a
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
