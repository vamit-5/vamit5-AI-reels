"""
Lock fajl (lock.txt) u repo-u sprecava da GitHub-ov interni cron I
spoljasnji cron-job.org "budilnik" pokrenu objavu dvaput istovremeno.

Trajanje katanca (LOCK_MAX_AGE_MINUTES) mora biti duze od najsporijeg
mogueg pokretanja -- video generisanje + TTS + montaza + IG obrada
ume da potraje 5-15 minuta, zato je ovde 25 min (isto kao u dokazanom
sistemu).
"""
import os
import subprocess
import time

LOCK_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lock.txt")
LOCK_MAX_AGE_MINUTES = 25


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def try_acquire() -> bool:
    if os.path.exists(LOCK_PATH):
        with open(LOCK_PATH, "r") as f:
            try:
                ts = float(f.read().strip())
            except ValueError:
                ts = 0
        age_minutes = (time.time() - ts) / 60
        if age_minutes < LOCK_MAX_AGE_MINUTES:
            return False  # neko drugi drzi katanac, tiho se povlacimo

    with open(LOCK_PATH, "w") as f:
        f.write(str(time.time()))

    _run(["git", "config", "user.name", "vamit5-bot"])
    _run(["git", "config", "user.email", "bot@vamit-5.local"])
    _run(["git", "add", "lock.txt"])
    _run(["git", "commit", "-m", "chore: acquire lock"])

    for attempt in range(5):
        _run(["git", "fetch", "origin", "main"])
        _run(["git", "rebase", "origin/main"])
        push = _run(["git", "push", "origin", "HEAD:main"])
        if push.returncode == 0:
            return True
        time.sleep(3)

    return False  # push nikad nije uspeo -> neko drugi je zauzeo katanac


def release_and_commit(extra_paths: list[str], message: str):
    for attempt in range(5):
        _run(["git", "add", *extra_paths, "lock.txt"])
        _run(["git", "commit", "-m", message])
        _run(["git", "fetch", "origin", "main"])
        _run(["git", "rebase", "origin/main"])
        push = _run(["git", "push", "origin", "HEAD:main"])
        if push.returncode == 0:
            return True
        time.sleep(3)
    return False
