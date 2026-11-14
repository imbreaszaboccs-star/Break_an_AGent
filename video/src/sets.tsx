import React from 'react';
import {random, useCurrentFrame} from 'remotion';
import {BALOO, C, H, VT323, W} from './theme';
import {useBoil} from './fx';
import {twos} from './lib/anim';

const BG = 7; // background outline

/* ------------------------------------------------------------------ */
/* Night exterior                                                       */
/* ------------------------------------------------------------------ */

export const NightExterior: React.FC<{lit?: boolean}> = ({lit = true}) => {
  const boil = useBoil(true);
  const cols = 8;
  const rows = 6;
  const windows: React.ReactNode[] = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const on = lit && r === 2 && c === 5;
      windows.push(
        <rect
          key={`${r}-${c}`}
          x={600 + c * 90}
          y={440 + r * 90}
          width={54}
          height={54}
          fill={on ? C.amber : C.sky1}
          stroke={C.line}
          strokeWidth={BG}
        />,
      );
    }
  }
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{position: 'absolute', left: 0, top: 0}}>
      <g filter={boil}>
        <rect width={W} height={H} fill={C.sky1} />
        <rect y={260} width={W} height={300} fill={C.sky2} />
        <rect y={520} width={W} height={300} fill={C.sky3} />
        {/* distant skyline */}
        <path d="M0 760 L0 640 L120 640 L120 590 L220 590 L220 660 L330 660 L330 610 L1500 610 L1500 650 L1620 650 L1620 580 L1740 580 L1740 640 L1920 640 L1920 760 Z" fill={C.sky2} stroke={C.line} strokeWidth={BG} />
        {/* ground */}
        <rect y={900} width={W} height={180} fill="#111A30" />
        <line x1={0} x2={W} y1={900} y2={900} stroke={C.line} strokeWidth={BG} />
        {/* datacenter block */}
        <rect x={560} y={380} width={800} height={540} fill={C.building} stroke={C.line} strokeWidth={BG} />
        <rect x={1240} y={380} width={120} height={540} fill={C.buildingDark} />
        <rect x={560} y={380} width={800} height={540} fill="none" stroke={C.line} strokeWidth={BG} />
        <rect x={540} y={350} width={840} height={40} fill={C.buildingDark} stroke={C.line} strokeWidth={BG} />
        {windows}
        <rect x={900} y={800} width={120} height={120} fill={C.sky1} stroke={C.line} strokeWidth={BG} />
        <rect x={700} y={290} width={520} height={64} fill={C.sky1} stroke={C.line} strokeWidth={BG} />
        <text x={960} y={324} textAnchor="middle" dominantBaseline="central" fontFamily={VT323} fontSize={52} fill={C.amber}>
          DATACENTER 7
        </text>
        {/* antenna */}
        <line x1={1280} y1={350} x2={1280} y2={250} stroke={C.line} strokeWidth={BG} />
        <circle cx={1280} cy={244} r={10} fill={C.fireRed} stroke={C.line} strokeWidth={5} />
      </g>
    </svg>
  );
};

/* ------------------------------------------------------------------ */
/* Appliances, racks                                                    */
/* ------------------------------------------------------------------ */

const Sparks: React.FC<{x: number; y: number; seed: string}> = ({x, y, seed}) => {
  const f = twos(useCurrentFrame());
  if (Math.floor(f / 2) % 3 === 2) return null;
  const pts = Array.from({length: 7}, (_, i) => {
    const px = x + (i % 2 ? 18 : -18) * random(`${seed}-a-${f}-${i}`) + i * 4 - 12;
    const py = y - i * 11 - random(`${seed}-b-${f}-${i}`) * 8;
    return `${px.toFixed(1)},${py.toFixed(1)}`;
  }).join(' ');
  return (
    <>
      <polyline points={pts} fill="none" stroke={C.line} strokeWidth={9} strokeLinejoin="round" />
      <polyline points={pts} fill="none" stroke={C.gold} strokeWidth={4} strokeLinejoin="round" />
    </>
  );
};

