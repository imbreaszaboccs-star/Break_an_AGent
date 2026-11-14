import React, {useId} from 'react';
import {random, useCurrentFrame} from 'remotion';
import {BALOO, C, VT323} from './theme';
import {useBoil} from './fx';
import {twos} from './lib/anim';

export type Expr = 'neutral' | 'deadpan' | 'surprised' | 'panic' | 'happy' | 'sad' | 'smug';

type Base = {
  x: number;
  y: number;
  height?: number;
  flip?: boolean;
  expr?: Expr;
  talking?: boolean;
  look?: [number, number];
  blink?: boolean;
  squash?: number;
  rotate?: number;
  style?: React.CSSProperties;
};

const SW = 10; // character outline
const SD = 6; // detail outline

/** Absolute wrapper anchored at the feet (bottom-center). */
const Wrap: React.FC<{
  x: number;
  y: number;
  vbW: number;
  vbH: number;
  height: number;
  flip?: boolean;
  squash?: number;
  rotate?: number;
  style?: React.CSSProperties;
  children: React.ReactNode;
}> = ({x, y, vbW, vbH, height, flip, squash = 0, rotate = 0, style, children}) => {
  const boil = useBoil();
  const w = (vbW / vbH) * height;
  const sy = 1 - 0.22 * squash;
  const sx = (1 + 0.22 * squash) * (flip ? -1 : 1);
  return (
    <div
      style={{
        position: 'absolute',
        left: x - w / 2,
        top: y - height,
        width: w,
        height,
        transformOrigin: '50% 100%',
        rotate: `${rotate}deg`,
        scale: `${sx} ${sy}`,
        ...style,
      }}
    >
      <svg width={w} height={height} viewBox={`0 0 ${vbW} ${vbH}`} style={{overflow: 'visible'}}>
        <g filter={boil}>{children}</g>
      </svg>
    </div>
  );
};

/* ------------------------------------------------------------------ */
/* Shared face                                                          */
/* ------------------------------------------------------------------ */

type ExprDef = {lid: number; lift: number; tilt: number; mouth: 'line' | 'smile' | 'frown' | 'o' | 'wide' | 'smirk'; pupil: number; browL?: number};
const EXPR: Record<Expr, ExprDef> = {
  neutral: {lid: 0.15, lift: 0, tilt: 0, mouth: 'line', pupil: 1},
  deadpan: {lid: 0.5, lift: 4, tilt: 0, mouth: 'line', pupil: 1},
  surprised: {lid: 0, lift: -14, tilt: 0, mouth: 'o', pupil: 0.8},
  panic: {lid: 0, lift: -14, tilt: -9, mouth: 'wide', pupil: 0.7},
  happy: {lid: 0.2, lift: -5, tilt: 0, mouth: 'smile', pupil: 1},
  sad: {lid: 0.35, lift: 2, tilt: -11, mouth: 'frown', pupil: 1},
  smug: {lid: 0.55, lift: 0, tilt: 3, mouth: 'smirk', pupil: 1, browL: -12},
};

type FaceProps = {
  cx1: number;
  cx2: number;
  ey: number;
  rx: number;
  ry: number;
  mx: number;
  my: number;
  mw: number;
  expr: Expr;
  talking: boolean;
  look: [number, number];
  blink: boolean;
  lidColor: string;
  lidMul?: number;
  pupilR: number;
  jitter?: number;
  browY: number;
  mouthFill?: string;
};

