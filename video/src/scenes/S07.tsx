import React from 'react';
import {AbsoluteFill, random, useCurrentFrame} from 'remotion';
import {BALOO, C, H, VT323, W} from '../theme';
import {lerp, talkOpen, twos} from '../lib/anim';
import {Camera, useBoil} from '../fx';
import {DeepSeek, Herring, Opus} from '../characters';
import {Line, ScreenTag, Sfx, SFX} from '../ui';
import {PaperSlip} from '../sets';
import {Easing} from 'remotion';

const Room: React.FC = () => {
  const boil = useBoil(true);
  const panels: React.ReactNode[] = [];
  for (let r = 0; r < 3; r++) {
    for (let c = 0; c < 7; c++) {
      panels.push(
        <g key={`${r}-${c}`} transform={`translate(${60 + c * 264} ${50 + r * 180})`}>
          <rect width={248} height={160} rx={10} fill={C.line} stroke={C.line} strokeWidth={6} />
          <rect x={8} y={8} width={232} height={144} rx={6} fill="#14301F" />
          <text x={124} y={92} textAnchor="middle" fontFamily={VT323} fontSize={64} fill={C.okGreen}>
            200 OK ✓
          </text>
          <rect x={20} y={118} width={60 + ((c * 37 + r * 53) % 120)} height={10} fill={C.okGreen} opacity={0.6} />
        </g>,
      );
    }
  }
  return (
    <svg width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
      <g filter={boil}>
        <rect width={W} height={H} fill={C.mint} />
        <rect y={780} width={W} height={300} fill={C.pink} />
        <rect y={770} width={W} height={20} fill={C.okGreen} stroke={C.line} strokeWidth={6} />
        {panels}
      </g>
    </svg>
  );
};

const Coin: React.FC<{x: number; y: number; s?: number; spin: number}> = ({x, y, s = 1, spin}) => (
  <g transform={`translate(${x} ${y}) scale(${s})`}>
    <ellipse rx={36 * Math.max(0.3, Math.abs(Math.cos(spin)))} ry={36} fill={C.gold} stroke={C.line} strokeWidth={6} />
    <ellipse rx={22 * Math.max(0.3, Math.abs(Math.cos(spin)))} ry={22} fill="none" stroke="#C99A2E" strokeWidth={5} />
  </g>
);

const Rain: React.FC<{count: number; avoid?: boolean}> = ({count}) => {
  const frame = useCurrentFrame();
  const coins: React.ReactNode[] = [];
  for (let i = 0; i < count; i++) {
    const P = 54 + Math.floor(random(`cp-${i}`) * 20);
    const off = random(`co-${i}`) * P;
    const x = 80 + random(`cx-${i}`) * 1760;
    const p = ((frame + off) % P) / P;
    const y = -60 + p * 1000;
    const spin = frame * 0.5 + i;
    if (p < 0.45) {
      coins.push(<Coin key={i} x={x} y={y} spin={spin} />);
    } else {
      const d = (p - 0.45) * P * 4;
      coins.push(<Coin key={i + 'a'} x={x - d} y={y} s={0.7} spin={spin} />);
      coins.push(<Coin key={i + 'b'} x={x + d} y={y} s={0.7} spin={spin + 1} />);
    }
  }
  return (
    <svg width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
      {coins}
    </svg>
  );
};

const Register: React.FC<{x: number; y: number}> = ({x, y}) => {
  const boil = useBoil(true);
  return (
    <svg width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
      <g filter={boil} transform={`translate(${x} ${y})`}>
        <rect x={-260} y={-230} width={520} height={230} rx={14} fill={C.pink} stroke={C.line} strokeWidth={8} />
        <path d="M-230 -230 L-170 -400 L170 -400 L230 -230 Z" fill={C.gold} stroke={C.line} strokeWidth={8} strokeLinejoin="round" />
        <rect x={-130} y={-380} width={260} height={90} rx={8} fill="#14301F" stroke={C.line} strokeWidth={6} />
        <text x={0} y={-312} textAnchor="middle" fontFamily={VT323} fontSize={62} fill={C.okGreen}>
          200 OK ✓
        </text>
        <rect x={-200} y={-150} width={400} height={26} rx={6} fill={C.line} />
        <rect x={-200} y={-100} width={180} height={50} rx={8} fill={C.okCream} stroke={C.line} strokeWidth={6} />
        <rect x={20} y={-100} width={180} height={50} rx={8} fill={C.okGreen} stroke={C.line} strokeWidth={6} />
      </g>
    </svg>
  );
};