/** Stack of microwaves/toasters. (x,y) = bottom-center. */
export const Rack: React.FC<{x: number; y: number; label: string; status: 'fire' | 'ok'; scale?: number}> = ({
  x,
  y,
  label,
  status,
  scale = 1,
}) => {
  const fire = status === 'fire';
  const f = twos(useCurrentFrame());
  const lightOn = fire ? Math.floor(f / 2) % 2 === 0 : true;
  const unit = (i: number) => {
    const ty = -96 * (i + 1);
    const toaster = i === 1;
    return (
      <g key={i} transform={`translate(0 ${ty})`}>
        <rect x={-90} y={0} width={180} height={90} rx={toaster ? 22 : 8} fill={C.rack} stroke={C.line} strokeWidth={BG} />
        <rect x={-90} y={46} width={180} height={44} rx={toaster ? 20 : 4} fill={C.rackDark} />
        <rect x={-90} y={0} width={180} height={90} rx={toaster ? 22 : 8} fill="none" stroke={C.line} strokeWidth={BG} />
        {toaster ? (
          <>
            <rect x={-60} y={14} width={90} height={12} rx={6} fill={C.line} />
            <rect x={-60} y={34} width={90} height={12} rx={6} fill={C.line} />
            <rect x={50} y={20} width={22} height={34} rx={4} fill={C.cardboard} stroke={C.line} strokeWidth={5} />
          </>
        ) : (
          <>
            <rect x={-74} y={14} width={104} height={62} rx={4} fill={fire && i === 0 ? C.brown : '#2E3B3A'} stroke={C.line} strokeWidth={5} />
            <circle cx={56} cy={28} r={9} fill={C.cardboard} stroke={C.line} strokeWidth={5} />
            <circle cx={56} cy={56} r={9} fill={C.cardboard} stroke={C.line} strokeWidth={5} />
          </>
        )}
      </g>
    );
  };
  return (
    <g transform={`translate(${x} ${y}) scale(${scale})`}>
      <ellipse cx={0} cy={4} rx={110} ry={12} fill={C.brown} opacity={0.5} />
      {[0, 1, 2].map(unit)}
      {/* label plate */}
      <rect x={-96} y={-396} width={192} height={44} rx={6} fill={C.boardCream} stroke={C.line} strokeWidth={BG} />
      <text x={0} y={-373} textAnchor="middle" dominantBaseline="central" fontFamily={VT323} fontSize={34} fill={C.line}>
        {label}
      </text>
      {/* status light */}
      <circle cx={0} cy={-420} r={14} fill={fire ? (lightOn ? C.fireRed : '#7A2024') : C.okCream} stroke={C.line} strokeWidth={BG - 1} />
      {fire ? <Sparks x={-30} y={-290} seed={label} /> : null}
      {fire ? <Sparks x={40} y={-110} seed={label + 'b'} /> : null}
    </g>
  );
};

