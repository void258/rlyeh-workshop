"""程序合成的音效库（骰子、打击、挥空、喷火、破门、锣、胜利……），不用外部素材，随本项目以 Apache-2.0 发布。

每个音效用自己名字算随机数种子，生成结果固定，和生成顺序无关。输出 48kHz 立体声。
"""
import zlib

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

SR = 48000
VERSION = 1            # 改了合成算法就加一，已经生成的音效会自动重做
rng = np.random.default_rng(0)


# ───────── 基本零件 ─────────
def n_(d):
    return int(SR * d)


def tt(d):
    return np.arange(n_(d)) / SR


def noise(d):
    return rng.standard_normal(n_(d))


def brown(d):
    x = np.cumsum(rng.standard_normal(n_(d)))
    x -= np.convolve(x, np.ones(2001) / 2001, mode='same')   # 去掉漂移
    return x / (np.abs(x).max() + 1e-9)


def filt(x, kind, f, order=2):
    return sosfilt(butter(order, f, btype=kind, fs=SR, output='sos'), x)


def decay(d, tau, attack=.002):
    t = tt(d)
    e = np.exp(-t / tau)
    a = n_(attack)
    if a:
        e[:a] *= np.linspace(0, 1, a)
    return e


def swell(d, peak=.5, attack_curve=2.0, release_tau=.25):
    """先渐强到 peak（占总长比例），再指数衰减。"""
    t = tt(d)
    p = d * peak
    up = (t / p) ** attack_curve
    down = np.exp(-(t - p) / release_tau)
    return np.where(t < p, up, down)


def sweep_bp(x, f0, f1, q=.35, steps=48):
    """中心频率从 f0 扫到 f1 的带通（分段处理，够用了）。"""
    out = np.zeros_like(x)
    edges = np.linspace(0, len(x), steps + 1).astype(int)
    for i in range(steps):
        c = f0 * (f1 / f0) ** (i / (steps - 1))
        lo, hi = max(30, c * (1 - q)), min(SR / 2 - 100, c * (1 + q))
        seg = slice(max(0, edges[i] - 2400), edges[i + 1])
        y = filt(x[seg], 'band', [lo, hi])
        out[edges[i]:edges[i + 1]] = y[-(edges[i + 1] - edges[i]):]
    return out


def tone(freq, d, wave='sine', vib=0.0, vib_rate=5.5, glide=None):
    t = tt(d)
    f = np.full_like(t, freq) if glide is None else freq * (glide / freq) ** (t / d)
    if vib:
        f = f * (1 + vib * np.sin(2 * np.pi * vib_rate * t))
    ph = 2 * np.pi * np.cumsum(f) / SR
    if wave == 'sine':
        return np.sin(ph)
    if wave == 'saw':
        return 2 * ((ph / (2 * np.pi)) % 1) - 1
    if wave == 'tri':
        return 2 * np.abs(2 * ((ph / (2 * np.pi)) % 1) - 1) - 1
    raise ValueError(wave)


def bell(freq, d=1.2, bright=1.0):
    parts = [(1, 1, .9), (2.0, .5 * bright, .55), (3.01, .25 * bright, .32), (4.21, .14 * bright, .2), (5.43, .07 * bright, .12)]
    y = sum(a * tone(freq * r, d) * decay(d, tau) for r, a, tau in parts)
    return y


def thump(f0=120, f1=45, d=.35, tau=.12):
    return tone(f0, d, glide=f1) * decay(d, tau, .001)


def hz(note):
    names = {'C': -9, 'D': -7, 'E': -5, 'F': -4, 'G': -2, 'A': 0, 'B': 2}
    n, acc, octv = note[0], note[1:-1], int(note[-1])
    semi = names[n] + (1 if acc == '#' else -1 if acc == 'b' else 0) + (octv - 4) * 12
    return 440 * 2 ** (semi / 12)


def place(buf, x, at):
    i = n_(at)
    if i < 0:
        x, i = x[-i:], 0
    j = min(len(buf), i + len(x))
    buf[i:j] += x[:j - i]
    return buf


def blank(d):
    return np.zeros(n_(d))


def to_stereo(x, width=.0, pan=0.0):
    """mono → 立体声；width 用轻微延迟做宽度，pan -1..1。"""
    l, r = x.copy(), x.copy()
    if width:
        dly = n_(.0004 + .0012 * width)
        r = np.concatenate([np.zeros(dly), r[:-dly]])
    gl, gr = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    return np.stack([l * gl * 1.414, r * gr * 1.414], 1)