const Face: React.FC<FaceProps> = (p) => {
  const frame = useCurrentFrame();
  const f = twos(frame);
  const id = useId().replace(/:/g, '_');
  const d = EXPR[p.expr];
  const lid = p.blink ? 1.08 : d.lid * (p.lidMul ?? 1);
  const open = p.talking && Math.floor(f / 4) % 2 === 0;
  const jx = p.jitter ? (random(`j-x-${f}`) * 2 - 1) * p.jitter : 0;
  const jy = p.jitter ? (random(`j-y-${f}`) * 2 - 1) * p.jitter : 0;
  const px = (p.look[0] * p.rx * 0.45 + jx) * 1;
  const py = (p.look[1] * p.ry * 0.45 + jy) * 1;

  const eye = (cx: number, k: number, left: boolean) => {
    const lidH = 2 * p.ry * Math.min(lid, 1.08);
    const top = p.ey - p.ry;
    return (
      <g key={k}>
        <clipPath id={`${id}-e${k}`}>
          <ellipse cx={cx} cy={p.ey} rx={p.rx} ry={p.ry} />
        </clipPath>
        <ellipse cx={cx} cy={p.ey} rx={p.rx} ry={p.ry} fill={C.eye} />
        <circle cx={cx + px} cy={p.ey + py} r={p.pupilR * d.pupil} fill={C.line} />
        <g clipPath={`url(#${id}-e${k})`}>
          {lid > 0 ? (
            <>
              <rect x={cx - p.rx - 4} y={top - 4} width={p.rx * 2 + 8} height={lidH + 4} fill={p.lidColor} />
              <line x1={cx - p.rx - 4} x2={cx + p.rx + 4} y1={top + lidH} y2={top + lidH} stroke={C.line} strokeWidth={SD} />
            </>
          ) : null}
        </g>
        <ellipse cx={cx} cy={p.ey} rx={p.rx} ry={p.ry} fill="none" stroke={C.line} strokeWidth={SD} />
        {/* brow */}
        {(() => {
          const lift = d.lift + (left ? d.browL ?? 0 : 0);
          const outerX = left ? cx - p.rx * 1.05 : cx + p.rx * 1.05;
          const innerX = left ? cx + p.rx * 0.75 : cx - p.rx * 0.75;
          const by = p.browY - (lid > 0.3 ? 0 : 0);
          return (
            <line
              x1={outerX}
              y1={by + lift - d.tilt * 0.3}
              x2={innerX}
              y2={by + lift + d.tilt}
              stroke={C.line}
              strokeWidth={SW}
              strokeLinecap="round"
            />
          );
        })()}
      </g>
    );
  };

  const m = open && d.mouth !== 'o' && d.mouth !== 'wide' ? 'open' : d.mouth;
  const mw = p.mw;
  let mouth: React.ReactNode;
  const fill = p.mouthFill ?? C.line;
  switch (m) {
    case 'open':
      mouth = <ellipse cx={p.mx} cy={p.my + 4} rx={mw * 0.4} ry={mw * 0.3} fill={fill} stroke={C.line} strokeWidth={SD} />;
      break;
    case 'o':
      mouth = <ellipse cx={p.mx} cy={p.my + 6} rx={mw * 0.22} ry={mw * 0.3} fill={fill} stroke={C.line} strokeWidth={SD} />;
      break;
    case 'wide':
      mouth = <ellipse cx={p.mx} cy={p.my + 8} rx={mw * 0.5} ry={mw * (open ? 0.42 : 0.34)} fill={fill} stroke={C.line} strokeWidth={SD} />;
      break;
    case 'smile':
      mouth = <path d={`M${p.mx - mw / 2} ${p.my} Q${p.mx} ${p.my + mw * 0.55} ${p.mx + mw / 2} ${p.my}`} fill="none" stroke={C.line} strokeWidth={SW} strokeLinecap="round" />;
      break;
    case 'frown':
      mouth = <path d={`M${p.mx - mw / 2} ${p.my + 10} Q${p.mx} ${p.my - 12} ${p.mx + mw / 2} ${p.my + 10}`} fill="none" stroke={C.line} strokeWidth={SW} strokeLinecap="round" />;
      break;
    case 'smirk':
      mouth = <path d={`M${p.mx - mw / 2} ${p.my + 4} Q${p.mx} ${p.my + 4} ${p.mx + mw / 2} ${p.my - 8}`} fill="none" stroke={C.line} strokeWidth={SW} strokeLinecap="round" />;
      break;
    default:
      mouth = <line x1={p.mx - mw / 2} y1={p.my} x2={p.mx + mw / 2} y2={p.my} stroke={C.line} strokeWidth={SW} strokeLinecap="round" />;
  }
  return (
    <g>
      {eye(p.cx1, 1, true)}
      {eye(p.cx2, 2, false)}
      {mouth}
    </g>
  );
};

