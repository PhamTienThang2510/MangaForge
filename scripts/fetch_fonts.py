"""Tải font đi kèm MangaForge từ kho chính thức google/fonts (SIL Open Font License 1.1).

  uv run --with fonttools --with requests scripts/fetch_fonts.py

- Font tĩnh: tải nguyên file.
- Font variable: dựng bản tĩnh ở độ đậm mong muốn bằng fontTools.varLib.instancer (OFL cho phép;
  Pillow chỉ vẽ được kiểu mặc định của font variable nên cần bản tĩnh).
- Mỗi họ font kèm file OFL.txt trong fonts/licenses/.
"""
import io
import os
import sys

import requests

RAW = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")
LIC = os.path.join(OUT, "licenses")

STATIC = {  # tên file xuất ra : (thư mục họ font, file trong kho)
    "BeVietnamPro-Bold.ttf": ("bevietnampro", "BeVietnamPro-Bold.ttf"),
    "BeVietnamPro-ExtraBold.ttf": ("bevietnampro", "BeVietnamPro-ExtraBold.ttf"),
    "Bangers-Regular.ttf": ("bangers", "Bangers-Regular.ttf"),
    "PatrickHand-Regular.ttf": ("patrickhand", "PatrickHand-Regular.ttf"),
    "Pangolin-Regular.ttf": ("pangolin", "Pangolin-Regular.ttf"),
    "Mansalva-Regular.ttf": ("mansalva", "Mansalva-Regular.ttf"),
    "FuzzyBubbles-Regular.ttf": ("fuzzybubbles", "FuzzyBubbles-Regular.ttf"),
    "FuzzyBubbles-Bold.ttf": ("fuzzybubbles", "FuzzyBubbles-Bold.ttf"),
    "DelaGothicOne-Regular.ttf": ("delagothicone", "DelaGothicOne-Regular.ttf"),
    "Bungee-Regular.ttf": ("bungee", "Bungee-Regular.ttf"),
    "VinaSans-Regular.ttf": ("vinasans", "VinaSans-Regular.ttf"),
    "BlackOpsOne-Regular.ttf": ("blackopsone", "BlackOpsOne-Regular.ttf"),
    "SigmarOne-Regular.ttf": ("sigmarone", "SigmarOne-Regular.ttf"),
    "CherryBombOne-Regular.ttf": ("cherrybombone", "CherryBombOne-Regular.ttf"),
}
VARIABLE = {  # tên file xuất ra : (thư mục, file variable, toạ độ trục)
    "PlaypenSans-Bold.ttf": ("playpensans", "PlaypenSans[wght].ttf", {"wght": 700}),
    "ShantellSans-Bold.ttf": ("shantellsans", "ShantellSans[BNCE,INFM,SPAC,wght].ttf",
                              {"wght": 700, "BNCE": 0, "INFM": 0, "SPAC": 0}),
    "ShantellSans-Bouncy.ttf": ("shantellsans", "ShantellSans[BNCE,INFM,SPAC,wght].ttf",
                                {"wght": 700, "BNCE": 50, "INFM": 50, "SPAC": 0}),
    "Baloo2-ExtraBold.ttf": ("baloo2", "Baloo2[wght].ttf", {"wght": 800}),
}


def get(url):
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content


def main():
    os.makedirs(LIC, exist_ok=True)
    families, bad = set(), []
    for out, (fam, fn) in STATIC.items():
        try:
            open(os.path.join(OUT, out), "wb").write(get(RAW + f"{fam}/{fn}"))
            families.add(fam)
            print("  ✓", out)
        except Exception as e:
            bad.append(f"{out}: {e}")
    try:
        from fontTools.ttLib import TTFont
        from fontTools.varLib import instancer
    except ImportError:
        print("Thiếu fontTools -> bỏ qua font variable (chạy kèm --with fonttools)")
        VARIABLE.clear()
    for out, (fam, fn, axes) in VARIABLE.items():
        try:
            vf = TTFont(io.BytesIO(get(RAW + f"{fam}/{fn.replace('[', '%5B').replace(']', '%5D')}")))
            have = {a.axisTag for a in vf["fvar"].axes}
            inst = instancer.instantiateVariableFont(vf, {k: v for k, v in axes.items() if k in have})
            inst.save(os.path.join(OUT, out))
            families.add(fam)
            print("  ✓", out, "(dựng từ font variable)")
        except Exception as e:
            bad.append(f"{out}: {e}")
    for fam in sorted(families):
        try:
            open(os.path.join(LIC, f"OFL-{fam}.txt"), "wb").write(get(RAW + f"{fam}/OFL.txt"))
        except Exception as e:
            bad.append(f"license {fam}: {e}")
    print(f"Xong: {len(families)} họ font ->", OUT)
    if bad:
        print("LỖI:\n  " + "\n  ".join(bad))
        sys.exit(1)


if __name__ == "__main__":
    main()