const Pile: React.FC = () => {
  const frame = useCurrentFrame();
  const boil = useBoil(true);
  const coins: React.ReactNode[] = [];
  for (let i = 0; i < 26; i++) {
    const row = Math.floor(i / 9);
    coins.push(<Coin key={i} x={1190 + (i % 9) * 56 - row * 28 + (random(`pj-${i}`) - 0.5) * 12} y={880 - row * 40} spin={0.4 + i * 0.7} />);
  }
  void frame;
  return (
    <svg width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
      <g filter={boil}>{coins}</g>
    </svg>
  );
};

export const S07: React.FC = () => {
  const frame = useCurrentFrame();
  const bonk = lerp(frame, [56, 58, 64], [0, 1, 0], Easing.linear);
  const coinY = frame < 56 ? lerp(frame, [44, 56], [-80, 330], Easing.in(Easing.quad)) : 330 - (frame - 56) * 18 + (frame - 56) ** 2 * 1.2;
  const coinX = 960 + (frame >= 56 ? (frame - 56) * 22 : 0);
  const herringUp = lerp(frame, [124, 130], [0, 1]);
  const receiptY = lerp(frame, [100, 118], [0, 1]);

  return (
    <AbsoluteFill>
      <Room />
      {frame < 48 ? (
        <Camera zoom={lerp(frame, [0, 48], [1, 1.06], Easing.linear)}>
          <Rain count={Math.round(lerp(frame, [8, 32], [0, 16]))} />
          <Opus x={640} y={980} height={520} expr="deadpan" talking={talkOpen(frame, 4, 44)} />
          <DeepSeek x={1320} y={980} height={330} expr="neutral" spout="spray" />
        </Camera>
      ) : null}
      {frame >= 48 && frame < 96 ? (
        <>
          <Rain count={10} />
          <DeepSeek
            x={960}
            y={1080}
            height={780}
            expr={frame < 56 ? 'neutral' : frame < 70 ? 'surprised' : 'panic'}
            spout={frame < 56 ? 'off' : 'spray'}
            squash={bonk}
            talking={talkOpen(frame, 64, 49)}
          />
          <svg width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
            {frame >= 44 && frame < 80 ? <Coin x={coinX} y={coinY} s={1.6} spin={frame * 0.6} /> : null}
          </svg>
        </>
      ) : null}
      {frame >= 96 ? (
        <>
          <Register x={560} y={900} />
          {/* receipt printing out of the register */}
          <div style={{position: 'absolute', left: 0, top: 0, width: W, height: H, clipPath: `inset(0 0 ${H - 500}px 0)`}}>
            <PaperSlip x={560} y={370 + 150 * (1 - receiptY)} text={'ORDER #4471 · SOCKS · CHARGED ×2'} rotate={-2} />
          </div>
          <Herring x={1400} y={820 + 150 * (1 - herringUp)} height={190} squeak={frame >= 130 && frame < 146} />
          <Pile />
          <ScreenTag x={960} y={120} text="SILENT HARM: HTTP 200 outside, double charges inside" appearAt={112} />
        </>
      ) : null}

      <Line who="opus" from={4} dur={58} text="Everything is green." />
      <Line who="deepseek" from={64} dur={49} text="Then why is it raining money?!" />
      <Sfx src={SFX.boing} at={56} />
      <Sfx src={SFX.tick} at={100} />
      <Sfx src={SFX.tick} at={106} />
      <Sfx src={SFX.tick} at={112} />
      <Sfx src={SFX.squeak} at={128} />
    </AbsoluteFill>
  );
};

void BALOO;
void twos;