/* ------------------------------------------------------------------ */
/* OPUS                                                                 */
/* ------------------------------------------------------------------ */

const starPath = (cx: number, cy: number, rOut: number, rIn: number, n: number): string => {
  let d = '';
  for (let i = 0; i < n * 2; i++) {
    const a = (i / (n * 2)) * Math.PI * 2 - Math.PI / 2;
    const r = i % 2 === 0 ? rOut : rIn;
    d += `${i === 0 ? 'M' : 'L'}${(cx + Math.cos(a) * r).toFixed(1)} ${(cy + Math.sin(a) * r).toFixed(1)} `;
  }
  return d + 'Z';
};

const Limb: React.FC<{d: string; w: number; fill: string}> = ({d, w, fill}) => (
  <>
    <path d={d} fill="none" stroke={C.line} strokeWidth={w + SW * 2} strokeLinecap="round" strokeLinejoin="round" />
    <path d={d} fill="none" stroke={fill} strokeWidth={w} strokeLinecap="round" strokeLinejoin="round" />
  </>
);

export const Opus: React.FC<Base & {mug?: boolean; arm?: 'down' | 'up' | 'lever' | 'point'}> = ({
  x,
  y,
  height = 420,
  flip,
  expr = 'deadpan',
  talking = false,
  look = [0, 0],
  blink,
  squash,
  rotate,
  style,
  mug = true,
  arm = 'down',
}) => {
  const frame = useCurrentFrame();
  const f = twos(frame);
  const id = useId().replace(/:/g, '_');
  const autoBlink = f % 96 >= 90 && f % 96 < 92;
  const bl = blink ?? autoBlink;
  const star = starPath(200, 150, 130, 88, 9);

  const armPaths = {
    down: 'M150 285 Q122 320 118 352',
    up: 'M150 285 Q100 240 108 190',
    lever: 'M150 285 Q100 300 66 318',
    point: 'M150 285 Q95 270 48 262',
  } as const;
  const handPos = {down: [118, 356], up: [108, 184], lever: [62, 320], point: [42, 262]}[arm];

  return (
    <Wrap x={x} y={y} vbW={400} vbH={430} height={height} flip={flip} squash={squash} rotate={rotate} style={style}>
      {/* slippers */}
      {[150, 250].map((cx) => (
        <g key={cx}>
          <ellipse cx={cx} cy={408} rx={42} ry={20} fill={C.slipper} stroke={C.line} strokeWidth={SW} />
          {[-22, -6, 10, 26].map((o) => (
            <circle key={o} cx={cx + o} cy={394} r={9} fill={C.slipper} stroke={C.line} strokeWidth={SD} />
          ))}
        </g>
      ))}
      {/* robe */}
      <clipPath id={`${id}-robe`}>
        <path d="M128 250 L272 250 L292 396 L108 396 Z" />
      </clipPath>
      <path d="M128 250 L272 250 L292 396 L108 396 Z" fill={C.robe} />
      <g clipPath={`url(#${id}-robe)`}>
        <path d="M226 250 L272 250 L292 396 L236 396 Z" fill={C.robeShadow} />
      </g>
      <path d="M128 250 L272 250 L292 396 L108 396 Z" fill="none" stroke={C.line} strokeWidth={SW} strokeLinejoin="round" />
      <path d="M170 252 L200 300 L230 252" fill="none" stroke={C.line} strokeWidth={SD} strokeLinejoin="round" />
      {/* belt */}
      <rect x={118} y={318} width={164} height={22} fill={C.robeShadow} stroke={C.line} strokeWidth={SD} />
      <path d="M196 340 L186 372 M204 340 L216 370" stroke={C.line} strokeWidth={SD} strokeLinecap="round" />
      {/* free arm */}
      <Limb d={armPaths[arm]} w={26} fill={C.robe} />
      <circle cx={handPos[0]} cy={handPos[1]} r={arm === 'lever' ? 17 : 15} fill={C.opus} stroke={C.line} strokeWidth={SD} />
      {/* mug arm */}
      <Limb d="M250 285 Q290 305 292 336" w={26} fill={C.robe} />
      {mug ? (
        <g>
          <path d="M318 322 q22 2 22 18 q0 16 -22 16" fill="none" stroke={C.line} strokeWidth={SD + 2} />
          <rect x={282} y={314} width={40} height={44} rx={6} fill={C.slipper} stroke={C.line} strokeWidth={SD} />
          <rect x={284} y={316} width={36} height={10} fill="#5A3A2A" />
          <circle cx={292} cy={338} r={13} fill={C.opus} stroke={C.line} strokeWidth={SD} />
        </g>
      ) : (
        <circle cx={292} cy={340} r={15} fill={C.opus} stroke={C.line} strokeWidth={SD} />
      )}
      {/* head: spark */}
      <clipPath id={`${id}-star`}>
        <path d={star} />
      </clipPath>
      <path d={star} fill={C.opusShadow} />
      <g clipPath={`url(#${id}-star)`}>
        <circle cx={188} cy={139} r={116} fill={C.opus} />
      </g>
      <path d={star} fill="none" stroke={C.line} strokeWidth={SW} strokeLinejoin="round" />
      <Face
        cx1={160}
        cx2={240}
        ey={150}
        rx={25}
        ry={28}
        mx={200}
        my={205}
        mw={44}
        browY={108}
        expr={expr}
        talking={talking}
        look={look}
        blink={bl}
        lidColor={C.opus}
        pupilR={6}
        mouthFill={C.line}
      />
    </Wrap>
  );
};

