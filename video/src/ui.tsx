import React from 'react';
import {random, Sequence, staticFile, useCurrentFrame} from 'remotion';
import {Audio} from '@remotion/media';
import {BALOO, C, VT323} from './theme';
import {lerp} from './lib/anim';
import voData from './vo.json';

/* ------------------------------------------------------------------ */
/* Sound effects                                                        */
/* ------------------------------------------------------------------ */

export const SFX = {
  pagerBeep: staticFile('sfx/pager-beep.wav'),
  portalBoom: staticFile('sfx/portal-boom.wav'),
  fwump: staticFile('sfx/fwump.wav'),
  boing: staticFile('sfx/boing.wav'),
  squeak: staticFile('sfx/squeak.wav'),
  stamp: staticFile('sfx/stamp.wav'),
  tick: staticFile('sfx/tick.wav'),
  clack: staticFile('sfx/clack.wav'),
  pop: staticFile('sfx/pop.wav'),
  crtOn: staticFile('sfx/crt-on.wav'),
  crtOff: staticFile('sfx/crt-off.wav'),
  drumroll: staticFile('sfx/drumroll.wav'),
  blipOpus: staticFile('sfx/blip-opus.wav'),
  blipDeepseek: staticFile('sfx/blip-deepseek.wav'),
  blipNarrator: staticFile('sfx/blip-narrator.wav'),
  cricket: staticFile('sfx/cricket.wav'),
  whoosh: staticFile('sfx/whoosh.wav'),
  whip: staticFile('sfx/whip.wav'),
  ding: staticFile('sfx/ding.wav'),
  switch: staticFile('sfx/switch.wav'),
  mouseClick: staticFile('sfx/mouse-click.wav'),
  recordScratch: staticFile('sfx/record-scratch.wav'),
} as const;

/** Play a sound at a LOCAL frame (relative to the enclosing Sequence/scene). */
export const Sfx: React.FC<{src: string; at: number; volume?: number}> = ({src, at, volume = 1}) => (
  <Sequence from={at} layout="none">
    <Audio src={src} volume={volume} />
  </Sequence>
);

/* ------------------------------------------------------------------ */
/* Subtitles                                                            */
/* ------------------------------------------------------------------ */

export type Who = 'opus' | 'deepseek' | 'narrator';
const WHO_COLOR: Record<Who, string> = {opus: C.opus, deepseek: C.deepseek, narrator: C.narrator};
const WHO_NAME: Record<Who, string> = {opus: 'OPUS', deepseek: 'DEEPSEEK', narrator: 'NARRATOR'};
const BLIP: Record<Who, string> = {opus: SFX.blipOpus, deepseek: SFX.blipDeepseek, narrator: SFX.blipNarrator};

/** Bottom-center subtitle. Occupies the bottom 255 px at most. */
export const Subtitle: React.FC<{who: Who; text: string}> = ({who, text}) => (
  <div
    style={{
      position: 'absolute',
      left: 0,
      right: 0,
      bottom: 22,
      display: 'flex',
      justifyContent: 'center',
    }}
  >
    <div style={{maxWidth: 1500, display: 'flex', flexDirection: 'column', alignItems: 'flex-start'}}>
      <div
        style={{
          fontFamily: BALOO,
          fontWeight: 800,
          fontSize: 34,
          lineHeight: '38px',
          padding: '2px 18px',
          borderRadius: 12,
          background: WHO_COLOR[who],
          color: C.white,
          border: `5px solid ${C.line}`,
          marginBottom: 6,
          letterSpacing: 1,
        }}
      >
        {WHO_NAME[who]}
      </div>
      <div
        style={{
          fontFamily: BALOO,
          fontWeight: 800,
          fontSize: 75,
          lineHeight: '78px',
          color: C.white,
          textAlign: 'center',
          WebkitTextStroke: '16px #000',
          paintOrder: 'stroke fill',
          strokeLinejoin: 'round',
        }}
      >
        {text}
      </div>
    </div>
  </div>
);

const fnv1a = (str: string): string => {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, '0');
};

const VO = voData as Record<string, {file: string; frames: number; say?: string}>;
const voEntry = (who: string, text: string) => VO[fnv1a(who + '|' + text)];

/** Length in frames of the generated voiceover for a line, if any. */
export const voFrames = (who: string, text: string): number | undefined => voEntry(who, text)?.frames;

