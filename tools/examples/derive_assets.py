"""Derive input variants from the generated assets: masked RGBA images (transparent = inpaint area, like ComfyUI's
mask editor saves them) and low-resolution copies for the upscalers.

  L:/ComfyUI/.venv/Scripts/python.exe tools/examples/derive_assets.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ASSETS = Path("L:/ComfyUI/tmp/examples-v131/assets")


def masked(src: str, dst: str, shapes: list, subtract: list = (), feather: int = 6) -> None:
    im = Image.open(ASSETS / src).convert("RGBA")
    mask = Image.new("L", im.size, 0)
    d = ImageDraw.Draw(mask)
    for kind, pts in shapes:
        (d.ellipse if kind == "ellipse" else d.polygon if kind == "poly" else d.rectangle)(pts, fill=255)
    for kind, pts in subtract:
        (d.ellipse if kind == "ellipse" else d.polygon if kind == "poly" else d.rectangle)(pts, fill=0)
    if feather:
        mask = mask.filter(ImageFilter.GaussianBlur(feather))
    alpha = Image.eval(mask, lambda v: 255 - v)
    im.putalpha(alpha)
    im.save(ASSETS / dst)
    print("wrote", dst)


def hair_mask(src: str, dst: str) -> None:
    """Hair only, from colour: saturated red-brown against the neutral grey studio background, minus face and neck.

    A shape mask (an arch around the head) also covered background; the inpainted background came out lighter and
    the arch stayed visible in the result."""
    import numpy as np

    im = Image.open(ASSETS / src).convert("RGBA")
    hsv = np.asarray(im.convert("RGB").convert("HSV")).astype(np.float32)
    hue, sat, val = hsv[..., 0] * 360 / 255, hsv[..., 1] / 255, hsv[..., 2] / 255
    yy, xx = np.mgrid[0:hsv.shape[0], 0:hsv.shape[1]]
    hair = ((hue < 40) | (hue > 340)) & (sat > 0.38) & (val < 0.80)
    face = ((xx - 522) / 128) ** 2 + ((yy - 355) / 175) ** 2 < 1
    neck = (xx > 440) & (xx < 600) & (yy > 480) & (yy < 640)
    mask = Image.fromarray(((hair & ~face & ~neck & (yy < 720)) * 255).astype(np.uint8))
    mask = mask.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(7)).filter(ImageFilter.MaxFilter(7))
    mask = mask.filter(ImageFilter.GaussianBlur(4))
    im.putalpha(Image.eval(mask, lambda v: 255 - v))
    im.save(ASSETS / dst)
    print("wrote", dst)


def smaller(src: str, dst: str, size: int) -> None:
    im = Image.open(ASSETS / src).convert("RGB")
    im.thumbnail((size, size), Image.LANCZOS)
    im.save(ASSETS / dst)
    print("wrote", dst, im.size)


def main() -> None:
    pw = "portrait_woman.png"
    if (ASSETS / pw).exists():
        masked(pw, "portrait_woman_mask_neck.png", [("ellipse", (405, 525, 625, 690))])
        masked(pw, "portrait_woman_mask_eyes.png", [("ellipse", (380, 245, 665, 370))])
        hair_mask(pw, "portrait_woman_mask_hair.png")
        masked(pw, "portrait_woman_mask_sweater.png",
               [("poly", [(170, 650), (300, 610), (430, 612), (512, 640), (600, 612), (740, 600), (880, 650),
                          (940, 1024), (90, 1024)])])
        smaller(pw, "portrait_woman_256.png", 256)
    if (ASSETS / "dog_photo.png").exists():
        smaller("dog_photo.png", "dog_photo_512.png", 512)
    if (ASSETS / "podcast_two.png").exists():
        # woman on the left, man on the right (ComfyUI: transparent = mask)
        masked("podcast_two.png", "podcast_two_mask_left.png", [("ellipse", (120, 40, 640, 768))], feather=12)
        masked("podcast_two.png", "podcast_two_mask_right.png", [("ellipse", (704, 40, 1224, 768))], feather=12)
    song = ASSETS / "song_pop.mp3"
    if song.exists():
        import subprocess
        ffmpeg = "L:/ComfyUI/.venv/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe"
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-ss", "8", "-t", "8", "-i", str(song), "-c:a", "libmp3lame",
                        "-b:a", "192k", str(ASSETS / "song_pop_excerpt.mp3")], check=True)
        print("wrote song_pop_excerpt.mp3 (8 s from 0:08)")
    import glob
    robot = sorted(glob.glob("L:/ComfyUI/tmp/examples-v131/runs/Text_to_Image_ZImage_turbo-Text-to-Image/robot-1024x1024/*.png"))
    robot = [r for r in robot if not r.endswith("workflow.png")]
    if robot:
        import shutil
        shutil.copy2(robot[0], ASSETS / "zimage_robot_with_metadata.png")
        print("wrote zimage_robot_with_metadata.png")
    if (ASSETS / "living_room.png").exists():
        # the potted fiddle-leaf fig in front of the wall (clean background behind it for LaMa)
        masked("living_room.png", "living_room_mask_plant.png", [("rect", (425, 312, 598, 648))], feather=8)

if __name__ == "__main__":
    main()