/* ------------------------------------------------------------------ */
/* DEEPSEEK                                                             */
/* ------------------------------------------------------------------ */

const Spout: React.FC<{state: 'off' | 'spray' | 'sputter' | 'droop'; f: number}> = ({state, f}) => {
  const water = '#BFE3FF';
  const drop = (cx: number, cy: number, r: number, k: string | number) => (
    <path
      key={k}
      d={`M${cx} ${cy - r * 1.8} Q${cx + r * 1.1} ${cy - r * 0.2} ${cx} ${cy + r} Q${cx - r * 1.1} ${cy - r * 0.2} ${cx} ${cy - r * 1.8} Z`}
      fill={water}
      stroke={C.line}
      strokeWidth={5}
      strokeLinejoin="round"
    />
  );
  const base = <rect x={186} y={52} width={28} height={30} rx={8} fill={C.deepseekShadow} stroke={C.line} strokeWidth={SD} />;
  if (state === 'off') return base;
  if (state === 'droop') {
    return (
      <g>
        <path d="M200 56 Q200 28 232 34 Q248 40 244 70" fill="none" stroke={C.line} strokeWidth={22} strokeLinecap="round" />
        <path d="M200 56 Q200 28 232 34 Q248 40 244 70" fill="none" stroke={C.deepseekShadow} strokeWidth={10} strokeLinecap="round" />
        {f % 8 < 4 ? drop(244, 94, 7, 'd') : null}
        {base}
      </g>
    );
  }
  if (state === 'sputter') {
    const k = Math.floor(f / 2) % 3;
    return (
      <g>
        {drop(196 + k * 8, 30 - k * 4, 8, 'a')}
        {k !== 1 ? drop(214, 14 + k * 6, 6, 'b') : null}
        {base}
      </g>
    );
  }
  const wob = Math.floor(f / 2) % 2 ? 6 : -6;
  return (
    <g>
      <path d={`M200 56 L200 -40 M200 56 Q${160 + wob} -10 ${130 + wob} 20 M200 56 Q${240 - wob} -10 ${270 - wob} 20`} fill="none" stroke={C.line} strokeWidth={18} strokeLinecap="round" />
      <path d={`M200 56 L200 -40 M200 56 Q${160 + wob} -10 ${130 + wob} 20 M200 56 Q${240 - wob} -10 ${270 - wob} 20`} fill="none" stroke={water} strokeWidth={8} strokeLinecap="round" />
      {drop(196 + wob, -56, 9, 'a')}
      {drop(124 + wob, 4, 8, 'b')}
      {drop(276 - wob, 4, 8, 'c')}
      {drop(160 - wob, -40, 6, 'd')}
      {drop(240 + wob, -40, 6, 'e')}
      {base}
    </g>
  );
};

