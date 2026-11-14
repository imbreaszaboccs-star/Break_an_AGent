"""Synthesize film SFX into public/sfx/. Stdlib only, fixed seed, 44.1 kHz 16-bit mono.
Run: python scripts/gen_sfx.py
"""
import math
import os
import random
import struct
import wave

SR = 44100
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "public", "sfx")
rnd = random.Random(1234)
TAU = 2 * math.pi


def n(sec):
    return int(sec * SR)


def sq(ph):
    return 1.0 if (ph % TAU) < math.pi else -1.0


def lowpass(x, fc):
    a = 1 - math.exp(-TAU * fc / SR)
    y, s = [], 0.0
    for v in x:
        s += a * (v - s)
        y.append(s)
    return y


def highpass(x, fc):
    a = math.exp(-TAU * fc / SR)
    y, px, py = [], 0.0, 0.0
    for v in x:
        py = a * (py + v - px)
        px = v
        y.append(py)
    return y


def noise(count):
    return [rnd.uniform(-1, 1) for _ in range(count)]


def env_ad(i, count, attack, decay_pow=3.0):
    a = max(1, n(attack))
    if i < a:
        return i / a
    return (1 - (i - a) / max(1, count - a)) ** decay_pow


def mix(*tracks):
    L = max(len(t) for t in tracks)
    out = [0.0] * L
    for t in tracks:
        for i, v in enumerate(t):
            out[i] += v
    return out


def save(name, x, peak=0.8):
    x = highpass(x, 40)  # nothing below 40 Hz
    m = max(abs(v) for v in x) or 1.0
    g = peak / m
    # tiny fade to avoid clicks
    f = min(n(0.004), len(x) // 2)
    for i in range(f):
        x[i] *= i / f
        x[-1 - i] *= i / f
    with wave.open(os.path.join(OUT, name), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, v * g)) * 32767)) for v in x))
    print("wrote", name, round(len(x) / SR, 2), "s")


def pager_beep():
    out = []
    for _ in range(3):
        c = n(0.12)
        out += [sq(TAU * 2800 * i / SR) * 0.6 * min(1, i / 60, (c - i) / 60) for i in range(c)]
        out += [0.0] * n(0.1)
    return out


def portal_boom():
    c = n(1.0)
    ph = 0.0
    sweep = []
    for i in range(c):
        t = i / c
        f = 120 + (45 - 120) * (1 - math.exp(-4 * t)) / (1 - math.exp(-4))
        ph += TAU * f / SR
        sweep.append(math.sin(ph) * env_ad(i, c, 0.01, 1.6))
    nz = lowpass(noise(c), 600)
    nz = [v * env_ad(i, c, 0.005, 3) * 1.5 for i, v in enumerate(nz)]
    return mix(sweep, nz)


def fwump():
    c = n(0.4)
    nz = lowpass(lowpass(noise(c), 220), 220)
    return [v * env_ad(i, c, 0.008, 3) * 6 for i, v in enumerate(nz)]


def boing():
    c = n(0.5)
    ph = 0.0
    out = []
    for i in range(c):
        t = i / SR
        f = 260 + 140 * math.sin(TAU * 11 * t) * math.exp(-5 * t) + 90 * math.exp(-8 * t)
        ph += TAU * f / SR
        out.append((math.sin(ph) + 0.3 * math.sin(2 * ph)) * env_ad(i, c, 0.005, 2))
    return out


def squeak():
    c = n(0.15)
    ph = 0.0
    out = []
    for i in range(c):
        t = i / c
        fc = 1500 + 1500 * t
        ph += TAU * (fc + 400 * math.sin(TAU * 28 * i / SR)) / SR
        out.append(math.sin(ph) * math.sin(math.pi * t) ** 0.5)
    return out


def stamp():
    c = n(0.3)
    ph = 0.0
    thud = []
    for i in range(c):
        t = i / SR
        ph += TAU * (90 * math.exp(-10 * t) + 55) / SR
        thud.append(math.sin(ph) * env_ad(i, c, 0.002, 4))
    k = n(0.03)
    click = [v * (1 - i / k) ** 2 * 0.7 for i, v in enumerate(highpass(noise(k), 2000))]
    return mix(thud, click)


