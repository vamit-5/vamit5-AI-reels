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


def _pick_clip_for_category(category: str, all_videos: list, used_ids: set,
                             last_by_category: dict):
    """Bira sledeci NEKORISCEN (unutar OVOG Reel-a) klip iz DATE kategorije.
    Ako ta kategorija nema (dovoljno) klipova, vraca se na ceo pool kao
    rezervu (bolje ponoviti nego pucanje/prazan segment)."""
    candidates = gdrive.filter_by_category(all_videos, category)
    pool = candidates if candidates else all_videos

    unused = [v for v in pool if v["id"] not in used_ids]
    if unused:
        last_id = last_by_category.get(category)
        ids = [v["id"] for v in unused]
        if last_id in ids:
            start_idx = (ids.index(last_id) + 1) % len(unused)
        else:
            start_idx = 0
        chosen = unused[start_idx]
    else:
        # sva kategorija vec iskoriscena u ovom Reel-u -- ponovi (retko,
        # samo kad je pool jos mali)
        chosen = pool[0]

    used_ids.add(chosen["id"])
    last_by_category[category] = chosen["id"]
    return chosen


def build_segmented_video(sentences: list[str], boundaries: list[list[int]],
                           categories: list[str], audio_dur: float, folder_id: str,
                           last_by_category: dict, out_path: str, tmp_dir: str):
    """Vraca (out_path, azurirani_last_by_category)."""
    timings = _segment_time_windows(sentences, boundaries, audio_dur)

    all_videos, _ = gdrive.list_files(folder_id)
    if not all_videos:
        raise RuntimeError(
            "Nema nijednog klipa u AI klipovi Drive folderu -- prvo treba "
            "generisati/dodati pocetnu seriju klipova."
        )

    used_ids = set()
    picked = []
    for category in categories:
        chosen = _pick_clip_for_category(category, all_videos, used_ids, last_by_category)
        picked.append(chosen)
        print(f"Kategorija '{category}' -> {chosen['name']}")

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

    return out_path, last_by_category