export const DeepSeek: React.FC<
  Base & {spout?: 'off' | 'spray' | 'sputter' | 'droop'; sticker?: string; flail?: boolean}
> = ({
  x,
  y,
  height = 340,
  flip,
  expr = 'neutral',
  talking = false,
  look = [0, 0],
  blink,
  squash,
  rotate,
  style,
  spout = 'off',
  sticker,
  flail = false,
}) => {
  const frame = useCurrentFrame();
  const f = twos(frame);
  const id = useId().replace(/:/g, '_');
  const bl = blink ?? (f % 72 >= 68 && f % 72 < 70);
  const finA = flail ? Math.sin(f * 0.9) * 38 : 0;
  const unflip = flip ? 'scale(-1 1)' : '';
  const body = 'M200 70 C300 70 340 140 340 205 C340 280 280 318 200 318 C120 318 60 280 60 205 C60 140 100 70 200 70 Z';
  return (
    <Wrap x={x} y={y} vbW={400} vbH={340} height={height} flip={flip} squash={squash} rotate={rotate} style={style}>
      {/* tail fluke */}
      <g transform={`rotate(${flail ? Math.sin(f * 0.7) * 10 : 0} 330 215)`}>
        <path d="M322 230 Q380 215 372 150 Q360 170 335 168 Q350 130 380 110 Q320 100 312 190 Z" fill={C.deepseek} stroke={C.line} strokeWidth={SW} strokeLinejoin="round" />
      </g>
      {/* feet */}
      {[148, 252].map((cx) => (
        <ellipse key={cx} cx={cx} cy={324} rx={34} ry={14} fill={C.deepseekShadow} stroke={C.line} strokeWidth={SW} />
      ))}
      {/* back fin */}
      <Spout state={spout} f={f} />
      {/* body */}
      <clipPath id={`${id}-body`}>
        <path d={body} />
      </clipPath>
      <path d={body} fill={C.deepseekShadow} />
      <g clipPath={`url(#${id}-body)`}>
        <ellipse cx={186} cy={196} rx={134} ry={118} fill={C.deepseek} />
        <ellipse cx={196} cy={296} rx={104} ry={58} fill={C.deepseekBelly} />
        {/* headband */}
        <rect x={40} y={92} width={320} height={44} fill={C.headband} />
        <line x1={40} x2={360} y1={92} y2={92} stroke={C.line} strokeWidth={SD} />
        <line x1={40} x2={360} y1={136} y2={136} stroke={C.line} strokeWidth={SD} />
      </g>
      <path d={body} fill="none" stroke={C.line} strokeWidth={SW} strokeLinejoin="round" />
      {/* headband knot tails */}
      <path d="M330 100 L372 84 L362 118 L376 140 L336 130 Z" fill={C.headband} stroke={C.line} strokeWidth={SD} strokeLinejoin="round" />
      <text x={0} y={0} transform={`translate(200 124) ${unflip}`} textAnchor="middle" fontFamily={BALOO} fontWeight={800} fontSize={32} fill={C.white} stroke={C.line} strokeWidth={0}>
        FLASH
      </text>
      {/* fins */}
      <g transform={`rotate(${-finA} 70 232)`}>
        <ellipse cx={46} cy={238} rx={34} ry={20} transform="rotate(-20 46 238)" fill={C.deepseek} stroke={C.line} strokeWidth={SW} />
      </g>
      <g transform={`rotate(${finA} 330 232)`}>
        <ellipse cx={354} cy={238} rx={34} ry={20} transform="rotate(20 354 238)" fill={C.deepseek} stroke={C.line} strokeWidth={SW} />
      </g>
      <Face
        cx1={150}
        cx2={250}
        ey={190}
        rx={32}
        ry={34}
        mx={200}
        my={262}
        mw={44}
        browY={146}
        expr={expr}
        talking={talking}
        look={look}
        blink={bl}
        lidColor={C.deepseek}
        lidMul={0.6}
        pupilR={6}
        jitter={expr === 'panic' || expr === 'surprised' ? 3 : 1}
        mouthFill={C.line}
      />
      {sticker ? (
        <g transform="translate(200 132) rotate(5)">
          <rect x={-(sticker.length * 6 + 14)} y={-20} width={sticker.length * 12 + 28} height={40} fill={C.boardCream} stroke={C.line} strokeWidth={SD} />
          <text x={0} y={0} transform={unflip} textAnchor="middle" dominantBaseline="central" fontFamily={VT323} fontSize={30} fill={C.line}>
            {sticker}
          </text>
        </g>
      ) : null}
    </Wrap>
  );
};

