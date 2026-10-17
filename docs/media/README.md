# Launch media

Release media for Ordixa 2.0.0, rendered from the HTML sources in `source/`.
All data shown is the fictional example data in
[`examples/ordixa`](../../examples/ordixa/README.md).

| File | What it is |
| --- | --- |
| `ordixa-loop.gif` | README loop: 960×540, 7.5 s, 20 fps, about 830 KB |
| `thumbnail.jpg` | Poster frame of the launch video, 1920×1080 |
| `launch.mp4` | 23 s launch video: 1920×1080, 30 fps, H.264 + AAC, faststart, 6.9 MB. Not committed (over the 5 MB tracked-file limit); attach it to the GitHub release |
| `source/loop/` | `loop.html` and `build.py` for the GIF |
| `source/launch/` | `video.html`, `audio.py` (synthesized soundtrack), and `build.py` for the video |
| `source/assets.py` | Derives the cropped and reversed logos from [`docs/images`](../images) at build time |

## Rebuilding

From the repository root, with Python that has Playwright (and its Chromium),
numpy, and Pillow, and with `ffmpeg` on `PATH`:

```bash
python docs/media/source/loop/build.py      # writes docs/media/ordixa-loop.gif
python docs/media/source/launch/build.py    # writes launch.mp4 and thumbnail.jpg
```

Both renders are deterministic: with the same fonts (Segoe UI, Calibri, and
Consolas, as on Windows) they reproduce these files byte for byte. Frames,
palettes, the soundtrack, and the derived logos are written next to each
source and are git-ignored. The GIF build stops if any table text would
overflow its cell.

## Source of the numbers

The GIF shows rows of `inventory-after.csv` and what `clean` did with them.
The totals (124 rows read, 119 written, 5 held back) come from:

```bash
python -m app.ordixa clean --profile examples/ordixa/profiles/inventory-clean.toml \
  --input examples/ordixa/exports/inventory/inventory-after.csv --out output/inventory-clean
```
