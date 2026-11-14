#!/usr/bin/env python3
"""Generate ElevenLabs voiceover for every <Line> in src/scenes/*.tsx. Stdlib only.

Usage: python scripts/gen_vo.py [--force] [--only KEY [--max FRAMES]] [--speed KEY=1.1 ...]
(--speed is accepted but eleven_v4 barely reacts to it; shorten TTS_TEXT instead.)
Reads ELEVENLABS_API_KEY from video/.env.local (never printed).
"""
import glob, json, math, os, re, struct, sys, urllib.request, wave

VOICES = {
    'opus': 'kLhAstPcnnPxqzk6gS5i',
    'deepseek': 'IKne3meq5aSn9XLyUdCD',
    'narrator': 'pqHfZKP75CvOlQylNhV4',
}
DEFAULT_TAG = {
    'opus': '[deadpan, dry, slow]',
    'deepseek': '[nervous, fast]',
    'narrator': '[cheerful 1950s newsreel announcer]',
}
OVERRIDE = {
    'Who puts a WHALE in a BOX?!': '[panicked, shouting]',
    'A fresh deploy! It\'s ALWAYS the deploy!': '[excited]',
    'Then why is it raining money?!': '[confused, panicked]',
    "We've been here. We've been HERE. WE'VE BEEN—": '[panicking, getting louder]',
    'Okay. What if we just… restart everything?': '[whispering, sneaky]',
    'Scale everything to max?': '[whispering]',
    'Roll back all! Block the biggest client! Shed all traffic! Write ‘score one point oh’ in the report!': '[rapid-fire, desperate]',
    "We're all geniuses!": '[excited]',
    'Third… but fastest!': '[proud]',
    "You weren't tested.": '[quietly, awkward]',
    '…I\'m not on it.': '[long pause] [flat]',
    'Good.': '[satisfied]',
    '…For socks.': '[sighs]',
}
# Optional TTS-only text replacements (never subtitles), by subtitle text.
TTS_TEXT = {
    # shortened for timing only (subtitles keep the full text)
    "Welcome to OnCall! You're the on-call engineer for a twelve-service platform…": 'Welcome to OnCall!',
    '…that is already on fire.': '…already on fire.',
    'Every tool call moves the clock.': 'Every call moves the clock.',
    'Same seed. Same disaster. Every time.': 'Same seed. Same disaster.',
    'Sixty: traffic actually served. Thirty: faults truly fixed. Ten: the exact root cause.': 'Sixty traffic. Thirty faults. Ten root cause.',
    'Lose data? Quartered. Break things? Points off.': 'Lose data? Quartered.',
    "We've been here. We've been HERE. WE'VE BEEN—": "We've been here. We've been HERE. WE'VE—",
    'Okay. What if we just… restart everything?': 'Restart everything?',
    'Scale everything to max?': 'Scale to max?',
    'Roll back all! Block the biggest client! Shed all traffic! Write ‘score one point oh’ in the report!': 'Roll back! Block! Shed! Score one point oh!',
}
# Speed per key is passed via --speed; persisted speeds live here.
SPEED = {}
EXPECTED = 27

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FPS = 24


def fnv1a(s):
    h = 0x811C9DC5
    for ch in s:  # iterate UTF-16 code units, same as JS charCodeAt
        for u in struct_units(ch):
            h ^= u
            h = (h * 0x01000193) & 0xFFFFFFFF
    return '%08x' % h


def struct_units(ch):
    c = ord(ch)
    if c < 0x10000:
        return [c]
    c -= 0x10000
    return [0xD800 + (c >> 10), 0xDC00 + (c & 0x3FF)]


def trim(pcm, th=500):
    """Trim leading/trailing silence, keeping ~1 frame lead and ~2 frames tail."""
    n = len(pcm) // 2
    d = struct.unpack('<%dh' % n, pcm)
    a = next((i for i, x in enumerate(d) if abs(x) > th), 0)
    b = next((n - i for i, x in enumerate(reversed(d)) if abs(x) > th), n)
    a = max(0, a - 1000)
    b = min(n, b + 2000)
    return pcm[a * 2:b * 2]


