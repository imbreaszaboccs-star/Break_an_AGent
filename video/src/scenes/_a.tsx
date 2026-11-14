import React from 'react';
import {C, VT323} from '../theme';
import {twos} from '../lib/anim';
import {useCurrentFrame} from 'remotion';

/** Flat cartoon flame, (x,y) = base-center. Flickers on twos. */
export const Flame: React.FC<{x: number; y: number; size?: number; seed?: number}> = ({x, y, size = 1, seed = 0}) => {
  const f = Math.floor(twos(useCurrentFrame()) / 2) + seed;
  const k = f % 3;
  const h = [92, 108, 80][k] * size;
  const w = 34 * size;
  const sway = [0, 8, -8][k] * size;
  return (
    <g transform={`translate(${x} ${y})`}>
      <path
        d={`M${-w} 0 C${-w * 1.1} ${-h * 0.4} ${-w * 0.3} ${-h * 0.5} ${sway} ${-h} C${w * 0.3} ${-h * 0.5} ${w * 1.1} ${-h * 0.4} ${w} 0 Z`}
        fill={C.fireRed}
        stroke={C.line}
        strokeWidth={6}
        strokeLinejoin="round"
      />
      <path
        d={`M${-w * 0.5} 0 C${-w * 0.6} ${-h * 0.25} ${-w * 0.1} ${-h * 0.35} ${sway * 0.6} ${-h * 0.62} C${w * 0.2} ${-h * 0.35} ${w * 0.6} ${-h * 0.25} ${w * 0.5} 0 Z`}
        fill={C.amber}
      />
    </g>
  );
};

/** Flat 4-point sparkle (no glow). */
export const Sparkle: React.FC<{x: number; y: number; r: number}> = ({x, y, r}) => (
  <path
    d={`M${x} ${y - r} L${x + r * 0.28} ${y - r * 0.28} L${x + r} ${y} L${x + r * 0.28} ${y + r * 0.28} L${x} ${y + r} L${x - r * 0.28} ${y + r * 0.28} L${x - r} ${y} L${x - r * 0.28} ${y - r * 0.28} Z`}
    fill={C.boardCream}
    stroke={C.line}
    strokeWidth={5}
    strokeLinejoin="round"
  />
);

/** Hand-held sign on a stick. (x,y) = bottom of the stick, board sits above it. */
export const SignBoard: React.FC<{x: number; y: number; text: string; hop?: number}> = ({x, y, text, hop = 0}) => {
  const fs = 40;
  const w = text.length * fs * 0.42 + 60;
  return (
    <div style={{position: 'absolute', left: x - w / 2, top: y - 110 + hop, width: w, height: 110}}>
      <div style={{position: 'absolute', left: w / 2 - 6, top: 62, width: 12, height: 60, background: C.line}} />
      <div
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          width: w,
          height: 66,
          boxSizing: 'border-box',
          background: C.boardCream,
          border: `7px solid ${C.line}`,
          fontFamily: VT323,
          fontSize: fs,
          lineHeight: '52px',
          textAlign: 'center',
          color: C.line,
          whiteSpace: 'pre',
        }}
      >
        {text}
      </div>
    </div>
  );
};
