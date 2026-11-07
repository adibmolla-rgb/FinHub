"""Reads the tone of financial headlines with finBERT. One job per process: JSON in on stdin, JSON out on stdout.

The code here and the libraries are permissively licensed. The model weights are CC BY-NC-SA 4.0, so they are
downloaded to this computer on first use, never shipped with FinHub, and are for non-commercial use.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

MODEL = "ProsusAI/finbert"
REVISION = "0bc2ac10dda6929bcb1f77ccc43c7ec5c424f031"  # pinned, so the first download is always the same model


def mood(request: dict) -> dict:
    from transformers import pipeline

    headlines = request["headlines"]
    if not headlines:
        return {"rows": []}
    classify = pipeline("text-classification", model=MODEL, revision=REVISION, top_k=None, device=-1)
    rows = []
    for headline, scores in zip(headlines, classify(headlines, truncation=True, batch_size=8)):
        by_label = {s["label"]: float(s["score"]) for s in scores}
        rows.append({"headline": headline, "label": max(by_label, key=by_label.get), **{k: by_label.get(k) for k in ("positive", "neutral", "negative")}})
    return {"rows": rows, "model": MODEL}


TASKS = {"mood": mood}


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from job_runner import run

    raise SystemExit(run(TASKS, "finBERT"))
