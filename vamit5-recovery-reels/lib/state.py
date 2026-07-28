"""
Cuva istoriju objavljenih epizoda u state.json unutar repo-a.
Ovo se commit-uje nazad u git posle svake uspesne objave (isti princip
kao lock.txt u postojecoj automatizaciji), da GitHub Actions runneri
(koji nemaju trajnu memoriju izmedju pokretanja) znaju sta je vec
objavljeno i ne ponavljaju iste hookove/uglove.
"""
import json
import os

STATE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state.json")

# Rotirajuci "slotovi" -- svaki vezan za jednu VAMIT-5 fazu ili fizioloski
# mehanizam. Ide se redom pa vrti u krug -- ali svaki krug Claude dobija
# istoriju hookova/uglova koji su vec iskorisceni za taj slot, pa smisli
# NOV hook/ugao umesto da ponovi isti.
TIME_POINTS = [
    "BLOCK faza - kettlebell snaga, kontrola i tehnika",
    "VO2 MAX faza - pluca i mitohondrijalna potraznja pod stresom",
    "PLYO faza - eksplozivnost i brza misicna vlakna",
    "SLOW faza - CNS i mentalna bitka (borba sa glasom u glavi)",
    "PUMP faza - lokalna pumpa, metaboliti, osecaj da misic gori",
    "Vaskularni efekat - zasto VAMIT-5 gradi nove krvne sudove (angiogeneza)",
    "Mitohondrijalni efekat - VAMIT-5 kao 'nadogradnja' celijskih elektrana",
    "365 dana novih izazova - zasto telo nikad ne sme da zna sta sledi",
    "Regeneracija i superkompenzacija izmedju VAMIT-5 treninga",
    "Hormonalni odgovor na VAMIT-5 (testosteron, endorfini, GH)",
    "VAMIT-5 vs obicna teretana/kardio - zasto je drugaciji pristup",
    "Prvi VAMIT-5 trening pocetnika - sta se dogadja u telu prvi put",
]


def load_state():
    if not os.path.exists(STATE_PATH):
        return {"next_index": 0, "history": {}}
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def pick_next_time_point(state):
    idx = state.get("next_index", 0) % len(TIME_POINTS)
    time_point = TIME_POINTS[idx]
    return time_point, idx


def record_episode(state, idx, angle_summary, caption):
    key = str(idx)
    state.setdefault("history", {}).setdefault(key, [])
    state["history"][key].append({
        "angle": angle_summary,
        "caption": caption,
    })
    # cuvamo samo poslednjih 6 uglova po tacki da fajl ne raste beskonacno
    state["history"][key] = state["history"][key][-6:]
    state["next_index"] = (idx + 1) % len(TIME_POINTS)
    return state