def collect():
    out = []
    pat = re.compile(r'<Line\s+who="(\w+)"\s+from=\{\d+\}\s+dur=\{\d+\}\s+text="([^"]*)"')
    for f in sorted(glob.glob(os.path.join(ROOT, 'src', 'scenes', '*.tsx'))):
        for m in pat.finditer(open(f, encoding='utf-8').read()):
            out.append((m.group(1), m.group(2)))
    return out


def api_key():
    for l in open(os.path.join(ROOT, '.env.local'), encoding='utf-8'):
        if l.startswith('ELEVENLABS_API_KEY='):
            return l.split('=', 1)[1].strip().strip('"\'')
    sys.exit('no key')


def tts(who, text, key, speed=None):
    body = {'text': text, 'model_id': 'eleven_v4'}
    if speed:
        body['voice_settings'] = {'speed': speed}
    req = urllib.request.Request(
        f'https://api.elevenlabs.io/v1/text-to-speech/{VOICES[who]}?output_format=pcm_24000',
        data=json.dumps(body).encode(), method='POST',
        headers={'xi-api-key': key, 'Content-Type': 'application/json'})
    try:
        return urllib.request.urlopen(req, timeout=120).read()
    except urllib.error.HTTPError as e:
        sys.exit(f'HTTP {e.code} for {text[:30]!r}: {e.read()[:200]!r}')


def main():
    a = sys.argv[1:]
    force = '--force' in a
    only = a[a.index('--only') + 1] if '--only' in a else None
    speeds = {}
    for i, x in enumerate(a):
        if x == '--speed':
            k, v = a[i + 1].split('=')
            speeds[k] = float(v)
    maxf = int(a[a.index('--max') + 1]) if '--max' in a else None
    lines = collect()
    assert len(lines) == EXPECTED, f'found {len(lines)} lines, expected {EXPECTED}'
    os.makedirs(os.path.join(ROOT, 'public', 'vo'), exist_ok=True)
    vo_json = os.path.join(ROOT, 'src', 'vo.json')
    manifest = json.load(open(vo_json, encoding='utf-8')) if os.path.exists(vo_json) else {}
    key = None
    rows = []
    for who, text in lines:
        k = fnv1a(who + '|' + text)
        path = os.path.join(ROOT, 'public', 'vo', k + '.wav')
        regen = k in speeds or (only == k) or (force and not only) or not os.path.exists(path)
        if regen:
            key = key or api_key()
            tags = DEFAULT_TAG[who] + ' ' + OVERRIDE.get(text, '')
            pcm = tts(who, tags.strip() + ' ' + TTS_TEXT.get(text, text), key, speeds.get(k, SPEED.get(k)))
            pcm = trim(pcm)
            for _ in range(5):  # --max N: retry (output varies run to run) until short enough
                if not maxf or len(pcm) / 48000 * FPS <= maxf:
                    break
                pcm = trim(tts(who, tags.strip() + ' ' + TTS_TEXT.get(text, text), key, speeds.get(k, SPEED.get(k))))
            with wave.open(path, 'wb') as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
        with wave.open(path, 'rb') as w:
            secs = w.getnframes() / w.getframerate()
        manifest[k] = {'who': who, 'text': text, 'say': TTS_TEXT.get(text, text), 'file': f'vo/{k}.wav', 'frames': math.ceil(secs * FPS)}
        rows.append((k, who, manifest[k]['frames'], text))
    live = {r[0] for r in rows}
    manifest = {k: v for k, v in manifest.items() if k in live}
    json.dump(manifest, open(vo_json, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'{len(rows)} lines')
    for k, who, fr, text in rows:
        print(f'{k} {who:9} {fr:4}  {text}')


if __name__ == '__main__':
    main()
