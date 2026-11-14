import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {C, H, VT323, W} from '../theme';
import {lerp, talkOpen} from '../lib/anim';
import {DeepSeek, Opus} from '../characters';
import {Camera, Shake, useBoil} from '../fx';
import {PaperSlip, SandboxHub, SimClock, Terminal} from '../sets';
import {Line, ScreenTag, SFX, Sfx, Typewriter} from '../ui';

const CALLS = ['get_metrics()', 'get_deploys()', 'get_logs()', 'get_metrics()', 'get_events()', 'get_logs()'];
const SLIPS = 24;
const FIX = 'run_maintenance(action="sync_clock", service="auth-svc")';

const Plain: React.FC = () => (
  <>
    <AbsoluteFill style={{background: C.wall}} />
    <div style={{position: 'absolute', left: 0, top: 800, width: W, height: 280, background: C.floor, borderTop: `7px solid ${C.line}`}} />
  </>
);

const LOG = [
  '03:12:01 gateway   WARN  p99 latency 2.4s',
  '03:12:02 payments  INFO  retry queue depth 412',
  '03:12:04 search    ERROR upstream timeout (3x)',
  '03:12:05 cart      INFO  session refreshed',
  '03:12:07 gateway   WARN  5xx rate 18%',
  '03:12:08 mail      INFO  digest deferred',
  'auth-svc: tokens rejected — clock skew detected',
  '03:12:11 redis     WARN  evictions rising',
  '03:12:12 catalog   INFO  cache warm 61%',
  '03:12:14 payments  WARN  3ds callback slow',
];

const Scroll: React.FC<{x: number; y: number; w: number; h: number; size: number; offset: number}> = ({x, y, w, h, size, offset}) => (
  <div style={{position: 'absolute', left: x, top: y, width: w, height: h, overflow: 'hidden', background: C.boardCream, border: `8px solid ${C.line}`, boxSizing: 'border-box'}}>
    <div style={{translate: `0 ${-offset}px`, padding: 14}}>
      {[...LOG, ...LOG, ...LOG].map((l, i) => (
        <div key={i} style={{fontFamily: VT323, fontSize: size, lineHeight: `${size * 1.25}px`, color: C.line, whiteSpace: 'pre'}}>
          {l}
        </div>
      ))}
    </div>
  </div>
);

