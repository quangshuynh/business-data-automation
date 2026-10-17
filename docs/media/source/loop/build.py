"""Build docs/media/ordixa-loop.gif from loop.html.

    python docs/media/source/loop/build.py [--out PATH]

Needs Python with Playwright (Chromium installed), numpy, Pillow, and ffmpeg
on PATH. Renders every frame of loop.html in headless Chromium, refuses to
encode if any table text overflows its cell, then makes a two-pass palette GIF.
"""

import argparse
import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from assets import make_assets  # noqa: E402

FRAMES = HERE / "frames"
FPS, DUR = 20, 7.5


async def render():
    shutil.rmtree(FRAMES, ignore_errors=True)
    FRAMES.mkdir()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 960, "height": 540})
        await page.goto((HERE / "loop.html").as_uri())
        await page.evaluate("window.ready")
        await page.wait_for_timeout(300)
        for t in (0.0, 4.0):  # before and after states
            await page.evaluate(f"render({t})")
            problems = await page.evaluate("audit()")
            if problems:
                sys.exit(f"layout audit failed at t={t}: {problems}")
        for i in range(int(FPS * DUR)):
            await page.evaluate(f"render({i / FPS})")
            await page.screenshot(path=str(FRAMES / f"f{i:04d}.png"))
        await browser.close()


def ffmpeg(*args):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True
    )


def encode(out):
    src = ["-framerate", str(FPS), "-i", str(FRAMES / "f%04d.png")]
    palette = HERE / "palette.png"
    ffmpeg(*src, "-vf", "palettegen=max_colors=160:stats_mode=full", str(palette))
    ffmpeg(
        *src,
        "-i",
        str(palette),
        "-lavfi",
        "paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle",
        "-loop",
        "0",
        str(out),
    )


def report(out):
    im = Image.open(out)
    frames, ms = 0, 0
    size, loop = im.size, im.info.get("loop")
    try:
        while True:
            ms += im.info["duration"]
            frames += 1
            im.seek(im.tell() + 1)
    except EOFError:
        pass
    print(
        f"{out}: {size[0]}x{size[1]}, {frames} frames, {ms / 1000:.2f} s, "
        f"{frames / (ms / 1000):.1f} fps, loop={loop}, "
        f"{out.stat().st_size / 1024:.0f} KB"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=HERE.parents[1] / "ordixa-loop.gif")
    out = parser.parse_args().out.resolve()
    make_assets(HERE, ["ordixa-wordmark-dark.png"])
    asyncio.run(render())
    encode(out)
    report(out)
