import pandas as pd
from pathlib import Path
from utils import load_phrases

OUT = Path("listings"); OUT.mkdir(parents=True, exist_ok=True)

PRODUCTS = [
    ("mug",   "white", "Coffee Mug"),
    ("mug",   "black", "Coffee Mug"),
    ("sign",  "white", "Wooden Sign"),
    ("sign",  "black", "Wooden Sign"),
    ("shirt", "white", "Pocket T-Shirt"),
    ("shirt", "black", "Pocket T-Shirt"),
]

DESC = {
    "mug":   "Add a touch of wit to your day with our coffee mug. Featuring the phrase '{p}', this makes a thoughtful gift for anyone who appreciates humor. Printed on demand.",
    "sign":  "Minimalist wooden sign featuring '{p}'. Perfect for home or office decor. Clean black-and-white aesthetic. Printed on demand.",
    "shirt": "Subtle pocket tee with '{p}'. Soft, everyday fit with minimalist text. Printed on demand.",
}

def build_tags(prod, colour, phrase):
    base = {
        "mug": ["mug","coffee","cup"],
        "sign":["sign","wooden","home decor","desk"],
        "shirt":["tshirt","shirt","pocket","casual"],
    }[prod]
    extra = ["minimalist","typography","black and white","funny","gift","humor", colour]
    words = [w.lower().strip("'\"") for w in phrase.split()]
    return ", ".join(base + extra + words)

def main():
    phrases = load_phrases("phrases.txt")
    rows = []
    for phrase in phrases:
        for prod, colour, nicename in PRODUCTS:
            title = f'{nicename} – "{phrase}" ({ "Black Text, White Background" if colour=="white" else "White Text, Black Background"})'
            rows.append({
                "phrase": phrase,
                "product_type": prod,
                "colour": colour,
                "title": title,
                "description": DESC[prod].format(p=phrase),
                "tags": build_tags(prod, colour, phrase)
            })
    import pandas as pd
    df = pd.DataFrame(rows)
    out_path = OUT / "listings.csv"
    df.to_csv(out_path, index=False)
    print(f"Wrote {len(df)} listing rows to {out_path.resolve()}")

if __name__ == "__main__":
    main()