/* ------------------------------------------------------------------ */
/* HERRING                                                              */
/* ------------------------------------------------------------------ */

export const Herring: React.FC<{
  x: number;
  y: number;
  height?: number;
  flip?: boolean;
  sign?: string;
  squeak?: boolean;
  walking?: boolean;
  look?: [number, number];
}> = ({x, y, height = 160, flip, sign, squeak, walking, look = [0, 0]}) => {
  const frame = useCurrentFrame();
  const f = twos(frame);
  const id = useId().replace(/:/g, '_');
  const step = Math.floor(f / 2) % 2;
  const legA = walking ? (step ? -10 : 0) : 0;
  const legB = walking ? (step ? 0 : -10) : 0;
  const hop = squeak ? (Math.floor(f / 2) % 2 ? -8 : 0) : walking ? (step ? -3 : 0) : 0;
  const body = 'M30 72 C30 34 70 22 108 24 C150 26 182 46 182 74 C182 106 150 122 108 122 C66 122 30 108 30 72 Z';
  const signW = sign ? sign.length * 11 + 28 : 0;
  return (
    <Wrap x={x} y={y} vbW={200} vbH={160} height={height}>
      {/* sign (never mirrored) */}
      {sign ? (
        <g transform={`translate(${flip ? 100 - 0 : 100} ${hop})`}>
          <line x1={0} y1={-6} x2={0} y2={40} stroke={C.line} strokeWidth={SW} strokeLinecap="round" />
          <rect x={-signW / 2} y={-74} width={signW} height={68} fill={C.boardCream} stroke={C.line} strokeWidth={SW} strokeLinejoin="round" />
          <text x={0} y={-40} textAnchor="middle" dominantBaseline="central" fontFamily={VT323} fontSize={30} fill={C.line}>
            {sign}
          </text>
        </g>
      ) : null}
      <g transform={`${flip ? 'translate(200 0) scale(-1 1)' : ''} translate(0 ${hop})`}>
        {/* legs */}
        <g>
          <rect x={72} y={112 + legA} width={20} height={36 - legA} rx={8} fill={C.herringShadow} stroke={C.line} strokeWidth={SD} />
          <ellipse cx={80} cy={152 - 0} rx={20} ry={8} fill={C.herringShadow} stroke={C.line} strokeWidth={SD} transform={`translate(0 ${legA})`} />
          <rect x={118} y={112 + legB} width={20} height={36 - legB} rx={8} fill={C.herringShadow} stroke={C.line} strokeWidth={SD} />
          <ellipse cx={128} cy={152} rx={20} ry={8} fill={C.herringShadow} stroke={C.line} strokeWidth={SD} transform={`translate(0 ${legB})`} />
        </g>
        {/* tail */}
        <path d="M34 72 L2 34 Q10 72 2 110 Z" fill={C.herring} stroke={C.line} strokeWidth={SW} strokeLinejoin="round" />
        {/* dorsal fin */}
        <path d="M80 28 L96 -2 L124 28 Z" fill={C.herringShadow} stroke={C.line} strokeWidth={SD} strokeLinejoin="round" />
        <clipPath id={`${id}-b`}>
          <path d={body} />
        </clipPath>
        <path d={body} fill={C.herring} />
        <g clipPath={`url(#${id}-b)`}>
          <ellipse cx={108} cy={124} rx={86} ry={32} fill={C.herringBelly} />
          <path d="M120 22 L182 22 L182 60 Q150 40 120 22 Z" fill={C.herringShadow} />
        </g>
        <path d={body} fill="none" stroke={C.line} strokeWidth={SW} strokeLinejoin="round" />
        {/* eye */}
        <circle cx={140} cy={62} r={24} fill={C.eye} stroke={C.line} strokeWidth={SD} />
        <circle cx={140 + look[0] * 8} cy={62 + look[1] * 8} r={6} fill={C.line} />
        {/* mouth */}
        {squeak ? (
          <ellipse cx={176} cy={88} rx={7} ry={9} fill={C.line} />
        ) : (
          <path d="M160 92 Q172 98 182 90" fill="none" stroke={C.line} strokeWidth={SD} strokeLinecap="round" />
        )}
        {squeak ? (
          <path d="M196 70 l14 -8 M198 84 l16 0 M196 98 l14 8" stroke={C.line} strokeWidth={SD} strokeLinecap="round" />
        ) : null}
      </g>
    </Wrap>
  );
};

