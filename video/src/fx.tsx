import React from 'react';
import {AbsoluteFill, Easing, random, Sequence, useCurrentFrame} from 'remotion';
import {Audio} from '@remotion/media';
import {staticFile} from 'remotion';
import {C, H, W} from './theme';
import {lerp} from './lib/anim';

/* ------------------------------------------------------------------ */
/* Line boil                                                            */
/* ------------------------------------------------------------------ */

/** Render once at Film root (and in any standalone composition). */
export const BoilDefs: React.FC = () => (
  <svg width={0} height={0} style={{position: 'absolute', left: 0, top: 0}}>
    <defs>
      {[0, 1, 2].map((i) => (
        <filter key={'c' + i} id={`boil-${i}`} x="-5%" y="-5%" width="110%" height="110%">
          <feTurbulence type="fractalNoise" baseFrequency="0.018" numOctaves={2} seed={i + 3} result="n" />
          <feDisplacementMap in="SourceGraphic" in2="n" scale={3} xChannelSelector="R" yChannelSelector="G" />
        </filter>
      ))}
      {[0, 1, 2].map((i) => (
        <filter key={'b' + i} id={`boil-bg-${i}`} x="-2%" y="-2%" width="104%" height="104%">
          <feTurbulence type="fractalNoise" baseFrequency="0.012" numOctaves={2} seed={i + 11} result="n" />
          <feDisplacementMap in="SourceGraphic" in2="n" scale={2} xChannelSelector="R" yChannelSelector="G" />
        </filter>
      ))}
    </defs>
  </svg>
);

/** `url(#boil-N)` for the current frame; N cycles 0..2 every 2 frames. */
export const useBoil = (bg = false): string => {
  const frame = useCurrentFrame();
  return `url(#boil${bg ? '-bg' : ''}-${Math.floor(frame / 2) % 3})`;
};

/* ------------------------------------------------------------------ */
/* Camera                                                               */
/* ------------------------------------------------------------------ */

export const Camera: React.FC<{
  zoom?: number;
  x?: number;
  y?: number;
  rotate?: number;
  children?: React.ReactNode;
}> = ({zoom = 1, x = 0, y = 0, rotate = 0, children}) => (
  <AbsoluteFill
    style={{
      transformOrigin: '50% 50%',
      translate: `${x}px ${y}px`,
      rotate: `${rotate}deg`,
      scale: String(zoom),
    }}
  >
    {children}
  </AbsoluteFill>
);

export const Shake: React.FC<{active: boolean; amount?: number; children?: React.ReactNode}> = ({
  active,
  amount = 8,
  children,
}) => {
  const frame = useCurrentFrame();
  const dx = active ? (random(`shake-x-${frame}`) * 2 - 1) * amount : 0;
  const dy = active ? (random(`shake-y-${frame}`) * 2 - 1) * amount : 0;
  return <AbsoluteFill style={{translate: `${dx}px ${dy}px`}}>{children}</AbsoluteFill>;
};

/** 2.39:1 bars. progress 1 = fully closed bars (~138 px each). */
export const Letterbox: React.FC<{progress: number}> = ({progress}) => {
  const h = 138 * Math.max(0, Math.min(1, progress));
  return (
    <>
      <div style={{position: 'absolute', left: 0, top: 0, width: W, height: h, background: '#000'}} />
      <div style={{position: 'absolute', left: 0, bottom: 0, width: W, height: h, background: '#000'}} />
    </>
  );
};

export const SpeedLines: React.FC<{direction: 'down' | 'left' | 'right'; opacity: number}> = ({
  direction,
  opacity,
}) => {
  const frame = useCurrentFrame();
  const lines = Array.from({length: 16}, (_, i) => {
    const r = random(`speed-${i}`);
    const len = 220 + random(`speedl-${i}`) * 380;
    const lane = r * (direction === 'down' ? W : H);
    const travel = direction === 'down' ? H + 600 : W + 600;
    const speed = 70 + random(`speeds-${i}`) * 70;
    const pos = ((i * 211 + frame * speed) % travel) - 300;
    const p = direction === 'right' ? pos : direction === 'left' ? travel - pos - 600 : pos;
    return direction === 'down' ? (
      <line key={i} x1={lane} y1={p} x2={lane} y2={p + len} />
    ) : (
      <line key={i} x1={p} y1={lane} x2={p + len} y2={lane} />
    );
  });
  return (
    <svg width={W} height={H} style={{position: 'absolute', left: 0, top: 0, opacity}}>
      <g stroke="#FFFFFF" strokeWidth={6} strokeLinecap="round">
        {lines}
      </g>
    </svg>
  );
};

/* ------------------------------------------------------------------ */
/* Portal (the ONLY glowing element)                                    */
/* ------------------------------------------------------------------ */

