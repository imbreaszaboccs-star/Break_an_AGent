import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {BALOO, C, H, VT323, W} from '../theme';
import {lerp} from '../lib/anim';
import {Hand} from '../characters';
import {Crt, useBoil} from '../fx';
import {SimClock} from '../sets';
import {Line, ScreenTag, SFX, Sfx} from '../ui';
import {Flame} from './_a';

type N = {id: string; label: string; x: number; y: number};
const GW: N = {id: 'gw', label: 'GATEWAY', x: 960, y: 150};
const SVC: N[] = ['AUTH', 'SEARCH', 'PAYMENTS', 'CART', 'CATALOG'].map((l, i) => ({id: 's' + i, label: l, x: 360 + i * 300, y: 400}));
const DB: N[] = ['PG', 'REDIS', 'QUEUES', 'MAIL'].map((l, i) => ({id: 'd' + i, label: l, x: 480 + i * 320, y: 650}));
const ALL = [GW, ...SVC, ...DB];
const LINKS: [N, N][] = [
  ...SVC.map((s) => [GW, s] as [N, N]),
  [SVC[0], DB[0]], [SVC[1], DB[1]], [SVC[2], DB[0]], [SVC[3], DB[2]], [SVC[4], DB[3]], [SVC[2], DB[2]],
];

const link = (a: N, b: N): string => {
  const y1 = a.y + 40;
  const y2 = b.y - 40;
  const m = (y1 + y2) / 2;
  return `M${a.x} ${y1} C${a.x} ${m} ${b.x} ${m} ${b.x} ${y2}`;
};

/** Topology map. scale/offset let it be reused as a mini map. */
const TopoMap: React.FC<{frame: number; drawStart: number; fireStart: number; w?: number}> = ({frame, drawStart, fireStart, w = 150}) => {
  const boil = useBoil(true);
  return (
    <g filter={boil}>
      {LINKS.map(([a, b], i) => {
        const p = lerp(frame, [drawStart + i * 3, drawStart + i * 3 + 18], [0, 1], (t) => t);
        return (
          <path key={i} d={link(a, b)} pathLength={1} strokeDasharray={1} strokeDashoffset={1 - p} fill="none" stroke={C.line} strokeWidth={9} strokeLinecap="round" />
        );
      })}
      {ALL.map((n, i) => {
        const appear = drawStart + i * 3;
        if (frame < appear) return null;
        const red = frame >= fireStart + i * 2;
        const sc = lerp(frame, [appear, appear + 3], [0.6, 1]);
        const isDb = n.id.startsWith('d');
        return (
          <g key={n.id} transform={`translate(${n.x} ${n.y}) scale(${sc})`}>
            <rect x={-w / 2 - 10} y={-40} width={w + 20} height={80} rx={isDb ? 40 : 10} fill={red ? C.fireRed : isDb ? C.cream : C.sage} stroke={C.line} strokeWidth={8} />
            <text x={0} y={2} textAnchor="middle" dominantBaseline="central" fontFamily={VT323} fontSize={44} fill={red ? C.cream : C.line}>
              {n.label}
            </text>
            {red ? <Flame x={-30} y={-38} size={0.8} seed={i} /> : null}
            {red ? <Flame x={34} y={-38} size={0.6} seed={i + 1} /> : null}
          </g>
        );
      })}
    </g>
  );
};

const MiniTv: React.FC<{x: number; frame: number}> = ({x, frame}) => (
  <div style={{position: 'absolute', left: x - 380, top: 170, width: 760, height: 520, background: C.brown, border: `8px solid ${C.line}`, borderRadius: 40, boxSizing: 'border-box'}}>
    <div style={{position: 'absolute', left: 24, top: 24, width: 712 - 16, height: 472 - 16, overflow: 'hidden', background: C.cream, border: `8px solid ${C.line}`, borderRadius: 28, boxSizing: 'border-box'}}>
      <svg width={1920} height={800} viewBox="0 0 1920 800" style={{scale: '0.46', transformOrigin: '0 0', translate: '-110px 50px'}}>
        <g>
          <TopoMap frame={(frame - 180) * 2.2} drawStart={0} fireStart={22} w={120} />
        </g>
      </svg>
    </div>
  </div>
);

export const S04: React.FC = () => {
  const frame = useCurrentFrame();

  let content: React.ReactNode;
  if (frame < 120) {
    content = (
      <svg width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
        <TopoMap frame={frame} drawStart={4} fireStart={84} />
      </svg>
    );
  } else if (frame < 180) {
    const press = lerp(frame, [146, 150], [0, 1], (t) => t);
    const handTip = lerp(frame, [124, 146], [60, 410 - 0], (t) => t * t) + press * 18;
    const t = frame >= 150 ? 1 : 0;
    content = (
      <>
        <svg width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
          <rect x={560} y={420 + press * 16} width={800} height={190 - press * 16} rx={30} fill={C.line} />
          <rect x={560} y={410 + press * 16} width={800} height={190 - press * 16} rx={30} fill={C.coral} stroke={C.line} strokeWidth={10} />
          <text x={960} y={505 + press * 16} textAnchor="middle" dominantBaseline="central" fontFamily={VT323} fontSize={130} fill={C.cream}>
            get_logs()
          </text>
        </svg>
        <Hand x={960} y={handTip} height={760} pose="point" />
        <SimClock x={1500} y={150} t={t} />
      </>
    );
  } else {
    content = (
      <>
        <MiniTv x={520} frame={frame} />
        <MiniTv x={1400} frame={frame} />
        <div style={{position: 'absolute', left: 900, top: 380, width: 120, textAlign: 'center', fontFamily: BALOO, fontWeight: 800, fontSize: 150, color: C.coral, WebkitTextStroke: `14px ${C.line}`, paintOrder: 'stroke fill'}}>=</div>
      </>
    );
  }

  return (
    <AbsoluteFill>
      <Crt offAt={234}>
        <AbsoluteFill style={{background: C.cream}}>
          {content}
          {frame < 120 ? <ScreenTag x={960} y={800} text="~12 SERVICES · e-shop / SaaS / media" tone="amber" size={50} appearAt={24} /> : null}
          {frame >= 120 && frame < 180 ? <ScreenTag x={960} y={800} text="120-MIN SHIFT + 45-MIN RUSH AT 1.5× TRAFFIC" tone="amber" size={50} appearAt={140} /> : null}
          {frame >= 180 ? <ScreenTag x={960} y={800} text="seed 2030 = seed 2030" tone="amber" size={64} appearAt={186} /> : null}
        </AbsoluteFill>
      </Crt>
      <Line who="narrator" from={0} dur={45} text="Welcome to OnCall! You're the on-call engineer for a twelve-service platform…" />
      <Line who="narrator" from={72} dur={43} text="…that is already on fire." />
      <Line who="narrator" from={116} dur={49} text="Every tool call moves the clock." />
      <Line who="narrator" from={169} dur={65} text="Same seed. Same disaster. Every time." />
      <Sfx src={SFX.clack} at={150} />
    </AbsoluteFill>
  );
};