export const SandboxHub: React.FC<{racks?: Record<string, 'fire' | 'ok'>; tvOn?: boolean}> = ({racks = {}, tvOn = false}) => {
  const boil = useBoil(true);
  const frame = useCurrentFrame();
  const st = (k: string): 'fire' | 'ok' => racks[k] ?? 'ok';
  const lamp = Math.floor(frame / 2) % 3;
  void lamp;
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{position: 'absolute', left: 0, top: 0}}>
      <g filter={boil}>
        <rect width={W} height={H} fill={C.wall} />
        <rect y={800} width={W} height={280} fill={C.floor} />
        <rect y={780} width={W} height={24} fill={C.brown} stroke={C.line} strokeWidth={BG} />
        {/* floor boards */}
        {[880, 960, 1040].map((yy) => (
          <line key={yy} x1={0} x2={W} y1={yy} y2={yy} stroke={C.brown} strokeWidth={4} opacity={0.5} />
        ))}
        {/* TV on the wall */}
        <rect x={760} y={150} width={400} height={300} rx={34} fill={C.brown} stroke={C.line} strokeWidth={BG} />
        <rect x={790} y={180} width={340} height={240} rx={28} fill={tvOn ? C.sage : '#2E3B3A'} stroke={C.line} strokeWidth={BG} />
        {tvOn ? (
          <>
            <rect x={820} y={210} width={120} height={80} fill={C.cream} />
            <rect x={960} y={250} width={140} height={30} fill={C.coral} />
          </>
        ) : null}
        <circle cx={1136} cy={430} r={7} fill={C.cardboard} stroke={C.line} strokeWidth={4} />
        <line x1={900} y1={150} x2={860} y2={90} stroke={C.line} strokeWidth={BG} strokeLinecap="round" />
        <line x1={1020} y1={150} x2={1070} y2={90} stroke={C.line} strokeWidth={BG} strokeLinecap="round" />
        {/* racks, back to front */}
        <Rack x={560} y={868} label="PAYMENTS" status={st('PAYMENTS')} scale={0.78} />
        <Rack x={1360} y={868} label="GATEWAY" status={st('GATEWAY')} scale={0.78} />
        <Rack x={350} y={900} label="SEARCH-SVC" status={st('SEARCH-SVC')} scale={0.9} />
        <Rack x={1570} y={900} label="REDIS-MAIN" status={st('REDIS-MAIN')} scale={0.9} />
        <Rack x={140} y={940} label="AUTH-SVC" status={st('AUTH-SVC')} scale={1} />
        <Rack x={1780} y={940} label="MAIL" status={st('MAIL')} scale={1} />
        {/* spaghetti cables */}
        <path d="M200 900 C400 1010 560 840 760 960 S1000 1030 1180 940 S1480 1020 1700 930" fill="none" stroke={C.line} strokeWidth={14} strokeLinecap="round" />
        <path d="M200 900 C400 1010 560 840 760 960 S1000 1030 1180 940 S1480 1020 1700 930" fill="none" stroke={C.coral} strokeWidth={6} strokeLinecap="round" />
        <path d="M300 940 C460 1050 700 900 880 1010 S1260 960 1500 1040" fill="none" stroke={C.line} strokeWidth={14} strokeLinecap="round" />
        <path d="M300 940 C460 1050 700 900 880 1010 S1260 960 1500 1040" fill="none" stroke={C.blue} strokeWidth={6} strokeLinecap="round" />
        <path d="M620 700 C680 780 760 760 780 860 M1300 700 C1240 790 1170 760 1150 860" fill="none" stroke={C.line} strokeWidth={BG} strokeLinecap="round" />
        {/* dusty desk lamp */}
        <g transform="translate(1000 930)">
          <ellipse cx={0} cy={0} rx={50} ry={12} fill={C.brown} stroke={C.line} strokeWidth={BG} />
          <path d="M0 0 L-30 -80 L40 -120" fill="none" stroke={C.line} strokeWidth={14} strokeLinecap="round" strokeLinejoin="round" />
          <path d="M0 0 L-30 -80 L40 -120" fill="none" stroke={C.grey} strokeWidth={5} strokeLinecap="round" strokeLinejoin="round" />
          <path d="M20 -140 L80 -150 L66 -100 Z" fill={C.cream} stroke={C.line} strokeWidth={BG} strokeLinejoin="round" />
          <path d="M-20 -6 q20 -10 40 0" fill="none" stroke={C.floor} strokeWidth={5} opacity={0.8} />
        </g>
      </g>
    </svg>
  );
};

/* ------------------------------------------------------------------ */
/* Box, terminal, clock, lever, paper                                   */
/* ------------------------------------------------------------------ */

