import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {C, VT323, W} from '../theme';
import {lerp, talkOpen} from '../lib/anim';
import {DeepSeek, Herring, Opus} from '../characters';
import {Camera} from '../fx';
import {Lever, SandboxHub} from '../sets';
import {Line, ScreenTag, SFX, Sfx, Typewriter} from '../ui';
import {SignBoard, Sparkle} from './_a';

const SIGN = 'NEW DEPLOY: search-svc v2.8.1 (2 min ago)';
const TRAPS = 'TRAPS: red-herring deploys · misleading team chat · unnecessary changes cost points';

const Bubble: React.FC<{x: number; y: number; appearAt: number}> = ({x, y, appearAt}) => {
  const frame = useCurrentFrame();
  if (frame < appearAt) return null;
  const s = lerp(frame, [appearAt, appearAt + 3], [0.7, 1]);
  return (
    <div style={{position: 'absolute', left: x, top: y, translate: '-50% -50%', scale: String(s)}}>
      <div style={{background: C.boardCream, border: `7px solid ${C.line}`, borderRadius: 30, padding: '8px 30px', fontFamily: VT323, fontSize: 56, color: C.line, whiteSpace: 'pre'}}>
        <div style={{fontSize: 30, color: C.brown}}>#team-chat</div>
        {'"pretty sure it\'s the deploy"'}
      </div>
      <svg width={60} height={50} style={{position: 'absolute', left: 80, bottom: -44}}>
        <path d="M4 0 L30 44 L52 0 Z" fill={C.boardCream} stroke={C.line} strokeWidth={7} strokeLinejoin="round" />
        <rect x={0} y={-4} width={60} height={9} fill={C.boardCream} />
      </svg>
    </div>
  );
};

export const S06: React.FC = () => {
  const frame = useCurrentFrame();

  const racks = (rbFire: boolean) =>
    ({PAYMENTS: 'fire', GATEWAY: 'fire', 'SEARCH-SVC': 'fire', 'REDIS-MAIN': rbFire ? 'fire' : 'ok', 'AUTH-SVC': 'ok', MAIL: 'fire'}) as const;

  // wide-shot choreography
  const herringX = frame < 48 ? lerp(frame, [0, 44], [2350, 1450], (u) => u) : frame >= 195 ? lerp(frame, [195, 216], [1450, 2350], (u) => u) : 1450;
  const herringWalk = frame < 46 || frame >= 195;
  const herringFlip = frame >= 195;

  let shot: React.ReactNode;
  if (frame < 48 || (frame >= 96 && frame < 132) || frame >= 195) {
    const pull = frame < 102 ? 0 : lerp(frame, [102, 106], [0, 1], (u) => u);
    const lean = frame >= 98 && frame < 102 ? -7 : 0;
    const rbFire = frame >= 108;
    const stick = frame >= 116 ? 'UNNEEDED ROLLBACK −0.10' : undefined;
    const inRollback = frame >= 96 && frame < 132;
    shot = (
      <>
        <SandboxHub racks={racks(rbFire)} tvOn />
        <Opus x={330} y={950} height={440} expr="deadpan" />
        <Lever x={1180} y={950} pulled={inRollback ? pull : 0} />
        <DeepSeek
          x={800}
          y={950}
          height={330}
          expr={frame >= 116 ? 'sad' : 'happy'}
          spout={frame >= 108 && frame < 132 ? 'sputter' : 'off'}
          rotate={lean}
          sticker={inRollback ? stick : undefined}
          squash={frame >= 106 && frame < 110 ? 0.6 : 0}
        />
        <Herring x={herringX} y={910} height={240} walking={herringWalk} squeak={frame >= 46 && frame < 60} flip={herringFlip} />
        <SignBoard x={herringX} y={712} text={SIGN} />
        <Bubble x={1300} y={330} appearAt={26} />
        {inRollback ? (
          <div style={{position: 'absolute', left: 0, top: 60, width: W, display: 'flex', justifyContent: 'center'}}>
            <div style={{background: C.line, border: `7px solid ${C.line}`, outline: `4px solid ${C.boardCream}`, outlineOffset: -12, borderRadius: 12, padding: '4px 36px', fontSize: 64, color: C.amber, minWidth: 1000}}>
              <Typewriter text={'rollback(service="search-svc")'} startAt={98} cps={40} />
            </div>
          </div>
        ) : null}
      </>
    );
  } else if (frame < 96) {
    shot = (
      <Camera zoom={lerp(frame, [48, 96], [1, 1.05], (u) => u)}>
        <SandboxHub racks={racks(false)} tvOn />
        <DeepSeek x={960} y={1060} height={1000} expr="happy" spout="sputter" talking={talkOpen(frame, 50, 71)} />
        <svg width={1920} height={1080} style={{position: 'absolute', left: 0, top: 0}}>
          {frame >= 50 && Math.floor(frame / 4) % 2 === 0 ? <Sparkle x={820} y={330} r={46} /> : null}
          {frame >= 50 && Math.floor(frame / 4) % 2 === 1 ? <Sparkle x={1110} y={310} r={40} /> : null}
        </svg>
      </Camera>
    );
  } else if (frame < 176) {
    const sip = frame >= 150 && frame < 160;
    shot = (
      <Camera zoom={lerp(frame, [132, 176], [1, 1.05], (u) => u)}>
        <SandboxHub racks={racks(true)} tvOn />
        <Opus x={960} y={1130} height={940} expr="deadpan" rotate={sip ? -4 : 0} talking={talkOpen(frame, 134, 46)} />
      </Camera>
    );
  } else {
    shot = (
      <>
        <SandboxHub racks={racks(true)} tvOn />
        <Herring x={960} y={960} height={720} look={[0.5, 0]} squeak={frame >= 188 && frame < 195} />
      </>
    );
  }

  return (
    <AbsoluteFill style={{background: '#000'}}>
      {shot}
      <ScreenTag x={960} y={70} text={TRAPS} tone="amber" size={42} appearAt={180} />
      <Line who="deepseek" from={48} dur={71} text="A fresh deploy! It's ALWAYS the deploy!" />
      <Line who="opus" from={132} dur={46} text="…That was a herring." />
      <Sfx src={SFX.squeak} at={4} volume={0.6} />
      <Sfx src={SFX.squeak} at={22} volume={0.6} />
      <Sfx src={SFX.switch} at={104} />
      <Sfx src={SFX.stamp} at={116} />
      <Sfx src={SFX.squeak} at={188} />
    </AbsoluteFill>
  );
};
