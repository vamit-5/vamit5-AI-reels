"""
Cuva stanje izmedju pokretanja u state.json unutar repo-a (commit-uje se
nazad posle svake uspesne objave, isti princip kao lock.txt).

Prati:
- next_script_index: koja skripta je sledeca na redu (rotacija u krug)
- last_video_id / last_audio_id: poslednji koriscen Drive fajl (da se ne
  ponovi isti dva puta zaredom)
"""
import json
import os

STATE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state.json")


def load_state():
    if not os.path.exists(STATE_PATH):
        return {
            "next_script_index": 0, "last_video_id": None, "last_audio_id": None,
            "next_edu_script_index": 0, "last_edu_audio_id": None,
        }
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("next_script_index", 0)
    data.setdefault("last_video_id", None)
    data.setdefault("last_audio_id", None)
    data.setdefault("next_edu_script_index", 0)
    data.setdefault("last_edu_audio_id", None)
    return data


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