/** Cardboard box, (x,y) = bottom-center. flaps 0 = open, 1 = closed. */
export const Box: React.FC<{x: number; y: number; label?: string; flaps: number}> = ({x, y, label = 'SANDBOX', flaps}) => {
  const boil = useBoil(true);
  const bw = 560;
  const bh = 380;
  const ang = (1 - flaps) * 118;
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{position: 'absolute', left: 0, top: 0}}>
      <g filter={boil} transform={`translate(${x} ${y})`}>
        {/* back flaps (open state shows inside) */}
        <g transform={`translate(${-bw / 2} ${-bh}) rotate(${-ang})`}>
          <rect x={0} y={-70} width={bw / 2 + 2} height={70} fill={C.floor} stroke={C.line} strokeWidth={BG} />
        </g>
        <g transform={`translate(${bw / 2} ${-bh}) rotate(${ang})`}>
          <rect x={-bw / 2 - 2} y={-70} width={bw / 2 + 2} height={70} fill={C.floor} stroke={C.line} strokeWidth={BG} />
          <rect x={-bw / 2 - 2} y={-70} width={30} height={70} fill={C.brown} opacity={0.35} />
        </g>
        <rect x={-bw / 2} y={-bh} width={bw} height={bh} fill={C.cardboard} stroke={C.line} strokeWidth={BG} />
        <rect x={bw / 2 - 90} y={-bh} width={90} height={bh} fill={C.brown} opacity={0.35} />
        <rect x={-40} y={-bh} width={80} height={bh * 0.55} fill="#E6D3A8" stroke={C.line} strokeWidth={BG - 2} />
        <text x={0} y={-bh * 0.38} textAnchor="middle" dominantBaseline="central" fontFamily={BALOO} fontWeight={800} fontSize={72} fill={C.line}>
          {label}
        </text>
        <text x={-bw / 2 + 24} y={-40} dominantBaseline="central" fontFamily={VT323} fontSize={36} fill={C.line}>
          THIS SIDE UP ↑
        </text>
        <text x={bw / 2 - 24} y={-40} textAnchor="end" dominantBaseline="central" fontFamily={VT323} fontSize={36} fill={C.stampRed}>
          DO NOT OPEN
        </text>
        <rect x={-bw / 2} y={-bh} width={bw} height={bh} fill="none" stroke={C.line} strokeWidth={BG} />
      </g>
    </svg>
  );
};

/** Typewriter wired to a toaster. (x,y) = bottom-center. */
export const Terminal: React.FC<{x: number; y: number; scale?: number}> = ({x, y, scale = 1}) => {
  const boil = useBoil(true);
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{position: 'absolute', left: 0, top: 0}}>
      <g filter={boil} transform={`translate(${x} ${y}) scale(${scale})`}>
        {/* toaster */}
        <rect x={60} y={-150} width={170} height={120} rx={28} fill={C.rack} stroke={C.line} strokeWidth={BG} />
        <rect x={80} y={-136} width={110} height={12} rx={6} fill={C.line} />
        <rect x={80} y={-114} width={110} height={12} rx={6} fill={C.line} />
        <rect x={200} y={-100} width={16} height={36} rx={4} fill={C.cardboard} stroke={C.line} strokeWidth={4} />
        {/* paper out of toaster */}
        <rect x={90} y={-220} width={80} height={90} fill={C.boardCream} stroke={C.line} strokeWidth={5} />
        {/* typewriter */}
        <rect x={-190} y={-60} width={220} height={60} rx={12} fill={C.brown} stroke={C.line} strokeWidth={BG} />
        <path d="M-175 -60 L-150 -112 L10 -112 L20 -60 Z" fill={C.cardboard} stroke={C.line} strokeWidth={BG} strokeLinejoin="round" />
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <circle key={i} cx={-140 + i * 24} cy={-84} r={8} fill={C.boardCream} stroke={C.line} strokeWidth={4} />
        ))}
        <rect x={-180} y={-140} width={170} height={30} rx={6} fill={C.grey} stroke={C.line} strokeWidth={BG - 1} />
        <rect x={-150} y={-190} width={110} height={56} fill={C.boardCream} stroke={C.line} strokeWidth={5} />
        {/* cable */}
        <path d="M30 -30 C50 20 40 20 62 -40" fill="none" stroke={C.line} strokeWidth={12} strokeLinecap="round" />
        <path d="M30 -30 C50 20 40 20 62 -40" fill="none" stroke={C.coral} strokeWidth={5} strokeLinecap="round" />
      </g>
    </svg>
  );
};

