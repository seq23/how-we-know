"""Ambient bed, generated. Original audio, no licensing, no attribution.

Deliberately minimal: a slow drifting drone plus sparse harmonic swells. It sits
far under the narration and its job is to remove the deadness of pure silence,
not to be noticed. Anything more melodic competes with the voice.
"""
import numpy as np, wave, argparse, math

SR = 48000

def _fade(x, sec=6.0):
    n = int(SR * sec)
    if len(x) < 2 * n: return x
    r = np.linspace(0, 1, n) ** 2
    x[:n] *= r; x[-n:] *= r[::-1]
    return x

def bed(seconds, seed=7, root=55.0):
    """root ~A1. Low fundamental + drifting fifths, no percussion, no melody."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(SR * seconds)) / SR
    out = np.zeros_like(t)

    # slow-moving partials; detuned pairs give a natural chorus without effects
    for mult, amp in ((1.0, 0.32), (1.5, 0.16), (2.0, 0.11), (3.0, 0.05), (4.0, 0.035)):
        for detune in (-0.12, 0.12):
            f = root * mult + detune
            # each partial breathes on its own slow LFO so nothing pulses together
            lfo = 0.5 + 0.5 * np.sin(2*np.pi*(rng.uniform(0.008, 0.03))*t + rng.uniform(0, 6.28))
            out += amp * (0.55 + 0.45*lfo) * np.sin(2*np.pi*f*t + rng.uniform(0, 6.28))

    # distant swells, sparse and irregular
    for _ in range(max(2, int(seconds / 45))):
        c = rng.uniform(0, seconds); w = rng.uniform(9, 20)
        env = np.exp(-0.5*((t - c)/(w/2.6))**2)
        out += 0.07 * env * np.sin(2*np.pi*(root*rng.choice([3, 4, 6]))*t + rng.uniform(0, 6.28))

    # filtered noise for water-like air; one-pole lowpass, cheap and stable
    n = rng.normal(0, 1, len(t)); a = 0.0009
    lp = np.zeros_like(n); acc = 0.0
    for i in range(0, len(n), 64):                     # blockwise: fast enough, same character
        blk = n[i:i+64]
        acc = acc + a * (blk.mean() - acc)
        lp[i:i+64] = acc
    out += 0.05 * lp / (np.abs(lp).max() + 1e-9)

    out = _fade(out.astype(np.float64))
    out /= (np.abs(out).max() + 1e-9)
    return out * 0.5

def write(path, x):
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("seconds", type=float)
    ap.add_argument("out")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--root", type=float, default=55.0)
    a = ap.parse_args()
    write(a.out, bed(a.seconds, a.seed, a.root))
    print(f"wrote {a.out}  {a.seconds:.0f}s  seed={a.seed} root={a.root}Hz")
