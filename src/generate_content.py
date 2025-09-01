from pathlib import Path
from utils import load_phrases

OUT = Path("content"); OUT.mkdir(parents=True, exist_ok=True)

IDEAS = [
    ("When your day is chaotic but your coffee keeps you grounded.",
     "Pour a fresh cup into the mug that reads '{p}'. Chaos around you, slow sip, end on close-up of the mug."),
    ("Hang this where everyone can see it.",
     "Place the wooden sign with '{p}' on a wall/desk. Quick cuts of moments it 'saves the day'. Close-up end."),
    ("Subtle on the outside, savage on the pocket.",
     "Wear the pocket tee with '{p}'. POV: point to pocket whenever someone annoys you. Wink outro."),
]

def main():
    phrases = load_phrases("phrases.txt")
    lines = []
    for i, p in enumerate(phrases, 1):
        lines.append(f"Phrase {i}: {p}\n")
        for j, (cap, script) in enumerate(IDEAS, 1):
            lines.append(f"Idea {j}:\nCaption: {cap}\nScript: {script.format(p=p)}\n\n")
        lines.append("\n")
    out = OUT / "content.txt"
    out.write_text("".join(lines), encoding="utf-8")
    print(f"Wrote content ideas for {len(phrases)} phrase(s) to {out.resolve()}")

if __name__ == "__main__":
    main()
