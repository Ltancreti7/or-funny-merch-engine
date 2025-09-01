from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from textwrap import wrap
from utils import load_phrases, slugify

OUT = Path("mockups")
OUT.mkdir(parents=True, exist_ok=True)

def draw_box(text: str, w: int, h: int, fg: str, bg: str, pad=40):
    img = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(img)
    font_size = max(20, int(h * 0.10))
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", font_size)
    except:
        font = ImageFont.load_default()
    lines = []
    for chunk in text.split("\n"):
        guess = max(10, int(len(chunk) * (font_size / 14)))
        for line in wrap(chunk, width=guess):
            lines.append(line)
    dummy = ImageDraw.Draw(Image.new("RGB", (w, h)))
    sizes = [dummy.textbbox((0,0), ln, font=font) for ln in lines]
    tw = max((bx[2]-bx[0]) for bx in sizes) if sizes else 0
    th = sum((bx[3]-bx[1]) for bx in sizes) + (len(lines)-1)*6
    x = (w - tw)//2
    y = (h - th)//2
    for ln in lines:
        bbox = draw.textbbox((0,0), ln, font=font)
        lh = bbox[3]-bbox[1]
        draw.text((x, y), ln, fill=fg, font=font)
        y += lh + 6
    return img

def save_pair(phrase: str, base_name: str, w: int, h: int):
    slug = slugify(phrase)
    draw_box(phrase, w, h, fg="black", bg="white").save(OUT / f"{base_name}_white_{slug}.png")
    draw_box(phrase, w, h, fg="white", bg="black").save(OUT / f"{base_name}_black_{slug}.png")

def main():
    phrases = load_phrases("phrases.txt")
    if not phrases:
        print("No phrases found in phrases.txt"); return
    for p in phrases:
        save_pair(p, "mug",   1200, 1200)  # square
        save_pair(p, "sign",  1800, 600)   # wide
        save_pair(p, "shirt", 1200, 1600)  # portrait
    print(f"Generated mock-ups for {len(phrases)} phrase(s) in {OUT.resolve()}")

if __name__ == "__main__":
    main()