/* ------------------------------------------------------------------ */
/* HAND                                                                 */
/* ------------------------------------------------------------------ */

const SKIN = '#F2C9A0';
const SKIN_SH = '#D9A877';

/** Hangs from above. (x,y) = bottom-center, i.e. the fingertip end; sleeve cuff at the top. */
export const Hand: React.FC<{
  x: number;
  y: number;
  height?: number;
  rotate?: number;
  flip?: boolean;
  pose: 'open' | 'grab' | 'point';
}> = ({x, y, height = 500, rotate, flip, pose}) => {
  const finger = (cx: number, len: number, w: number, rot: number, k: number) => (
    <rect
      key={k}
      x={cx - w / 2}
      y={300}
      width={w}
      height={len}
      rx={w / 2}
      fill={SKIN}
      stroke={C.line}
      strokeWidth={SW}
      transform={`rotate(${rot} ${cx} 300)`}
    />
  );
  let fingers: React.ReactNode;
  if (pose === 'open') {
    fingers = [
      finger(98, 150, 36, 14, 0),
      finger(138, 176, 38, 5, 1),
      finger(178, 168, 38, -4, 2),
      finger(214, 140, 34, -13, 3),
    ];
  } else if (pose === 'grab') {
    fingers = [
      finger(100, 78, 38, 4, 0),
      finger(140, 92, 40, 0, 1),
      finger(180, 90, 40, 0, 2),
      finger(216, 74, 36, -4, 3),
    ];
  } else {
    fingers = [
      finger(100, 70, 38, 4, 0),
      finger(140, 180, 36, 0, 1),
      finger(180, 70, 40, 0, 2),
      finger(216, 62, 36, -4, 3),
    ];
  }
  const vbW = 300;
  const vbH = 500;
  return (
    <Wrap x={x} y={y} vbW={vbW} vbH={vbH} height={height} flip={flip} rotate={rotate} style={{transformOrigin: '50% 50%'}}>
      {/* sleeve */}
      <rect x={70} y={-40} width={160} height={150} fill="#7D70B5" stroke={C.line} strokeWidth={SW} />
      <rect x={70} y={-40} width={44} height={150} fill="#6A5EA0" />
      <rect x={70} y={-40} width={160} height={150} fill="none" stroke={C.line} strokeWidth={SW} />
      {/* cuff */}
      <rect x={60} y={110} width={180} height={64} rx={8} fill={C.boardCream} stroke={C.line} strokeWidth={SW} />
      <text x={150} y={142} textAnchor="middle" dominantBaseline="central" fontFamily={BALOO} fontWeight={800} fontSize={44} fill={C.line}>
        OPS
      </text>
      {/* thumb */}
      <rect x={30} y={190} width={52} height={pose === 'grab' ? 100 : 120} rx={26} fill={SKIN} stroke={C.line} strokeWidth={SW} transform={`rotate(${pose === 'grab' ? -35 : -50} 70 210)`} />
      {/* palm */}
      <rect x={76} y={168} width={148} height={150} rx={46} fill={SKIN} stroke={C.line} strokeWidth={SW} />
      {fingers}
      {/* repaint palm bottom to hide finger roots */}
      <rect x={82} y={250} width={136} height={60} rx={30} fill={SKIN} />
      <path d="M186 180 L216 180 L216 300 Q200 316 186 300 Z" fill={SKIN_SH} opacity={0} />
      {pose === 'grab' ? <path d="M92 318 q55 18 118 0" stroke={C.line} strokeWidth={SD} fill="none" strokeLinecap="round" /> : null}
    </Wrap>
  );
};

