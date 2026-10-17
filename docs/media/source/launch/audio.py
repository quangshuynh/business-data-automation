"""Soundtrack for the Ordixa v2 launch cut. 120 BPM. The problem scene sits on
a tense D minor pulse; "Meet Ordixa" resolves to D major. SFX share the key and
the reverb. Timings mirror video.html."""

import wave

import numpy as np

SR = 48000
DUR = 23.0
N = int(SR * DUR)
t_all = np.arange(N) / SR
rng = np.random.default_rng(11)


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def buf():
    return np.zeros(N)


def fft_filter(x, resp):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    return np.fft.irfft(X * resp(f), len(x))


def lp(fc, o=2):
    return lambda f: 1 / np.sqrt(1 + (f / fc) ** (2 * o))


def hp(fc, o=2):
    return lambda f: 1 / np.sqrt(1 + (np.maximum(f, 1e-3) / fc) ** (-2 * o))


def bp(lo, hi):
    return lambda f: lp(hi)(f) * hp(lo)(f)


def add(dst, sig, start):
    i = int(round(start * SR))
    if i >= N:
        return
    n = min(len(sig), N - i)
    dst[i : i + n] += sig[:n]


def tone(freq, length, harm=6, tilt=1.6, detune=0.0):
    tt = np.arange(int(length * SR)) / SR
    out = np.zeros_like(tt)
    for d in [-detune, 0, detune] if detune else [0]:
        f0 = freq * 2 ** (d / 1200)
        ph = rng.uniform(0, 2 * np.pi)
        for k in range(1, harm + 1):
            if f0 * k > SR / 2.2:
                break
            out += np.sin(2 * np.pi * f0 * k * tt + ph * k) / k**tilt
    return out, tt


def pluck(m, length=0.8, bright=5, decay=6.0, amp=1.0):
    s, tt = tone(hz(m), length, harm=bright, tilt=1.4)
    return s * np.minimum(tt / 0.004, 1) * np.exp(-tt * decay) * amp


music, sfx, drums = buf(), buf(), buf()

# ---------- 0-3 s: tension (D minor) ----------
pad = buf()
for m in [38, 50, 53, 57, 64]:  # D2 D3 F3 A3 E4  (Dm add9)
    s, tt = tone(hz(m), 3.3, harm=6, tilt=1.8, detune=8)
    add(pad, s * np.minimum(tt / 0.3, 1) * np.clip((3.3 - tt) / 0.5, 0, 1) * 0.10, 0.0)
music += fft_filter(pad, lp(650, 2))
# low pulse on eighths, slightly accelerating feel through accents
for i in range(12):
    st = i * 0.25
    L = 0.22
    tt = np.arange(int(L * SR)) / SR
    s = np.sin(2 * np.pi * hz(38) * tt) + 0.4 * np.sin(2 * np.pi * hz(50) * tt)
    add(
        music,
        s
        * np.minimum(tt / 0.005, 1)
        * np.exp(-tt * 14)
        * (0.16 if i % 4 == 0 else 0.09),
        st,
    )
# problem rings: dry, slightly dissonant ticks (F and Bb against the D pulse)
TENSE = [77, 74, 78, 77, 82, 81, 77]
for i in range(7):
    add(
        sfx,
        fft_filter(pluck(TENSE[i] - 12, 0.3, bright=3, decay=16, amp=0.06), lp(2600)),
        0.45 + i * 0.2,
    )
# riser into the resolve
n = rng.standard_normal(int(0.7 * SR))
x = np.arange(len(n)) / len(n)
add(
    sfx,
    (fft_filter(n, bp(300, 900)) * (1 - x) + fft_filter(n, bp(2000, 6000)) * x)
    * x**2.2
    * 0.07,
    2.32,
)

# ---------- 3 s onward: D major ----------
CHORDS = [[50, 54, 57, 61], [47, 50, 54, 57], [43, 47, 50, 54], [45, 49, 52, 54]]
ROOTS = [38, 35, 31, 33]
pad = buf()
for b in range(8):
    st = 3.0 + b * 2.0
    if st >= 18.5:
        break
    for m in CHORDS[b % 4]:
        s, tt = tone(hz(m), 2.8, harm=7, tilt=1.7, detune=6)
        add(
            pad,
            s * np.minimum(tt / 0.35, 1) * np.clip((2.8 - tt) / 0.8, 0, 1) * 0.10,
            st,
        )
    L = 2.0
    tt = np.arange(int(L * SR)) / SR
    r = ROOTS[b % 4]
    sub = np.sin(2 * np.pi * hz(r) * tt) + 0.25 * np.sin(4 * np.pi * hz(r) * tt)
    add(
        music,
        sub * np.minimum(tt / 0.02, 1) * np.clip((L - tt) / 0.15, 0, 1) * 0.15,
        st,
    )
# outro chord, held to the end
for m in [38, 50, 57, 61, 64, 66]:
    s, tt = tone(hz(m), DUR - 18.5, harm=7, tilt=1.6, detune=7)
    add(pad, s * np.minimum(tt / 0.3, 1) * np.exp(-tt * 0.3) * 0.11, 18.5)
music += fft_filter(pad, lp(2600, 2))


