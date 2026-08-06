"""
Definicije za "volumen" tok (46 reels-a dnevno iz 3 Drive foldera).

Svaki folder ima svoje pravilo za zvuk/tekst:
- MUTE_MUSIC_TEXT ("Ugasi ton"): ugasi original zvuk, dodaj ElevenLabs
  glas + muziku, dodaj caption koji prati govor
- KEEP_TEXT ("Ostavi ton"): zadrzi original zvuk, dodaj kratak statican
  natpis (iz CAPTION_TEXTS, rotira u krug), BEZ muzike/glasa
- MUTE_MUSIC_NOTEXT ("Postavi bez izmena" / "Ne dodavaj tekst..."):
  POTPUNO NETAKNUTO -- original video i original zvuk, BEZ ikakve izmene
  (bez teksta, bez muzike, bez glasa, bez loga)

Tekstovi na snimcima (8 komada) rotiraju se u krug, NEZAVISNO od rotacije
video snimaka.
"""
import os

MODE_MUTE_MUSIC_TEXT = "mute_music_text"
MODE_KEEP_TEXT = "keep_text"
MODE_MUTE_MUSIC_NOTEXT = "mute_music_notext"

# folder_id se cita iz GitHub Secrets (setuj: GDRIVE_FOLDER_MUTE_TEXT,
# GDRIVE_FOLDER_KEEP_TEXT, GDRIVE_FOLDER_MUTE_NOTEXT)
# needs_voice: da li se dodaje ElevenLabs naracija (iz lib/scripts.py pool-a)
# REDOSLED U OVOJ LISTI = REDOSLED ROTACIJE (folder1 -> folder2 -> folder3 ->
# ponovo folder1...). Ime foldera na Google Drive-u moze slobodno da se
# menja -- kod prepoznaje folder po folder_id (ID iz linka), ne po imenu.
FOLDERS = [
    {"key": "mute_text", "folder_id": os.environ.get("GDRIVE_FOLDER_MUTE_TEXT", ""), "mode": MODE_MUTE_MUSIC_TEXT, "needs_voice": True},
    {"key": "keep_text", "folder_id": os.environ.get("GDRIVE_FOLDER_KEEP_TEXT", ""), "mode": MODE_KEEP_TEXT, "needs_voice": False},
    {"key": "mute_notext", "folder_id": os.environ.get("GDRIVE_FOLDER_MUTE_NOTEXT", ""), "mode": MODE_MUTE_MUSIC_NOTEXT, "needs_voice": False},
]

CAPTION_TEXTS = [
    'Komentariši "VAMIT" i dobijaš 7 dana besplatan VAMIT-5 App',
    "Balkanci, ulazite u VAMIT-5 (7 dana besplatno)",
    "Sagori do 800 kalorija za 40 minuta (link u BIO)",
    "Treba ti balkanska motivacija za trening? Zahvali se posle!",
    "Nema ko da te motiviše za trening? Uđi u VAMIT-5!",
    "Za one kojima treba balkanska motivacija u treningu!",
    "Za Balkance koji znaju ko su",
    "Za one kojima treba balkanska zajednica!",
]

FIXED_CTA_BLOCK = (
    "Testiraj VAMIT-5 App 7 dana besplatno. Link u BIO.\n"
    "#joinvamit5\n\n"
    "@vamit5_\n"
    "@vamit5.athletes"
)