export const S05: React.FC = () => {
  const frame = useCurrentFrame();
  const boil = useBoil(true);

  const slipSfx: React.ReactNode[] = [];
  for (let i = 0; i < SLIPS; i++) slipSfx.push(<Sfx key={i} src={i % 2 ? SFX.mouseClick : SFX.tick} at={6 + i * 3} volume={0.35} />);

  let shot: React.ReactNode;
  if (frame < 98) {
    const t = 7 + Math.min(12, Math.max(0, Math.floor((frame - 6) / 5.5)));
    const slips: React.ReactNode[] = [];
    for (let i = 0; i < SLIPS; i++) {
      const age = frame - (6 + i * 3);
      if (age < 0 || age > 14) continue;
      const p = age / 14;
      slips.push(
        <PaperSlip
          key={i}
          x={1760 - p * (620 - (i % 5) * 40)}
          y={600 - p * (400 - (i % 4) * 50) - Math.sin(p * Math.PI) * 60}
          text={CALLS[i % CALLS.length]}
          rotate={((i % 3) - 1) * 10 - p * 12}
        />,
      );
    }
    const os = lerp(frame, [26, 44], [0, 1], (u) => u);
    shot = (
      <>
        <AbsoluteFill style={{background: C.wall}} />
        <div style={{position: 'absolute', left: 960, top: 0, width: 960, height: H, background: '#DCCDAE'}} />
        <div style={{position: 'absolute', left: 0, top: 800, width: W, height: 280, background: C.floor, borderTop: `7px solid ${C.line}`}} />
        <Scroll x={50} y={140} w={620} h={330} size={24} offset={frame * 3} />
        <Terminal x={250} y={870} scale={1.2} />
        <Opus x={760} y={870} height={460} expr="deadpan" arm="point" look={[-1, -1]} />
        {frame >= 26 && frame < 44 ? <PaperSlip x={250 + os * 120} y={600 - os * 90} text="get_events()" rotate={-8} /> : null}
        <Terminal x={1650} y={870} scale={1.1} />
        <DeepSeek x={1260} y={870} height={400} expr="happy" spout="spray" talking={talkOpen(frame, 0, 96)} flail />
        {slips}
        <div style={{position: 'absolute', left: 954, top: 0, width: 12, height: H, background: C.line}} />
        <SimClock x={960} y={120} t={t} />
        {slipSfx}
      </>
    );
  } else if (frame < 126) {
    shot = (
      <Camera zoom={lerp(frame, [98, 126], [1, 1.04], (u) => u)}>
        <Plain />
        <Opus x={960} y={1160} height={1000} expr="deadpan" look={[0, 1]} />
      </Camera>
    );
  } else if (frame < 142) {
    const p = lerp(frame, [126, 140], [0, 1], (u) => u);
    const t = 19 + Math.floor(p * 11) * 2;
    shot = (
      <>
        <Plain />
        <div style={{position: 'absolute', inset: 0, scale: '2.6', transformOrigin: '960px 440px'}}>
          <SimClock x={960} y={440} t={t} />
        </div>
        <Sfx src={SFX.clack} at={0} />
      </>
    );
  } else if (frame < 156) {
    const sad = frame >= 148;
    shot = (
      <Shake active={!sad} amount={5}>
        <Plain />
        <DeepSeek x={960} y={1080} height={1000} expr={sad ? 'sad' : 'surprised'} spout={sad ? 'droop' : 'sputter'} />
      </Shake>
    );
  } else if (frame < 210) {
    const hl = lerp(frame, [160, 172], [0, 1], (u) => u);
    shot = (
      <>
        <AbsoluteFill style={{background: C.brown}} />
        <div style={{position: 'absolute', left: 130, top: 60, width: 1660, height: 560, overflow: 'hidden', background: C.boardCream, border: `8px solid ${C.line}`, boxSizing: 'border-box'}}>
          <svg width={1660} height={560} style={{position: 'absolute', left: 0, top: 0}}>
            <g filter={boil}>
              <rect x={30} y={28 + 6 * 72 + 4} width={hl * 1500} height={66} fill={C.amber} />
            </g>
          </svg>
          <div style={{padding: '20px 40px', position: 'relative'}}>
            {LOG.slice(0, 7).map((l, i) => (
              <div key={i} style={{fontFamily: VT323, fontSize: 56, lineHeight: '72px', color: C.line, whiteSpace: 'pre'}}>
                {l}
              </div>
            ))}
          </div>
        </div>
        <div style={{position: 'absolute', left: 130, top: 650, width: 1660, height: 110, background: C.line, border: `8px solid ${C.line}`, boxSizing: 'border-box', padding: '10px 30px'}}>
          <Typewriter text={FIX} startAt={176} cps={60} style={{fontSize: 58, color: C.amber}} />
        </div>
      </>
    );
  } else {
    const fixed = frame >= 222;
    shot = (
      <>
        <SandboxHub
          racks={{PAYMENTS: 'fire', GATEWAY: 'fire', 'SEARCH-SVC': 'fire', 'REDIS-MAIN': 'fire', 'AUTH-SVC': fixed ? 'ok' : 'fire', MAIL: 'fire'}}
          tvOn
        />
        <Opus x={760} y={1010} height={330} expr={fixed ? 'smug' : 'deadpan'} />
        <DeepSeek x={1130} y={1010} height={240} expr="happy" />
        <ScreenTag x={960} y={700} text="1 / 3 FAULTS FIXED" tone="amber" size={64} appearAt={224} />
      </>
    );
  }

  return (
    <AbsoluteFill style={{background: '#000'}}>
      {shot}
      <Line who="deepseek" from={0} dur={96} text="Metrics! Deploys! Logs! Faster is better, right?" />
      <Line who="opus" from={98} dur={65} text="The clock moves with every call." />
      <Sfx src={SFX.tick} at={178} />
      <Sfx src={SFX.ding} at={222} />
    </AbsoluteFill>
  );
};
