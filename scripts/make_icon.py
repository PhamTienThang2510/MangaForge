"""Vẽ biểu tượng MangaForge (desktop/icon.ico + web/favicon.png). Chạy: uv run --with pillow scripts/make_icon.py"""
import os
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
# nền bo góc chuyển màu xanh -> tím
grad = Image.new("RGBA", (S, S))
px = grad.load()
for y in range(S):
    for x in range(S):
        t = (x + y) / (2 * S)
        px[x, y] = (int(91 + (124 - 91) * t), int(140 + (92 - 140) * t), 255, 255)
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([40, 40, S - 40, S - 40], radius=230, fill=255)
img.paste(grad, (0, 0), mask)
d = ImageDraw.Draw(img)
# bong bóng thoại trắng + chữ M
d.ellipse([170, 190, 854, 750], fill=(255, 255, 255, 255))
d.polygon([(330, 690), (270, 880), (470, 735)], fill=(255, 255, 255, 255))
font = ImageFont.truetype(os.path.join(ROOT, "fonts", "BeVietnamPro-ExtraBold.ttf"), 430)
d.text((512, 470), "M", font=font, fill=(60, 72, 160, 255), anchor="mm")
img.save(os.path.join(ROOT, "desktop", "icon.ico"), sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
img.resize((128, 128), Image.LANCZOS).save(os.path.join(ROOT, "web", "favicon.png"))
img.resize((512, 512), Image.LANCZOS).save(os.path.join(ROOT, "desktop", "icon.png"))
print("ok")