const spiral = (rot: number): string => {
  let d = '';
  for (let i = 0; i <= 28; i++) {
    const t = i / 28;
    const a = rot + t * 2.4;
    const r = 70 * (1 - t) + 10;
    d += `${i === 0 ? 'M' : 'L'}${(Math.cos(a) * r).toFixed(1)} ${(Math.sin(a) * r).toFixed(1)} `;
  }
  return d;
};

export const Portal: React.FC<{x: number; y: number; size: number; openAt: number; closeAt?: number}> = ({
  x,
  y,
  size,
  openAt,
  closeAt,
}) => {
  const frame = useCurrentFrame();
  const open = lerp(frame, [openAt, openAt + 7], [0, 1], Easing.back(1.7));
  const close = closeAt === undefined ? 1 : lerp(frame, [closeAt, closeAt + 6], [1, 0], Easing.in(Easing.quad));
  const s = frame < openAt ? 0 : Math.max(0, open * close);
  if (s < 0.005) return null;

  const rot = frame * 7;
  const phase = frame * 0.18;
  let rim = '';
  for (let i = 0; i <= 72; i++) {
    const a = (i / 72) * Math.PI * 2;
    const r = 92 * (1 + 0.06 * Math.sin(9 * a + phase) + 0.04 * Math.sin(5 * a - phase * 0.7));
    rim += `${i === 0 ? 'M' : 'L'}${(Math.cos(a) * r).toFixed(1)} ${(Math.sin(a) * r).toFixed(1)} `;
  }
  rim += 'Z';

  return (
    <div
      style={{
        position: 'absolute',
        left: x - size / 2,
        top: y - size / 2,
        width: size,
        height: size,
        scale: String(s),
        filter: `drop-shadow(0 0 22px ${C.portal}) drop-shadow(0 0 60px ${C.portal})`,
      }}
    >
      <svg width={size} height={size} viewBox="-100 -100 200 200" style={{overflow: 'visible'}}>
        {/* translucent flat wash over the scene */}
        <circle r={1600} fill={C.portal} opacity={0.12} />
        <path d={rim} fill={C.portal} stroke={C.line} strokeWidth={4} strokeLinejoin="round" />
        <circle r={72} fill="#1E9FBF" stroke={C.line} strokeWidth={3} />
        <g transform={`rotate(${rot})`} fill="none" stroke={C.portalCore} strokeWidth={6} strokeLinecap="round">
          {[0, 1, 2, 3].map((i) => (
            <path key={i} d={spiral((i * Math.PI) / 2)} />
          ))}
        </g>
        <circle r={26} fill={C.portalCore} stroke={C.line} strokeWidth={3} />
        {Array.from({length: 10}, (_, i) => {
          const life = (frame * 3 + i * 17) % 60;
          const a = (i / 10) * Math.PI * 2 + frame * 0.03 + random(`ps-${i}`) * 3;
          const r = 95 + life;
          return (
            <circle
              key={i}
              cx={Math.cos(a) * r}
              cy={Math.sin(a) * r}
              r={4 - life / 20}
              fill={C.portalCore}
              opacity={1 - life / 60}
            />
          );
        })}
      </svg>
    </div>
  );
};

/** 16-frame full-screen swirl. Use <Sequence from={cut-8} durationInFrames={16}><SwirlWipe/></Sequence>. */
export const SwirlWipe: React.FC = () => {
  const frame = useCurrentFrame();
  const p = frame <= 8 ? frame / 8 : (16 - frame) / 8;
  const eased = Easing.out(Easing.cubic)(Math.max(0, Math.min(1, p)));
  const R = eased * 1500;
  const rot = frame * 28;
  const arm = (a0: number) => {
    let d = '';
    for (let i = 0; i <= 24; i++) {
      const t = i / 24;
      const a = a0 + t * 3;
      const r = R * (0.15 + 0.85 * t);
      d += `${i === 0 ? 'M' : 'L'}${(Math.cos(a) * r).toFixed(1)} ${(Math.sin(a) * r).toFixed(1)} `;
    }
    return d;
  };
  return (
    <AbsoluteFill>
      <svg width={W} height={H} viewBox={`${-W / 2} ${-H / 2} ${W} ${H}`}>
        <circle r={R} fill={C.portal} stroke={C.line} strokeWidth={10} />
        <g transform={`rotate(${rot})`} fill="none" stroke={C.portalCore} strokeWidth={60 * eased} strokeLinecap="round">
          {[0, 1, 2, 3].map((i) => (
            <path key={i} d={arm((i * Math.PI) / 2)} />
          ))}
        </g>
        <circle r={R * 0.55} fill={C.line} />
      </svg>
    </AbsoluteFill>
  );
};

/* ------------------------------------------------------------------ */
/* CRT                                                                  */
/* ------------------------------------------------------------------ */

const SCREEN_W = 1704;
const SCREEN_H = 958;
const CONTENT_SCALE = SCREEN_W / W; // 0.8875

