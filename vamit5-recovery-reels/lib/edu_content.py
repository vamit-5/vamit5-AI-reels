"""
Uzima FIKSNU skriptu (tekst se ne menja, dolazi iz lib/edu_scripts.py) i
preko Claude API-ja je deli na N segmenata (grupe recenica), gde za svaki
segment Claude smislja odgovarajuci AI video prompt (koji deo anatomije/
organa da se prikaze, u skladu sa onim sto se u tom delu izgovara).

Bitno: Claude NE prepisuje/menja sam tekst naracije -- samo bira granice
(indekse recenica) i pise video prompt. Ovo garantuje da izgovoreni tekst
ostaje 100% ono sto je covek napisao.
"""
import json
import os
import urllib.request

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
MODEL = "claude-sonnet-5"

EDU_SEGMENT_COUNT = 5

SYSTEM_PROMPT = """Ti si vizuelni reziser za VAMIT-5 edukativne Instagram Reels
epizode. Dobijas skriptu (vec podeljenu na numerisane recenice) i tvoj JEDINI
posao je da:

1. Podelis te recenice u TACNO {segment_count} uzastopnih grupa (segmenata) --
   svaka recenica mora pripadati tacno jednom segmentu, bez preskakanja i bez
   preklapanja, pokrivajuci SVE recenice od prve do poslednje.
2. Za svaki segment napises video_prompt_english -- opis AI generisane scene
   koja vizuelno prati SADRZAJ tog dela teksta.

STIL SCENE (koristi dosledno u svakom promptu): muskularan, atletski gradjen
covek u tamnom VAMIT-5 trening studiju (dark gym studio background, military
green accent lighting, cinematic), sa X-ray/transparent-skin bioloskim
overlay efektom koji pokazuje TACNO ono o cemu se u tom delu teksta govori:
- ako se pominje srce/puls/kardio -> prikazi srce kako kuca, krvotok
- ako se pominje umor/misici/snaga -> prikazi misicna vlakna, kontrakcije
- ako se pominje mozak/CNS/odluka/disciplina -> prikazi nervne signale,
  mozak/CNS putanje
- ako se pominje energija/mitohondrije/izdrzljivost -> prikazi mitohondrije
  kao sitne svetlece cestice u celijama
- ako tekst NE pominje nista telesno konkretno (npr. opsti uvod, prica o
  svakodnevnom zivotu) -> prikazi atletu u pokretu (npr. hoda ka teretani,
  stoji zamisljen, kettlebell u ruci) i dalje u VAMIT-5 studio stilu, bez
  X-ray efekta ako nema jasnog telesnog fokusa

Vrati ISKLJUCIVO validan JSON (bez markdown ograda), u formatu:
{{"segments": [{{"start": 0, "end": 2, "video_prompt_english": "..."}}, ...]}}
gde su "start" i "end" INDEKSI recenica (0-indeksirano, end je INKLUZIVNO),
tacno {segment_count} segmenata, bez rupa i bez preklapanja.
"""


def _anthropic_call(user_content: str) -> str:
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 2000,
        "system": SYSTEM_PROMPT.format(segment_count=EDU_SEGMENT_COUNT),
        "messages": [{"role": "user", "content": user_content}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "content-type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return "".join(b["text"] for b in data["content"] if b.get("type") == "text")


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1:
        raw = raw[start:end + 1]
    return json.loads(raw)


def _fallback_equal_split(num_sentences: int) -> list[dict]:
    """Ako Claude ne vrati validnu podelu, napravi prostu ravnomernu podelu
    umesto da ceo workflow pukne."""
    n = min(EDU_SEGMENT_COUNT, num_sentences) or 1
    base = num_sentences // n
    remainder = num_sentences % n
    segments, idx = [], 0
    for i in range(n):
        size = base + (1 if i < remainder else 0)
        if size == 0:
            continue
        segments.append({
            "start": idx,
            "end": idx + size - 1,
            "video_prompt_english": (
                "Muscular athletic man in a dark VAMIT-5 training studio, "
                "military green cinematic lighting, kettlebell training pose, "
                "X-ray biological overlay showing glowing muscle fibers"
            ),
        })
        idx += size
    return segments


def _validate_segments(segments: list[dict], num_sentences: int) -> bool:
    if not segments:
        return False
    covered = sorted((s["start"], s["end"]) for s in segments)
    expected_start = 0
    for start, end in covered:
        if start != expected_start or end < start:
            return False
        expected_start = end + 1
    return expected_start == num_sentences


def split_into_segments(sentences: list[str]) -> list[dict]:
    numbered = "\n".join(f"{i}: {s}" for i, s in enumerate(sentences))
    user_content = f"Skripta (recenice numerisane):\n{numbered}\n\nPodeli je i napravi video promptove."

    for attempt in range(3):
        try:
            raw = _anthropic_call(user_content)
            data = _parse_json(raw)
            segments = data.get("segments", [])
            if _validate_segments(segments, len(sentences)):
                return segments
        except (json.JSONDecodeError, KeyError, TypeError):
            continue

    return _fallback_equal_split(len(sentences))
