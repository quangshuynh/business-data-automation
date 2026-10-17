"""Build docs/media/launch.mp4 and docs/media/thumbnail.jpg from video.html.

    python docs/media/source/launch/build.py [--out-dir DIR]

Needs Python with Playwright (Chromium installed), numpy, Pillow, and ffmpeg
on PATH. Renders 690 frames (23 s at 30 fps), synthesizes the soundtrack with
audio.py, uses the frame at 13.6 s as the poster (thumbnail.jpg and frame 0, so
it is the idle thumbnail everywhere), and encodes H.264 + AAC with faststart.
"""

import argparse
import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from assets import make_assets  # noqa: E402

FRAMES = HERE / "frames"
FPS, DUR = 30, 23.0
POSTER = 408  # 13.6 s: the AFTER table of the clean-and-validate scene


async def render():
    shutil.rmtree(FRAMES, ignore_errors=True)
    FRAMES.mkdir()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.goto((HERE / "video.html").as_uri())
        await page.evaluate("window.ready")
        await page.wait_for_timeout(300)
        for i in range(round(FPS * DUR)):
            await page.evaluate(f"render({i / FPS})")
            await page.screenshot(path=str(FRAMES / f"f{i:05d}.png"))
        await browser.close()


def ffmpeg(*args):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, default=HERE.parents[1])
    out_dir = parser.parse_args().out_dir.resolve()
    make_assets(HERE, ["ordixa-icon.png", "ordixa-wordmark.png"])
    asyncio.run(render())
    subprocess.run([sys.executable, "audio.py"], cwd=HERE, check=True)
    poster = FRAMES / f"f{POSTER:05d}.png"
    ffmpeg("-i", str(poster), "-q:v", "2", str(out_dir / "thumbnail.jpg"))
    shutil.copyfile(poster, FRAMES / "f00000.png")
    ffmpeg(
        *("-framerate", str(FPS), "-i", str(FRAMES / "f%05d.png")),
        *("-i", str(HERE / "soundtrack.wav")),
        *("-af", "loudnorm=I=-16:TP=-1.5:LRA=11"),
        *("-c:v", "libx264", "-preset", "slow", "-crf", "17"),
        *("-pix_fmt", "yuv420p", "-profile:v", "high"),
        *("-c:a", "aac", "-b:a", "192k", "-ar", "48000"),
        *("-movflags", "+faststart", "-shortest"),
        str(out_dir / "launch.mp4"),
    )
    print(f"wrote {out_dir / 'launch.mp4'} and {out_dir / 'thumbnail.jpg'}")
