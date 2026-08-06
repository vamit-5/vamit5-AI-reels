"""
Glavni ulazni fajl za EDUKATIVNE (AI anatomija) reels-e. Pokrece ga
GitHub Actions, odvojen raspored od main.py/main_volume.py.

NOVA VERZIJA (bez uzivo Higgsfield API poziva):
1. Zauzmi lock (deljen sa ostalim tokovima)
2. Odaberi sledecu edukativnu skriptu (rotacija u krug)
3. ElevenLabs generise audio (tacan tekst, bez izmena)
4. Claude API SAMO deli naraciju na segmente (koliko treba, na osnovu
   duzine audija) -- vise NE generise video promptove
5. Za svaki segment, BIRA gotov klip iz Drive "AI klipovi" foldera
   (unapred napravljeni preko pravog higgsfield.ai sajta), bez ponavljanja
   klipova UNUTAR ovog istog Reel-a
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
from lib.edu_scripts import EDU_SCRIPTS
from lib.assemble import _split_sentences

HASHTAGS = "#vamit5 #kettlebell #trening #disciplina #fitness"
AI_CLIPS_FOLDER_ID = os.environ.get("GDRIVE_FOLDER_AI_CLIPS", "")


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

    if not AI_CLIPS_FOLDER_ID:
        raise RuntimeError(
            "GDRIVE_FOLDER_AI_CLIPS nije podesen -- prvo napravi Drive folder "
            "za gotove AI klipove, podeli ga sa service account-om i dodaj "
            "GitHub secret."
        )

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
            target_segment_count = edu_content.compute_segment_count(audio_dur)
            boundaries = edu_content.get_segment_boundaries(sentences, target_segment_count)
            print(f"Podeljeno na {len(boundaries)} segmenata (klipovi iz Drive pool-a)")

            base_video_path = os.path.join(tmp, "edu_base.mp4")
            _, new_last_video_id = edu_video.build_segmented_video(
                sentences, boundaries, audio_dur,
                AI_CLIPS_FOLDER_ID, st.get("last_edu_video_id"),
                base_video_path, tmp,
            )

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
        st["last_edu_video_id"] = new_last_video_id
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