/** Subtitle for [from, from+dur) (held at least 43 frames, or the voice length) plus voiceover (or blips if no voice file). */
export const Line: React.FC<{who: Who; from: number; dur: number; text: string; blips?: boolean}> = ({
  who,
  from,
  dur,
  text,
  blips = true,
}) => {
  const entry = voEntry(who, text);
  const hold = Math.max(dur, 43, entry?.frames ?? 0);
  const speak = Math.max(4, Math.min(text.length * 1.6, dur - 4));
  const n = blips && !entry ? Math.floor(speak / 4) : 0;
  return (
    <Sequence from={from} durationInFrames={hold} layout="none">
      <Subtitle who={who} text={entry?.say ?? text} />
      {entry ?<Audio src={staticFile(entry.file)} volume={1} /> : null}
      {Array.from({length: n}, (_, k) => (
        <Sfx key={k} src={BLIP[who]} at={k * 4} volume={0.5} />
      ))}
    </Sequence>
  );
};

/* ------------------------------------------------------------------ */
/* Labels & text                                                        */
/* ------------------------------------------------------------------ */

const TONES = {
  dark: {bg: C.line, fg: C.amber, border: C.line},
  amber: {bg: C.amber, fg: C.line, border: C.line},
  cream: {bg: C.boardCream, fg: C.line, border: C.line},
} as const;

/** VT323 label in a flat outlined box, centered on (x,y). Pops in on `appearAt` (local frame). */
export const ScreenTag: React.FC<{
  x: number;
  y: number;
  text: string;
  size?: number;
  tone?: 'dark' | 'amber' | 'cream';
  appearAt?: number;
}> = ({x, y, text, size = 44, tone = 'dark', appearAt = 0}) => {
  const frame = useCurrentFrame();
  if (frame < appearAt) return null;
  const s = lerp(frame, [appearAt, appearAt + 3], [0.75, 1]);
  const t = TONES[tone];
  return (
    <div
      style={{
        position: 'absolute',
        left: x,
        top: y,
        translate: '-50% -50%',
        scale: String(s),
        padding: `${size * 0.12}px ${size * 0.4}px`,
        background: t.bg,
        color: t.fg,
        border: `6px solid ${t.border}`,
        outline: tone === 'dark' ? `3px solid ${C.boardCream}` : undefined,
        outlineOffset: tone === 'dark' ? -10 : undefined,
        borderRadius: 10,
        fontFamily: VT323,
        fontSize: size,
        lineHeight: 1.05,
        whiteSpace: 'pre',
        textAlign: 'center',
      }}
    >
      {text}
    </div>
  );
};

/** Reveals characters at `cps` chars per second after `startAt` (local frame). */
export const Typewriter: React.FC<{
  text: string;
  startAt: number;
  cps?: number;
  style?: React.CSSProperties;
}> = ({text, startAt, cps = 24, style}) => {
  const frame = useCurrentFrame();
  const n = Math.max(0, Math.min(text.length, Math.floor(((frame - startAt) * cps) / 24)));
  return <span style={{fontFamily: VT323, whiteSpace: 'pre-wrap', ...style}}>{text.slice(0, n)}</span>;
};

/** Chunky title letters appearing one per 2 frames. No overshoot. Positioned in normal flow. */
export const TitlePop: React.FC<{text: string; startAt: number; size: number; color: string}> = ({
  text,
  startAt,
  size,
  color,
}) => {
  const frame = useCurrentFrame();
  return (
    <div style={{display: 'flex', fontFamily: BALOO, fontWeight: 800, fontSize: size, lineHeight: 1}}>
      {text.split('').map((ch, i) => {
        const at = startAt + i * 2;
        const shown = frame >= at;
        const rot = (random(`tp-${text}-${i}`) * 2 - 1) * 3;
        return (
          <span
            key={i}
            style={{
              display: 'inline-block',
              whiteSpace: 'pre',
              opacity: shown ? 1 : 0,
              rotate: `${rot}deg`,
              color,
              WebkitTextStroke: `${Math.round(size * 0.12)}px ${C.line}`,
              paintOrder: 'stroke fill',
              strokeLinejoin: 'round',
              translate: `0 ${shown ? lerp(frame, [at, at + 2], [size * 0.15, 0]) : 0}px`,
            }}
          >
            {ch}
          </span>
        );
      })}
    </div>
  );
};