def reverb(x, size=1.2, mix=.25, damp=4000):
    """噪声冲激响应的简易混响，立体声去相关。x 可以是单声道或立体声。"""
    if x.ndim == 1:
        x = to_stereo(x)
    ir_len = n_(size)
    irs = []
    for _ in range(2):
        ir = rng.standard_normal(ir_len) * np.exp(-np.arange(ir_len) / SR / (size / 6.5))
        ir = filt(ir, 'low', damp)
        ir[:n_(.012)] = 0
        irs.append(ir / np.sqrt((ir ** 2).sum()))
    wet = np.stack([fftconvolve(x[:, i], irs[i])[:len(x) + ir_len] for i in range(2)], 1)
    dry = np.concatenate([x, np.zeros((ir_len, 2))])[:len(wet)]
    return dry * (1 - mix * .5) + wet * mix


def finish(x, peak_db=-1.0, fade=.01):
    if x.ndim == 1:
        x = to_stereo(x)
    nz = np.where(np.abs(x).max(1) > 1e-4)[0]
    if len(nz):
        x = x[:nz[-1] + n_(.02)]
    f = min(len(x) // 2, n_(fade))
    x[-f:] *= np.linspace(1, 0, f)[:, None]
    return x / (np.abs(x).max() + 1e-9) * 10 ** (peak_db / 20)


# ───────── 骰子 ─────────
def click_wood(amp=1.0):
    d = .09
    y = filt(noise(d), 'band', [1800, 7000]) * decay(d, .004, .0003) * .8
    for f in rng.uniform([820, 1350, 2150], [980, 1550, 2450]):
        y += .35 * tone(f, d) * decay(d, rng.uniform(.015, .03), .0005)
    y += .25 * tone(rng.uniform(160, 200), d) * decay(d, .025, .001)
    return y * amp


def dice_roll():
    buf = blank(1.0)
    times = [0, .075, .16, .235, .31, .375, .43, .48, .525, .565, .6, .628, .65]
    for i, t0 in enumerate(times):
        place(buf, click_wood(.95 * .88 ** i * rng.uniform(.7, 1)), t0 + rng.uniform(-.006, .006))
        if rng.random() < .5:   # 两颗骰子偶尔相碰
            place(buf, click_wood(.4 * .88 ** i), t0 + .018)
    return reverb(buf, .35, .12)


def dice_good():
    buf = blank(1.4)
    for i, nt in enumerate(['E5', 'G#5', 'B5', 'E6']):
        place(buf, bell(hz(nt), 1.2) * (.6 + .1 * i), i * .065)
    buf += filt(noise(1.4), 'high', 7000) * decay(1.4, .25) * .05
    return reverb(buf, 1.4, .3)


def dice_bad():
    buf = blank(1.0)
    for i, (nt, d) in enumerate([('D4', .22), ('A3', .55)]):
        y = filt(tone(hz(nt), d, 'tri'), 'low', 1400) * decay(d, d * .55, .006)
        place(buf, y * .8, i * .2)
    place(buf, thump(110, 60, .3, .08) * .5, 0)
    return reverb(buf, .6, .15)


def brass(notes, d, cutoff=(400, 3200), vib=.004):
    t = tt(d)
    y = sum(tone(hz(nt), d, 'saw', vib=vib, vib_rate=5 + i * .3) for i, nt in enumerate(notes)) / len(notes)
    env_f = cutoff[0] + (cutoff[1] - cutoff[0]) * np.minimum(1, t / .12) * np.exp(-np.maximum(0, t - .12) / (d * .8))
    out = np.zeros_like(y)
    seg = n_(.02)
    for i in range(0, len(y), seg):     # 分段低通模拟滤波包络
        out[i:i + seg] = filt(y[max(0, i - 2400):i + seg], 'low', float(env_f[i]))[-len(y[i:i + seg]):]
    a = np.minimum(1, t / .03)
    rel = np.minimum(1, (d - t) / .25)
    return out * a * rel


def dice_crit():
    buf = blank(2.2)
    place(buf, thump(95, 50, .9, .35) * .9, .0)
    place(buf, brass(['C4', 'E4', 'G4', 'C5'], 1.6) * .9, .02)
    for i, nt in enumerate(['C6', 'E6', 'G6', 'C7', 'E7']):
        place(buf, bell(hz(nt), .9, .7) * .35, .15 + i * .05)
    cym = filt(noise(1.8), 'high', 5000) * swell(1.8, .08, 1.5, .6) * .35
    place(buf, cym, .0)
    return reverb(buf, 1.8, .35)


def dice_fumble():
    buf = blank(2.0)
    seq = [('G3', .26), ('F#3', .26), ('F3', .26), ('E3', .9)]
    at = 0
    for i, (nt, d) in enumerate(seq):
        y = brass([nt], d, (300, 1300), vib=.012 if i == 3 else .004)
        place(buf, y * .9, at)
        at += d + .02
    place(buf, thump(90, 40, .5, .2) * .7, at - .9)
    return reverb(buf, .9, .2)


# ───────── 打击 ─────────
def whoosh(d=.35, f0=400, f1=2600, back=None, amp=1.0):
    x = noise(d)
    y = sweep_bp(x, f0, f1) if back is None else np.concatenate([
        sweep_bp(noise(d * .55), f0, f1), sweep_bp(noise(d * .45), f1, back)])
    return y[:n_(d)] * swell(d, .55, 1.6, d * .2) * amp


def hit_blunt():
    buf = blank(.9)
    place(buf, whoosh(.14, 500, 2200, amp=.35), 0)
    place(buf, thump(150, 48, .5, .1), .13)
    place(buf, filt(noise(.12), 'low', 2200) * decay(.12, .02) * .7, .13)
    place(buf, filt(noise(.05), 'band', [900, 3200]) * decay(.05, .008) * .5, .13)
    return reverb(buf, .5, .15)


def hit_slash():
    buf = blank(1.0)
    place(buf, whoosh(.16, 900, 6000, amp=.5), 0)
    ring = sum(a * tone(f, .6) * decay(.6, tau) for f, a, tau in [(3150, .3, .12), (4410, .22, .09), (5230, .18, .07), (6720, .12, .05)])
    place(buf, ring * .6, .15)
    place(buf, filt(noise(.03), 'high', 2500) * decay(.03, .004) * .8, .15)
    place(buf, thump(220, 90, .2, .05) * .45, .16)
    return reverb(buf, .6, .18)


def hit_heavy():
    buf = blank(1.4)
    place(buf, whoosh(.2, 300, 1600, amp=.4), 0)
    place(buf, thump(110, 38, .9, .22), .19)
    place(buf, filt(noise(.06), 'band', [1800, 5500]) * decay(.06, .012) * .9, .19)
    place(buf, filt(brown(.8), 'low', 300) * decay(.8, .25) * .6, .2)
    return reverb(buf, .9, .22)


def miss():
    y = to_stereo(whoosh(.38, 350, 2800, back=700, amp=.9))
    pan = np.linspace(-.7, .7, len(y))
    y[:, 0] *= np.cos((pan + 1) * np.pi / 4) * 1.414
    y[:, 1] *= np.sin((pan + 1) * np.pi / 4) * 1.414
    return reverb(y, .4, .12)


def sling():
    buf = blank(1.1)
    for i in range(3):
        place(buf, whoosh(.16, 600, 1400, amp=.35 + .1 * i), i * .15)
    place(buf, whoosh(.3, 500, 3500, back=900, amp=.8), .45)
    return reverb(buf, .4, .12)


def burn():
    d = .9
    y = filt(brown(d), 'low', 1200) * swell(d, .2, 1.2, .3)
    y += filt(noise(d), 'band', [1500, 5000]) * swell(d, .15, 1.0, .2) * .3
    return reverb(y, .5, .15)


# ───────── 特效 ─────────
def crackles(d, rate, amp=.6):
    y = blank(d)
    for t0 in np.sort(rng.uniform(0, d - .03, int(rate * d))):
        c = filt(noise(.02), 'band', [1500, 7000]) * decay(.02, rng.uniform(.002, .006), .0003)
        place(y, c * rng.uniform(.2, 1) * amp, t0)
    return y


def fire_breath():
    d = 1.7
    roar = filt(brown(d), 'low', 900) * 1.2 + filt(noise(d), 'band', [700, 3500]) * .35
    lfo = 1 + .25 * np.sin(2 * np.pi * 7 * tt(d)) * np.sin(2 * np.pi * .9 * tt(d))
    env = np.minimum(1, tt(d) / .08) * np.minimum(1, (d - tt(d)) / .6)
    y = roar * lfo * env + crackles(d, 40, .5)
    place(y, thump(80, 40, .6, .2) * .5, 0)
    return reverb(to_stereo(y, .6), .8, .2)


def flames():
    d = 3.0
    base = filt(brown(d), 'low', 600) * .7 * swell(d, .3, 1.0, 1.2)
    y = base + crackles(d, 55, .55) + whoosh(d, 200, 900, amp=.4)
    return reverb(to_stereo(y, .8), 1.0, .2)


def ghost():
    d = 3.2
    t = tt(d)
    trem = 1 + .3 * np.sin(2 * np.pi * 4.2 * t)
    pad = (tone(hz('A4'), d) + tone(hz('A4') + 5, d) + .7 * tone(hz('E5') - 3, d) + .5 * tone(hz('C6'), d, vib=.006)) * trem
    pad *= swell(d, .4, 1.4, 1.1) * .35
    whistle = tone(1750, d, vib=.012, vib_rate=3.1, glide=2150) * swell(d, .55, 2.0, .7) * .12
    air = filt(noise(d), 'band', [2500, 7000]) * swell(d, .45, 2.5, .6) * .18
    return reverb(pad + whistle + air, 3.0, .5, 6000)


def dash():
    y = to_stereo(whoosh(.75, 250, 4200, back=500, amp=1.0), .5)
    return reverb(y, .4, .1)


def door_break():
    buf = blank(2.0)
    place(buf, thump(90, 35, 1.0, .25), 0)
    for t0 in [0, .03, .07, .13]:
        c = filt(noise(.12), 'band', [400, 3200]) * decay(.12, .02)
        c += sum(.3 * tone(f, .12) * decay(.12, .03) for f in rng.uniform(260, 700, 3))
        place(buf, c * rng.uniform(.6, 1), t0)
    for t0 in np.sort(rng.uniform(.2, 1.4, 22)):        # 木屑落地
        place(buf, click_wood(rng.uniform(.1, .45)), t0)
    return reverb(buf, 1.2, .25)


def door_bang():
    buf = blank(.9)
    place(buf, thump(85, 45, .6, .12), 0)
    place(buf, sum(.4 * tone(f, .4) * decay(.4, .08) for f in [215, 330, 470]), 0)
    place(buf, filt(noise(.06), 'low', 1500) * decay(.06, .015) * .6, 0)
    return reverb(filt(buf, 'low', 2500), 1.0, .3, 2500)


def rumble():
    d = 1.0
    y = filt(brown(d), 'low', 140) * swell(d, .1, 1.0, .35) * 1.2 + thump(60, 30, d, .3) * .8
    return reverb(y, .6, .12)


def flash():
    buf = blank(2.2)
    rise = filt(noise(.45), 'high', 2500) * (tt(.45) / .45) ** 2.5 * .5
    place(buf, rise, 0)
    for nt in ['C5', 'G5', 'E6', 'B6']:
        place(buf, bell(hz(nt), 1.6, .8) * .4, .45)
    place(buf, filt(noise(1.2), 'high', 3000) * decay(1.2, .3) * .35, .45)
    return reverb(buf, 2.0, .4)


def dawn():
    buf = blank(3.2)
    pad = sum(tone(hz(nt), 3.2) for nt in ['D4', 'A4', 'F#5']) * swell(3.2, .4, 1.5, 1.2) * .18
    buf += pad
    for i, nt in enumerate(['D6', 'E6', 'F#6', 'A6', 'B6', 'D7']):
        place(buf, bell(hz(nt), 1.4, .6) * .28, .3 + i * .18)
    buf += filt(noise(3.2), 'band', [3000, 9000]) * swell(3.2, .5, 2.0, .9) * .05
    return reverb(buf, 2.5, .45)


# ───────── 战斗 / 横幅 ─────────
def taiko(amp=1.0):
    d = .9
    return (thump(78, 46, d, .26) + filt(noise(d), 'low', 500) * decay(d, .05) * .5) * amp


def battle_start():
    buf = blank(2.6)
    place(buf, filt(noise(.5), 'high', 4000) * (tt(.5) / .5) ** 2 * .3, 0)
    for t0, a in [(0, .8), (.17, .7), (.5, 1.0)]:
        place(buf, taiko(a), t0)
    place(buf, brass(['D3', 'F3', 'A3', 'D4'], 1.3, (500, 2800)) * .8, .5)
    place(buf, filt(noise(1.6), 'high', 3000) * decay(1.6, .5) * .4, .5)
    return reverb(buf, 1.6, .28)


def gong():
    d = 3.0
    f0 = 98
    y = sum(a * (tone(f0 * r, d) + tone(f0 * r + .7, d)) * decay(d, tau, .004)
            for r, a, tau in [(1, 1, 1.6), (1.48, .6, 1.2), (1.95, .5, 1.0), (2.39, .35, .8), (2.81, .3, .6), (3.42, .2, .5), (4.2, .15, .4)])
    place(y, taiko(.5), 0)
    return reverb(y * .5, 2.2, .3)


def battle_end():
    buf = blank(2.8)
    for i, nt in enumerate(['C5', 'E5', 'G5', 'C6']):
        place(buf, bell(hz(nt), 1.5) * .45, i * .09)
    place(buf, brass(['C4', 'E4', 'G4', 'C5'], 1.8, (600, 3000)) * .7, .3)
    place(buf, taiko(.6), .3)
    return reverb(buf, 2.0, .35)


def clash():
    buf = blank(1.8)
    place(buf, whoosh(.18, 600, 3000, amp=.4), 0)
    ring = sum(a * tone(f, 1.4) * decay(1.4, tau) for f, a, tau in [(523, .5, .7), (1307, .4, .5), (2091, .3, .4), (3011, .25, .3), (4180, .2, .22)])
    place(buf, ring * .7, .17)
    place(buf, filt(noise(.04), 'high', 2000) * decay(.04, .006), .17)
    place(buf, thump(100, 45, .6, .18) * .6, .17)
    return reverb(buf, 1.2, .25)


def item():
    buf = blank(2.0)
    for i, nt in enumerate(['C6', 'E6', 'G6', 'C7', 'E7', 'G7']):
        place(buf, bell(hz(nt), 1.0, .6) * .3, i * .045)
    buf += filt(noise(2.0), 'high', 6000) * swell(2.0, .2, 1.0, .5) * .08
    buf += sum(tone(hz(nt), 2.0) for nt in ['C5', 'G5']) * swell(2.0, .3, 1.5, .6) * .1
    return reverb(buf, 1.8, .4)


def chapter_boom():
    buf = blank(4.0)
    rise = filt(noise(.9), 'low', 1800) * (tt(.9) / .9) ** 3 * .5
    place(buf, rise, 0)
    place(buf, thump(62, 32, 3.0, 1.0) * 1.0, .9)
    place(buf, filt(noise(1.2), 'low', 400) * decay(1.2, .35) * .5, .9)
    place(buf, bell(hz('D3'), 2.5, .5) * .25, .9)
    return reverb(buf, 3.0, .4, 3000)


def scene_whoosh():
    buf = blank(1.6)
    place(buf, whoosh(1.0, 500, 2200, back=800, amp=.5), 0)
    place(buf, bell(hz('A5'), 1.0, .4) * .18, .55)
    return reverb(buf, 1.2, .3)


def cg_impact():
    buf = blank(3.0)
    place(buf, thump(70, 30, 2.2, .7), 0)
    place(buf, filt(noise(.08), 'high', 1500) * decay(.08, .01) * .8, 0)
    ring = sum(a * tone(f, 2.0) * decay(2.0, tau) for f, a, tau in [(311, .4, .9), (466, .3, .7), (740, .2, .5)])
    place(buf, ring * .4, 0)
    return reverb(buf, 2.4, .4, 3500)


SOUNDS = {
    'dice_roll': dice_roll, 'dice_good': dice_good, 'dice_bad': dice_bad, 'dice_crit': dice_crit, 'dice_fumble': dice_fumble,
    'hit_blunt': hit_blunt, 'hit_slash': hit_slash, 'hit_heavy': hit_heavy, 'miss': miss, 'sling': sling, 'burn': burn,
    'fire_breath': fire_breath, 'flames': flames, 'ghost': ghost, 'dash': dash, 'door_break': door_break,
    'door_bang': door_bang, 'rumble': rumble, 'flash': flash, 'dawn': dawn,
    'battle_start': battle_start, 'gong': gong, 'battle_end': battle_end, 'clash': clash, 'item': item,
    'chapter': chapter_boom, 'scene': scene_whoosh, 'cg': cg_impact,
}


def seed(name):
    """按名字重置随机数，同一个音效每次都一样。"""
    global rng
    rng = np.random.default_rng(zlib.crc32(name.encode('utf-8')))


def render(name):
    seed(name)
    return finish(SOUNDS[name]())
