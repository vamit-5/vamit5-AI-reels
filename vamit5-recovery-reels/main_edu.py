"""
Glavni ulazni fajl za EDUKATIVNE (AI anatomija) reels-e. Pokrece ga
GitHub Actions, odvojen raspored od main.py/main_volume.py.

VRACENO na UZIVO Higgsfield generisanje (DoP Standard, bolji kvalitet od
Lite), po izricitom zahtevu -- gotovi Drive klipovi nisu davali dovoljno
preciznu vezu sa sadrzajem. Skripte za ovaj tok dolaze ISKLJUCIVO iz
lib/edu_dop_scripts.py, potpuno odvojeno od ostalih pool-ova.

1. Zauzmi lock (deljen sa ostalim tokovima)
2. Odaberi sledecu skriptu (rotacija u krug, lib/edu_dop_scripts.py)
3. ElevenLabs generise audio (tacan tekst, bez izmena)
4. Claude API deli naraciju na segmente I smislja video prompt za svaki
   (doslovno prati sta se u tom delu prica)
5. Higgsfield DoP Standard generise sliku+video za svaki segment uzivo
6. Svi segmenti se spajaju u jedan kontinuiran silent video tacne duzine
7. Sa Google Drive-a (glavni folder) preuzmi sledecu muziku
8. ffmpeg dodaje caption segmente + muzika (ducked) + logo + CTA mockup
9. Cloudinary hostuje finalni fajl, Instagram Graph API objavljuje
10. Upisuje se novo stanje i lock se otkljucava, sve se commit-uje
"""
import datetime
import os
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import state as state_lib
from lib import theme, tts, gdrive, assemble, edu_content, edu_video, cloudinary_upload, instagram, lock
from lib.edu_dop_scripts import EDU_DOP_SCRIPTS
from lib.assemble import _split_sentences

HASHTAGS = "#vamit5 #kettlebell #trening #disciplina #fitness"


def _in_allowed_window() -> bool:
    windows = os.environ.get("ALLOWED_UTC_HOUR_WINDOWS", "").strip()
    if not windows:
        return True
    current_hour = datetime.datetime.utcnow().hour
    for part in windows.split(","):
        start, end = part.split("-")
        if int(start) <= current_hour < int(end):
            return True
    return False


def main():
    is_manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    if not is_manual and not _in_allowed_window():
        print("Van dozvoljenog vremenskog prozora -- tiho izlazim (bez objave).")
        return

    if not EDU_DOP_SCRIPTS:
        raise RuntimeError(
            "lib/edu_dop_scripts.py je prazan -- prvo dodaj skripte pre pokretanja."
        )

    acquired = lock.try_acquire()
    if not acquired:
        print("Lock zauzet od strane drugog pokretanja -- tiho izlazim.")
        return

    try:
        st = state_lib.load_state()

        episode = theme.select_from_pool(EDU_DOP_SCRIPTS, st.get("next_edu_script_index", 0))
        print(f"Edu skripta #{episode['script_index']}: {episode['hook_serbian'][:60]}...")

        with tempfile.TemporaryDirectory() as tmp:
            audio_path = os.path.join(tmp, "narration.mp3")
            tts.synthesize(episode["narration_serbian"], audio_path)
            audio_dur = assemble._ffprobe_duration(audio_path)

            sentences = _split_sentences(episode["narration_serbian"])
            target_segment_count = edu_content.compute_segment_count(audio_dur)
            segments = edu_content.split_into_segments(sentences, target_segment_count)
            print(f"Podeljeno na {len(segments)} AI video segmenata (DoP Standard)")

            base_video_path = os.path.join(tmp, "edu_base.mp4")
            edu_video.build_segmented_video(sentences, segments, audio_dur, base_video_path, tmp)

            _, audios = gdrive.list_files()
            music_item = None
            if audios:
                music_item = gdrive.pick_next(audios, st.get("last_edu_audio_id"))
                music_raw_path = os.path.join(tmp, "music_raw.mp3")
                gdrive.download_file(music_item["id"], music_raw_path)
                print(f"Muzika: {music_item['name']}")

            final_path = os.path.join(tmp, "final.mp4")
            assemble.finalize(
                base_video_path, audio_path,
                narration_text=episode["narration_serbian"],
                out_path=final_path,
                tmp_dir=tmp,
            )

            public_url = cloudinary_upload.upload_video(final_path)

            full_caption = f"{episode['caption_serbian']}\n\n{HASHTAGS}"
            post_id = instagram.publish_reel(public_url, full_caption)
            print(f"Objavljeno na Instagram, post id: {post_id}")

        st["next_edu_script_index"] = episode["script_index"] + 1
        if music_item:
            st["last_edu_audio_id"] = music_item["id"]
        state_lib.save_state(st)

        lock.release_and_commit(
            [state_lib.STATE_PATH],
            f"chore: objavljena edu skripta #{episode['script_index']} (post {post_id})",
        )

    except Exception:
        traceback.print_exc()
        lock.release_and_commit([], "chore: release lock posle greske")
        sys.exit(1)


if __name__ == "__main__":
    main()
