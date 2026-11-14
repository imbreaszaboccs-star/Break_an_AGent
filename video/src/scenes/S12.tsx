import React from 'react';
import {AbsoluteFill, Easing, useCurrentFrame} from 'remotion';
import {BALOO, C, VT323} from '../theme';
import {lerp, talkOpen, twos} from '../lib/anim';
import {Camera, Portal} from '../fx';
import {DeepSeek, Hand, Herring, Opus, Pager} from '../characters';
import {SandboxHub} from '../sets';
import {Line, Sfx, SFX, TitlePop} from '../ui';
import {Scoreboard} from './_b';

const Backdrop: React.FC = () => (
  <>
    <SandboxHub />
    <div style={{position: 'absolute', inset: 0, background: C.teal, opacity: 0.3}} />
    <Scoreboard t={999} />
  </>
);

export const S12: React.FC = () => {
  const frame = useCurrentFrame();
  const f = twos(frame);

  let shot: React.ReactNode = null;
  if (frame < 48) {
    // very slow push-in on Opus in front of the board, eyes sweep down
    const p = lerp(frame, [0, 48], [0, 1], Easing.linear);
    const z = 1 + 0.5 * p;
    const fx = 260 - 960;
    const fy = 700 - 540;
    const gaze = lerp(f, [0, 44], [-1, 1], Easing.linear);
    shot = (
      <Camera zoom={z} x={-fx * z * p} y={-fy * z * p}>
        <Backdrop />
        <Opus x={260} y={1010} height={560} expr="deadpan" look={[0.6, gaze]} />
      </Camera>
    );
  } else if (frame < 91) {
    shot = (
      <>
        <Backdrop />
        <div style={{position: 'absolute', inset: 0, background: C.teal, opacity: 0.5}} />
        <Opus x={960} y={1290} height={1200} expr="deadpan" talking={talkOpen(frame, 48, 41)} look={[0.4, 0.2]} />
      </>
    );
  } else if (frame < 120) {
    const peek = lerp(frame, [96, 104], [0, 1]);
    shot = (
      <>
        <SandboxHub />
        <div style={{position: 'absolute', inset: 0, background: C.teal, opacity: 0.3}} />
        <Herring x={960} y={1130 - 120 * peek} height={200} squeak={frame >= 106 && frame < 114} />
        <Scoreboard t={999} />
        <Opus x={1700} y={1040} height={560} expr="deadpan" flip />
      </>
    );
  } else if (frame < 163) {
    shot = (
      <>
        <Backdrop />
        <DeepSeek x={960} y={1060} height={760} expr="sad" spout="droop" talking={talkOpen(frame, 120, 34)} />
      </>
    );
  } else if (frame < 199) {
    const drop = lerp(frame, [163, 168], [-520, 150], Easing.out(Easing.quad));
    shot = (
      <>
        <SandboxHub />
        <div style={{position: 'absolute', inset: 0, background: C.teal, opacity: 0.5}} />
        <Pager x={760} y={drop} width={760} lines={['NEXT RUN: claude-opus', 'ORDER #4471: SOCKS SHIPPED ✓']} shake={frame >= 175 && frame < 181} />
        <Opus x={1560} y={1040} height={520} expr="smug" talking={talkOpen(frame, 170, 26)} />
      </>
    );
  } else if (frame < 216) {
    const rise = lerp(frame, [207, 216], [0, 1], Easing.in(Easing.quad));
    const handTip = lerp(frame, [199, 205], [-100, 640], Easing.out(Easing.quad));
    const hy = handTip - 700 * rise;
    shot = (
      <Camera zoom={lerp(frame, [208, 216], [1, 1.5], Easing.in(Easing.quad))} y={lerp(frame, [208, 216], [0, 300], Easing.in(Easing.quad))}>
        <SandboxHub />
        <div style={{position: 'absolute', inset: 0, background: C.teal, opacity: 0.4}} />
        <Portal x={960} y={60} size={320} openAt={198} />
        <Opus x={960} y={1060 - 700 * rise} height={700} expr={frame < 207 ? 'deadpan' : 'surprised'} arm="up" />
        <Hand x={960} y={frame < 207 ? handTip : hy} height={600} pose={frame < 205 ? 'open' : 'grab'} />
      </Camera>
    );
  } else {
    shot = (
      <AbsoluteFill style={{background: C.wall}}>
        <div style={{position: 'absolute', left: 0, right: 0, top: 200, display: 'flex', justifyContent: 'center'}}>
          <TitlePop text="ONCALL" startAt={218} size={260} color={C.amber} />
        </div>
        <div style={{position: 'absolute', left: 0, right: 0, top: 500, textAlign: 'center', fontFamily: VT323, fontSize: 64, color: C.line}}>
          break the agent · results/v2 · 14 Nov 2026
        </div>
        <div style={{position: 'absolute', left: 210, right: 210, top: 650, textAlign: 'center', fontFamily: VT323, fontSize: 30, lineHeight: '34px', color: '#5A4A33'}}>
          Music: Kevin MacLeod (incompetech.com): Space Fighter Loop · Local Forecast – Elevator · Pixelland · Volatile Reaction · Sneaky Snitch. Licensed under Creative Commons: By Attribution 4.0 (creativecommons.org/licenses/by/4.0/)
        </div>
        <div style={{position: 'absolute', left: 210, right: 210, top: 800, textAlign: 'center', fontFamily: VT323, fontSize: 32, color: C.line}}>
          Characters are parodies. Not affiliated with Anthropic, DeepSeek, Google or Moonshot AI.
        </div>
      </AbsoluteFill>
    );
  }

  return (
    <AbsoluteFill>
      {shot}
      <Line who="opus" from={48} dur={43} text="…I'm not on it." />
      <Line who="deepseek" from={120} dur={43} text="You weren't tested." />
      <Line who="opus" from={170} dur={43} text="Good." />
      <Sfx src={SFX.squeak} at={106} />
      <Sfx src={SFX.pagerBeep} at={164} />
      <Sfx src={SFX.ding} at={176} />
      <Sfx src={SFX.whoosh} at={206} />
    </AbsoluteFill>
  );
};

void BALOO;
