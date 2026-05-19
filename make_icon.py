"""Generate the app/exe icon (icon.ico + icon.png).

Run once: ``python make_icon.py``. The icon is a modern red rounded-tile with
two compression chevrons squeezing a "PDF" wordmark -- i.e. "compress a PDF".
"""

from PIL import Image, ImageDraw, ImageFont

S = 1024
TOP = (255, 96, 82)      # light red (top-left)
BOTTOM = (193, 35, 24)   # deep red (bottom-right)
WHITE = (255, 255, 255, 255)
SHADOW = (120, 12, 6, 90)


def _font(size):
    for name in ("seguibl.ttf", "segoeuib.ttf", "arialbd.ttf", "Arialbd.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def build():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # diagonal red gradient
    grad = Image.new("RGB", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / (S - 1)
        row = tuple(int(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3))
        gd.line([(0, y), (S, y)], fill=row)

    # rounded-square tile mask
    margin, radius = 56, 210
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [margin, margin, S - margin, S - margin], radius=radius, fill=255)
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    cx = S // 2

    # two chevrons squeezing inward (compression)
    w, ch, thick = 320, 132, 66
    d.line([(cx - w / 2, 252), (cx, 252 + ch), (cx + w / 2, 252)],
           fill=WHITE, width=thick, joint="curve")
    d.line([(cx - w / 2, S - 252), (cx, S - 252 - ch), (cx + w / 2, S - 252)],
           fill=WHITE, width=thick, joint="curve")

    # "PDF" wordmark in the middle
    font = _font(186)
    d.text((cx + 5, cx + 8), "PDF", font=font, fill=SHADOW, anchor="mm")
    d.text((cx, cx), "PDF", font=font, fill=WHITE, anchor="mm")

    img.save("icon.png")
    img.save("icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                                (64, 64), (128, 128), (256, 256)])
    print("Wrote icon.ico and icon.png")


if __name__ == "__main__":
    build()
