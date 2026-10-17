"""Derive the logo images the animations use from docs/images.

The cropped and reversed logos are generated, not committed: each build calls
make_assets() and the outputs are git-ignored.
"""

from pathlib import Path

import numpy as np
from PIL import Image

IMAGES = Path(__file__).resolve().parents[2] / "images"


def _crop(im):
    """crops an RGBA image to its opaque pixels (alpha above half)"""
    mask = im.getchannel("A").point(lambda v: 255 if v > 128 else 0)
    return im.crop(mask.getbbox())


def _reversed(im):
    """recolors the dark parts of a logo to off-white for a navy background"""
    a = np.array(im.convert("RGBA")).astype(float)
    rgb = a[:, :, :3]
    k = np.clip((110 - rgb.mean(2)) / 40, 0, 1)[..., None]
    a[:, :, :3] = rgb * (1 - k) + np.array([242, 244, 239.0]) * k
    return Image.fromarray(a.astype("uint8"))


def make_assets(dest, names):
    """
    writes the requested logo images into dest
    :param dest: directory next to the page that uses them
    :param names: any of ordixa-icon.png, ordixa-wordmark.png,
        ordixa-wordmark-dark.png
    """
    makers = {
        "ordixa-icon.png": lambda: _crop(Image.open(IMAGES / "ordixa-logo2.png")),
        "ordixa-wordmark.png": lambda: _crop(Image.open(IMAGES / "ordixa-logo.png")),
        "ordixa-wordmark-dark.png": lambda: _reversed(
            _crop(Image.open(IMAGES / "ordixa-logo.png").convert("RGBA"))
        ),
    }
    for name in names:
        makers[name]().save(Path(dest) / name)