/* ------------------------------------------------------------------ */
/* PAGER                                                                */
/* ------------------------------------------------------------------ */

/** (x,y) = top-center of the pager body; the string continues up out of frame. */
export const Pager: React.FC<{
  x: number;
  y: number;
  width?: number;
  lines: string[];
  chars?: number;
  string?: boolean;
  shake?: boolean;
}> = ({x, y, width = 520, lines, chars, string = true, shake}) => {
  const frame = useCurrentFrame();
  const boil = useBoil();
  const h = width * 0.62;
  const dx = shake ? (random(`pg-x-${frame}`) * 2 - 1) * 3 : 0;
  const dy = shake ? (random(`pg-y-${frame}`) * 2 - 1) * 3 : 0;
  const lcdX = width * 0.07;
  const lcdW = width * 0.86;
  const lcdH = h * 0.5;
  const maxLen = Math.max(8, ...lines.map((l) => l.length));
  const fs = Math.min(width * 0.12, lcdW / (maxLen * 0.42));
  let left = chars ?? Infinity;
  const shown = lines.map((l) => {
    const s = l.slice(0, Math.max(0, left));
    left -= l.length;
    return s;
  });
  const caret = chars !== undefined && frame % 12 < 6;
  return (
    <div style={{position: 'absolute', left: x - width / 2 + dx, top: y + dy, width, height: h}}>
      <svg width={width} height={h} viewBox={`0 0 ${width} ${h}`} style={{overflow: 'visible'}}>
        <g filter={boil}>
        {string ? (
          <line x1={width / 2} y1={4} x2={width / 2} y2={-2400} stroke={C.line} strokeWidth={SW} />
        ) : null}
        <rect x={5} y={5} width={width - 10} height={h - 10} rx={26} fill="#4B4560" stroke={C.line} strokeWidth={SW} />
        <path d={`M${width - 5} ${h * 0.4} L${width - 5} ${h - 31} Q${width - 5} ${h - 5} ${width - 31} ${h - 5} L${width * 0.5} ${h - 5} Z`} fill="#3A3548" opacity={0} />
        <rect x={lcdX - 10} y={h * 0.1 - 10} width={lcdW + 20} height={lcdH + 20} rx={12} fill="#3A3548" stroke={C.line} strokeWidth={SD} />
        <rect x={lcdX} y={h * 0.1} width={lcdW} height={lcdH} rx={6} fill="#2A1F0A" stroke={C.line} strokeWidth={SD} />
        {shown.map((s, i) => (
          <text
            key={i}
            x={lcdX + 14}
            y={h * 0.1 + 12 + fs * 0.8 + i * fs * 0.95}
            fontFamily={VT323}
            fontSize={fs}
            fill={C.amber}
            style={{whiteSpace: 'pre'}}
          >
            {s}
            {caret && i === shown.findIndex((q, j) => q.length < lines[j].length || j === shown.length - 1) ? '_' : ''}
          </text>
        ))}
        {/* buttons */}
        {[0.2, 0.42, 0.64].map((o, i) => (
          <rect key={i} x={width * o} y={h * 0.74} width={width * 0.15} height={h * 0.14} rx={10} fill={i === 1 ? C.stampRed : '#8D99AE'} stroke={C.line} strokeWidth={SD} />
        ))}
        {/* beaten: scratches, dent and crack */}
        <path d={`M${width * 0.08} ${h * 0.82} l22 -14 M${width * 0.86} ${h * 0.7} l-20 -22 M${width * 0.9} ${h * 0.82} l-16 6`} stroke={C.line} strokeWidth={4} strokeLinecap="round" opacity={0.7} />
        <path d={`M${width * 0.78} 6 l-14 26 l14 10 l-10 22`} fill="none" stroke={C.line} strokeWidth={SD} strokeLinejoin="round" />
        <circle cx={width / 2} cy={5} r={12} fill={C.grey} stroke={C.line} strokeWidth={SD} />
        </g>
      </svg>
    </div>
  );
};