def kick():
    L = 0.45
    tt = np.arange(int(L * SR)) / SR
    f = 45 + 75 * np.exp(-tt * 28)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 9) * 0.55


def hat(a):
    n = rng.standard_normal(int(0.08 * SR))
    n = fft_filter(n, hp(7000, 2))
    return n * np.exp(-np.arange(len(n)) / SR * 60) * a


k = kick()
for i in range(16):
    bt = 3.0 + i * 1.0
    if bt > 18.0:
        break
    add(drums, k * (1.2 if i == 0 else 1), bt)
for i in range(40):
    bt = 6.25 + i * 0.5
    if bt > 18.3:
        break
    add(drums, hat(0.02 if i % 2 else 0.014), bt)

arp = buf()
for i in range(100):
    st = 6.0 + i * 0.25
    if st >= 18.5:
        break
    ch = CHORDS[int((st - 3.0) // 2) % 4]
    m = ch[[0, 2, 1, 3, 2, 1, 3, 2][i % 8]] + 12
    add(arp, pluck(m, 0.6, bright=5, decay=7, amp=0.06 if i % 2 == 0 else 0.042), st)
music += fft_filter(arp, lp(3200, 1))


# ---------- SFX ----------
def sweep(L, f0, f1, amp):
    n = rng.standard_normal(int(L * SR))
    x = np.arange(len(n)) / len(n)
    a = fft_filter(n, bp(f0 * 0.7, f0 * 1.4))
    b = fft_filter(n, bp(f1 * 0.7, f1 * 1.4))
    return (a * (1 - x) + b * x) * np.sin(np.pi * x) ** 2 * amp


for tc in [5.7, 9.2, 14.2, 18.2]:
    add(sfx, sweep(0.55, 2400, 600, 0.05), tc)
# reveal bloom
for m in [62, 66, 69, 73]:
    add(sfx, pluck(m + 12, 2.5, bright=4, decay=1.6, amp=0.045), 3.12)
SC = [62, 64, 66, 69, 71, 74, 76, 78, 81, 83]


def ping(t0, i, amp=0.05, decay=9, oct=12):
    add(sfx, pluck(SC[i % len(SC)] + oct, 0.5, bright=3, decay=decay, amp=amp), t0)


# import: files land, mapping lines draw
add(sfx, pluck(50, 0.5, bright=3, decay=10, amp=0.07), 6.25)
add(sfx, pluck(54, 0.5, bright=3, decay=10, amp=0.06), 6.4)
for i in range(5):
    ping(6.95 + i * 0.22 + 0.3, i, 0.04 if i < 4 else 0.02)
# clean & validate: scan, then a rising pluck per fixed row, a low soft tone per held row
n = rng.standard_normal(int(2.0 * SR))
x = np.arange(len(n)) / len(n)
add(
    sfx,
    (fft_filter(n, bp(500, 1500)) * (1 - x) + fft_filter(n, bp(1500, 4500)) * x)
    * np.sin(np.pi * x)
    * 0.025,
    10.2,
)
for i in range(7):
    at = 10.25 + (i + 0.5) / 7 * 1.9
    if i < 3:
        ping(at, 4 + i * 2, 0.06)
    else:
        add(
            sfx,
            fft_filter(
                pluck([45, 45, 42, 42][i - 3] + 12, 0.6, bright=3, decay=8, amp=0.07),
                lp(1400),
            ),
            at,
        )
for m in [74, 78, 81]:
    add(sfx, pluck(m, 1.0, bright=4, decay=3.5, amp=0.035), 12.2)
ping(12.4, 5, 0.04)
ping(12.55, 7, 0.04)
# results: cards rise, checks tick
for i in range(3):
    ping(15.05 + i * 0.22, [2, 4, 6][i], 0.05)
for i in range(9):
    ping(15.75 + i * 0.07, 5 + (i % 4), 0.014, 18)
# close
for m in [74, 78, 81, 85]:
    add(sfx, pluck(m, 2.8, bright=3, decay=1.2, amp=0.04), 18.6)
ping(19.45, 8, 0.035, 5)


def reverb(x, seconds=2.4, decay=3.2, seed=0):
    r = np.random.default_rng(seed)
    L = int(seconds * SR)
    tt = np.arange(L) / SR
    ir = r.standard_normal(L) * np.exp(-tt * decay)
    ir = fft_filter(ir, lp(5000, 1))
    ir[: int(0.012 * SR)] = 0
    ir /= np.sqrt(np.sum(ir**2))
    n = len(x) + L
    return np.fft.irfft(np.fft.rfft(x, n) * np.fft.rfft(ir, n), n)[: len(x)]


send = music * 0.35 + sfx * 0.6
wl, wr = reverb(send, seed=1), reverb(send, seed=2)
dry = music + sfx * 0.85 + drums
fade = np.clip(t_all / 0.05, 0, 1) * np.clip((DUR - t_all) / 1.4, 0, 1) ** 1.5
st = np.stack([(dry + wl * 0.32) * fade, (dry + wr * 0.32) * fade], 1)
st /= np.max(np.abs(st)) / 0.9
st = np.tanh(st * 1.15) / np.tanh(1.15) * 0.89
with wave.open("soundtrack.wav", "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes((st * 32767).astype("<i2").tobytes())
print("wrote soundtrack.wav", len(st) / SR)
