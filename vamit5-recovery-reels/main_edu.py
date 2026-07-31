"""
Glavni ulazni fajl za EDUKATIVNE (AI anatomija) reels-e. Pokrece ga
GitHub Actions, odvojen raspored od main.py (obicni Drive reels-i).

Tok:
1. Pokusaj da zauzmes lock -- ako neko drugi vec radi (bilo koji od dva
   pipeline-a), tiho izadji (isti lock.txt se deli izmedju oba)
2. Odaberi sledecu edukativnu skriptu (rotacija u krug, odvojena od
   obicnih skripti)
3. ElevenLabs generise audio (tacan tekst, bez izmena)
4. Claude API deli naraciju na segmente i smislja AI video prompt za svaki
5. Higgsfield generise po jedan kratak video za svaki segment (slika+animacija)
6. Svi segmenti se spajaju u jedan kontinuiran silent video tacne duzine
7. Sa Google Drive-a preuzmi sledecu muziku (odvojena rotacija od obicnih)
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
from lib.edu_scripts import EDU_SCRIPTS
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

    acquired = lock.try_acquire()
    if not acquired:
        print("Lock zauzet od strane drugog pokretanja -- tiho izlazim.")
        return

    try:
        st = state_lib.load_state()

        episode = theme.select_from_pool(EDU_SCRIPTS, st.get("next_edu_script_index", 0))
        print(f"Edu skripta #{episode['script_index']}: {episode['hook_serbian'][:60]}...")

        with tempfile.TemporaryDirectory() as tmp:
            audio_path = os.path.join(tmp, "narration.mp3")
            tts.synthesize(episode["narration_serbian"], audio_path)
            audio_dur = assemble._ffprobe_duration(audio_path)

            sentences = _split_sentences(episode["narration_serbian"])
            segments = edu_content.split_into_segments(sentences)
            print(f"Podeljeno na {len(segments)} AI video segmenata")

            base_video_path = os.path.join(tmp, "edu_base.mp4")
            edu_video.build_segmented_video(sentences, segments, audio_dur, base_video_path, tmp)

            videos, audios = gdrive.list_files()
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
