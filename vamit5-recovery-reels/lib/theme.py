"""
Bira sledecu gotovu skriptu (rotacija u krug) i iz nje izvlaci:
- hook_text: prva recenica skripte (ono sto se prvo izgovara, ispisano i
  na ekranu kao caption -- gledalac cita isto sto i cuje)
- caption_serbian: prve 1-2 recenice skripte + fiksni CTA/mentions blok

Nema vise AI generisanja teksta -- tekst je unapred napisan (lib/scripts.py),
ovo samo pakuje taj tekst u strukturu koju main.py koristi.
"""
import re

from lib.scripts import SCRIPTS

FIXED_CTA_BLOCK = (
    "\n\n@vamit5_ @vamit5.athletes\n"
    "Testiraj VAMIT-5 App 7 dana besplatno. Link u BIO.\n"
    "#joinvamit5"
)

MAX_HOOK_WORDS = 14


def _first_sentence(text: str) -> str:
    match = re.search(r"[^.!?]+[.!?]", text)
    sentence = match.group(0).strip() if match else text.strip()
    words = sentence.split()
    if len(words) > MAX_HOOK_WORDS:
        sentence = " ".join(words[:MAX_HOOK_WORDS]) + "..."
    return sentence


def _first_two_sentences(text: str) -> str:
    matches = re.findall(r"[^.!?]+[.!?]", text)
    return " ".join(m.strip() for m in matches[:2]) if matches else text.strip()


def select_from_pool(scripts_pool: list, index: int) -> dict:
    idx = index % len(scripts_pool)
    narration = scripts_pool[idx]

    hook = _first_sentence(narration)
    caption_intro = _first_two_sentences(narration)
    caption = f"{caption_intro}{FIXED_CTA_BLOCK}"

    return {
        "script_index": idx,
        "narration_serbian": narration,
        "hook_serbian": hook,
        "caption_serbian": caption,
    }


def select_episode(state: dict) -> dict:
    return select_from_pool(SCRIPTS, state.get("next_script_index", 0))