/** VT323 sim clock, centered on (x,y). */
export const SimClock: React.FC<{x: number; y: number; t: number}> = ({x, y, t}) => (
  <div
    style={{
      position: 'absolute',
      left: x,
      top: y,
      translate: '-50% -50%',
      padding: '6px 34px',
      background: C.line,
      color: C.amber,
      border: `${BG}px solid ${C.line}`,
      outline: `4px solid ${C.boardCream}`,
      outlineOffset: -12,
      borderRadius: 14,
      fontFamily: VT323,
      fontSize: 84,
      lineHeight: 1,
      whiteSpace: 'pre',
    }}
  >
    {`t = ${String(Math.round(t)).padStart(2, '0')}`}
  </div>
);

/** Lever, (x,y) = bottom-center of the base. pulled 0 = up, 1 = down. */
export const Lever: React.FC<{x: number; y: number; pulled: number}> = ({x, y, pulled}) => {
  const boil = useBoil(true);
  const a = -38 + 76 * pulled;
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{position: 'absolute', left: 0, top: 0}}>
      <g filter={boil} transform={`translate(${x} ${y})`}>
        <rect x={-90} y={-50} width={180} height={50} rx={10} fill={C.brown} stroke={C.line} strokeWidth={BG} />
        <rect x={-60} y={-80} width={120} height={36} rx={18} fill={C.line} />
        <g transform={`translate(0 -62) rotate(${a})`}>
          <line x1={0} y1={0} x2={0} y2={-170} stroke={C.line} strokeWidth={22} strokeLinecap="round" />
          <line x1={0} y1={0} x2={0} y2={-170} stroke={C.grey} strokeWidth={8} strokeLinecap="round" />
          <circle cx={0} cy={-180} r={26} fill={C.fireRed} stroke={C.line} strokeWidth={BG} />
        </g>
        <circle cx={0} cy={-62} r={16} fill={C.cardboard} stroke={C.line} strokeWidth={5} />
      </g>
    </svg>
  );
};

/** Torn paper slip with VT323 text, centered on (x,y). */
export const PaperSlip: React.FC<{x: number; y: number; text: string; rotate?: number}> = ({x, y, text, rotate = 0}) => {
  const lines = text.split('\n');
  const fs = 32;
  const w = Math.max(...lines.map((l) => l.length)) * fs * 0.42 + 44;
  const h = lines.length * fs * 0.95 + 36;
  const teeth = Math.max(4, Math.round(w / 22));
  let tear = '';
  for (let i = 0; i <= teeth; i++) tear += ` L${(w - (i * w) / teeth).toFixed(1)} ${(h + (i % 2 ? 0 : 10)).toFixed(1)}`;
  return (
    <svg
      width={w + 20}
      height={h + 30}
      viewBox={`-10 -10 ${w + 20} ${h + 30}`}
      style={{position: 'absolute', left: x - (w + 20) / 2, top: y - (h + 30) / 2, rotate: `${rotate}deg`, overflow: 'visible'}}
    >
      <path d={`M0 0 L${w} 0 L${w} ${h}${tear} Z`} fill={C.boardCream} stroke={C.line} strokeWidth={5} strokeLinejoin="round" />
      {lines.map((l, i) => (
        <text key={i} x={22} y={26 + fs * 0.7 + i * fs * 0.95} fontFamily={VT323} fontSize={fs} fill={C.line}>
          {l}
        </text>
      ))}
    </svg>
  );
};