/**
 * Full-screen old TV. Children get a normal 1920x1080 canvas that is scaled into the screen.
 * onAt: turn-on frame (8 frames); offAt: turn-off frame (6 frames).
 */
export const Crt: React.FC<{children?: React.ReactNode; onAt?: number; offAt?: number}> = ({
  children,
  onAt = 0,
  offAt,
}) => {
  const frame = useCurrentFrame();
  const t = frame - onAt;
  let sx = 1;
  let sy = 1;
  let visible = true;
  if (t < 0) visible = false;
  else if (t < 3) {
    sx = lerp(t, [0, 3], [0.03, 1]);
    sy = 0.012;
  } else if (t < 8) sy = lerp(t, [3, 8], [0.012, 1]);
  if (offAt !== undefined && frame >= offAt) {
    const u = frame - offAt;
    if (u >= 6) visible = false;
    else if (u < 3) {
      sx = 1;
      sy = lerp(u, [0, 3], [1, 0.012], Easing.in(Easing.quad));
    } else {
      sy = 0.012;
      sx = lerp(u, [3, 6], [1, 0.02], Easing.in(Easing.quad));
    }
  }
  const thin = Math.max(0, 1 - (sy - 0.012) / 0.4);
  const sfx = [
    <Sequence key="on" from={onAt} layout="none">
      <Audio src={staticFile('sfx/crt-on.wav')} volume={0.6} />
    </Sequence>,
    offAt !== undefined ? (
      <Sequence key="off" from={offAt} layout="none">
        <Audio src={staticFile('sfx/crt-off.wav')} volume={0.6} />
      </Sequence>
    ) : null,
  ];

  return (
    <AbsoluteFill style={{background: C.brown}}>
      <svg width={0} height={0} style={{position: 'absolute'}}>
        <defs>
          <filter id="crt-fringe" x="0" y="0" width="100%" height="100%" colorInterpolationFilters="sRGB">
            <feColorMatrix in="SourceGraphic" type="matrix" values="1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0" result="r" />
            <feOffset in="r" dx={-1.5} dy={0} result="ro" />
            <feColorMatrix in="SourceGraphic" type="matrix" values="0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 1 0" result="g" />
            <feColorMatrix in="SourceGraphic" type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 0 0 1 0" result="b" />
            <feOffset in="b" dx={1.5} dy={0} result="bo" />
            <feBlend in="ro" in2="g" mode="screen" result="rg" />
            <feBlend in="rg" in2="bo" mode="screen" />
          </filter>
        </defs>
      </svg>
      {sfx}
      {/* bezel */}
      <div
        style={{
          position: 'absolute',
          left: (W - SCREEN_W) / 2 - 14,
          top: (H - SCREEN_H) / 2 - 14,
          width: SCREEN_W + 28,
          height: SCREEN_H + 28,
          borderRadius: 84,
          background: '#6F5C42',
          border: `8px solid ${C.line}`,
          boxSizing: 'border-box',
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: (W - SCREEN_W) / 2,
          top: (H - SCREEN_H) / 2,
          width: SCREEN_W,
          height: SCREEN_H,
          borderRadius: 70,
          overflow: 'hidden',
          background: '#000',
          scale: `${visible ? sx : 0} ${visible ? sy : 0}`,
          transformOrigin: '50% 50%',
        }}
      >
        {visible ? (
          <>
            <div style={{position: 'absolute', left: 0, top: 0, width: W, height: H, transformOrigin: '0 0', scale: String(CONTENT_SCALE), filter: 'url(#crt-fringe)'}}>
              {children}
            </div>
            {/* scanlines + vignette (CRT texture: the only gradient exception) */}
            <div
              style={{
                position: 'absolute',
                inset: 0,
                background: 'repeating-linear-gradient(to bottom, rgba(0,0,0,0.16) 0px, rgba(0,0,0,0.16) 2px, rgba(0,0,0,0) 2px, rgba(0,0,0,0) 5px)',
              }}
            />
            <div
              style={{
                position: 'absolute',
                inset: 0,
                background: 'radial-gradient(ellipse at center, rgba(0,0,0,0) 55%, rgba(0,0,0,0.5) 100%)',
              }}
            />
            <div style={{position: 'absolute', inset: 0, background: '#FFFFFF', opacity: thin * 0.9}} />
          </>
        ) : null}
      </div>
      {/* bezel knobs */}
      <div style={{position: 'absolute', right: 26, top: H / 2 - 60, width: 36, height: 36, borderRadius: 18, background: C.cardboard, border: `6px solid ${C.line}`, boxSizing: 'border-box'}} />
      <div style={{position: 'absolute', right: 26, top: H / 2 + 0, width: 36, height: 36, borderRadius: 18, background: C.cardboard, border: `6px solid ${C.line}`, boxSizing: 'border-box'}} />
    </AbsoluteFill>
  );
};
