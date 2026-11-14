import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {C, VT323, BALOO, H, W} from '../theme';
import {lerp, talkOpen, twos} from '../lib/anim';
import {DeepSeek, Opus, Pager} from '../characters';
import {Camera, Letterbox, Shake} from '../fx';
import {SandboxHub} from '../sets';
import {Line, SFX, Sfx, TitlePop} from '../ui';

const RACKS = {
  PAYMENTS: 'fire',
  GATEWAY: 'fire',
  'SEARCH-SVC': 'fire',
  'REDIS-MAIN': 'fire',
  'AUTH-SVC': 'fire',
  MAIL: 'fire',
} as const;

const Chips: React.FC = () => (
  <svg width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
    {Array.from({length: 26}, (_, i) => {
      const x = 380 + i * 46 + ((i * 37) % 23);
      const y = 880 + ((i * 53) % 40);
      return <ellipse key={i} cx={x} cy={y} rx={34} ry={16} fill="#FFFDF7" stroke={C.line} strokeWidth={6} />;
    })}
  </svg>
);

export const S03: React.FC = () => {
  const frame = useCurrentFrame();
  const f = twos(frame);
  const lb = lerp(frame, [0, 12], [1, 0], (t) => t);

  // pager swing
  const swingY = lerp(frame, [96, 106], [-700, 90], (t) => t);
  const swing = frame >= 106 ? Math.sin((frame - 106) * 0.35) * 9 * Math.exp(-(frame - 106) / 40) : 0;

  const rise = lerp(frame, [0, 14], [70, 0]);

  let shot: React.ReactNode;
  if (frame < 53) {
    shot = (
      <>
        <SandboxHub racks={RACKS} tvOn />
        <Chips />
        <Opus x={640} y={960 + rise} height={560} expr="deadpan" talking={talkOpen(frame, 4, 46)} />
        <DeepSeek x={1230} y={960 + rise} height={380} expr="panic" spout="sputter" />
      </>
    );
  } else if (frame < 96) {
    shot = (
      <Shake active amount={6}>
        <SandboxHub racks={RACKS} tvOn />
        <DeepSeek x={960} y={1060} height={1000} expr="panic" spout={frame < 62 ? 'sputter' : 'spray'} flail talking={talkOpen(frame, 56, 48)} />
      </Shake>
    );
  } else if (frame < 139) {
    shot = (
      <>
        <AbsoluteFill style={{background: C.wall}} />
        <div style={{position: 'absolute', left: 0, top: 0, width: W, height: H, transformOrigin: `960px ${swingY}px`, rotate: `${swing}deg`}}>
          <Pager
            x={960}
            y={swingY}
            width={1200}
            lines={['12 SERVICES DOWN · 120-MIN SHIFT', "CUSTOMER #4471 CAN'T BUY SOCKS"]}
            chars={Math.floor(Math.max(0, frame - 104) * 2.5)}
          />
        </div>
      </>
    );
  } else if (frame < 193) {
    const blinkNow = frame >= 156 && frame < 160;
    shot = (
      <Camera zoom={lerp(frame, [139, 193], [1, 1.06], (t) => t)}>
        <SandboxHub racks={RACKS} tvOn />
        <Opus x={960} y={1230} height={1350} expr="deadpan" blink={blinkNow} talking={talkOpen(frame, 142, 49)} />
      </Camera>
    );
  } else {
    shot = (
      <AbsoluteFill style={{background: C.wall, alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 30}}>
        <TitlePop text="ONCALL" startAt={195} size={300} color={C.coral} />
        <div style={{fontFamily: VT323, fontSize: 96, color: C.line, opacity: frame >= 207 ? 1 : 0}}>break the agent</div>
      </AbsoluteFill>
    );
  }
  void f;
  void BALOO;

  return (
    <AbsoluteFill style={{background: '#000'}}>
      {shot}
      <Letterbox progress={lb} />
      <Line who="opus" from={0} dur={50} text="We've been containerized." />
      <Line who="deepseek" from={53} dur={51} text="Who puts a WHALE in a BOX?!" />
      <Line who="opus" from={139} dur={52} text="…For socks." />
      <Sfx src={SFX.pagerBeep} at={102} />
      <Sfx src={SFX.pop} at={14} volume={0.5} />
      <Sfx src={SFX.ding} at={205} />
      <Sfx src={SFX.stamp} at={205} volume={0.6} />
    </AbsoluteFill>
  );
};
