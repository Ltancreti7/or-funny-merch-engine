from __future__ import annotations
import os, re
from typing import List

def load_phrases(path: str) -> List[str]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()]

def slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^\w\s-]+", "", s)
    s = re.sub(r"\s+", "_", s).strip("_")
    return s