def tick():
    c = n(0.04)
    x = highpass(noise(c), 1500)
    return [v * (1 - i / c) ** 4 for i, v in enumerate(x)]


def clack():
    c = n(0.06)
    ph = 0.0
    out = []
    for i in range(c):
        t = i / SR
        ph += TAU * 1800 / SR
        out.append((math.sin(ph) * 0.5 + rnd.uniform(-1, 1) * 0.6) * math.exp(-t * 90))
    return [v for v in lowpass(out, 5000)]


def pop():
    c = n(0.12)
    ph = 0.0
    out = []
    for i in range(c):
        t = i / SR
        ph += TAU * (900 * math.exp(-25 * t) + 250) / SR
        out.append(math.sin(ph) * math.exp(-t * 35))
    return out


def crt_on():
    c = n(0.4)
    ph = 0.0
    nz = lowpass(noise(c), 6000)
    out = []
    for i in range(c):
        t = i / c
        ph += TAU * (600 + 5000 * t * t) / SR
        out.append(nz[i] * 0.35 * (1 - t) + math.sin(ph) * 0.4 * min(1, t * 8) * (1 - t * 0.5))
    return out


def crt_off():
    c = n(0.3)
    ph = 0.0
    out = []
    for i in range(c):
        t = i / c
        ph += TAU * (7000 * (1 - t) ** 2 + 120) / SR
        out.append((math.sin(ph) + 0.2 * rnd.uniform(-1, 1)) * (1 - t) ** 1.5)
    return out


def drumroll():
    total = 3.0
    c = n(total)
    out = [0.0] * c
    t = 0.0
    while t < total - 0.1:
        prog = t / total
        interval = 0.11 - 0.07 * prog
        amp = 0.25 + 0.75 * prog
        s = n(t)
        L = n(0.09)
        hit = lowpass(noise(L), 5000)
        for i in range(L):
            if s + i < c:
                body = math.sin(TAU * 190 * i / SR) * 0.4
                out[s + i] += (hit[i] * 1.2 + body) * math.exp(-i / SR * 45) * amp
        t += interval
    return out


def blip(freq, dur, wobble=0.0):
    c = n(dur)
    ph = 0.0
    out = []
    for i in range(c):
        t = i / c
        ph += TAU * freq * (1 + wobble * math.sin(TAU * 20 * i / SR)) / SR
        out.append(sq(ph) * min(1, i / 120, (c - i) / 400) * (1 - 0.3 * t))
    return lowpass(out, 3500)


def cricket():
    c = n(1.0)
    out = [0.0] * c
    for start in (0.05, 0.17, 0.29, 0.55, 0.67, 0.79):
        s = n(start)
        L = n(0.07)
        for i in range(L):
            if s + i < c:
                t = i / L
                out[s + i] += math.sin(TAU * 4300 * i / SR) * math.sin(math.pi * t) * (1 + 0.5 * math.sin(TAU * 90 * i / SR)) * 0.35
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    save("pager-beep.wav", pager_beep(), 0.5)
    save("portal-boom.wav", portal_boom(), 0.9)
    save("fwump.wav", fwump(), 0.85)
    save("boing.wav", boing(), 0.7)
    save("squeak.wav", squeak(), 0.55)
    save("stamp.wav", stamp(), 0.85)
    save("tick.wav", tick(), 0.6)
    save("clack.wav", clack(), 0.6)
    save("pop.wav", pop(), 0.6)
    save("crt-on.wav", crt_on(), 0.6)
    save("crt-off.wav", crt_off(), 0.6)
    save("drumroll.wav", drumroll(), 0.7)
    save("blip-opus.wav", blip(140, 0.06), 0.5)
    save("blip-deepseek.wav", blip(420, 0.045, 0.01), 0.45)
    save("blip-narrator.wav", blip(250, 0.05), 0.45)
    save("cricket.wav", cricket(), 0.3)


if __name__ == "__main__":
    main()
