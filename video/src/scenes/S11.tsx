import React from 'react';
import {AbsoluteFill, Easing, useCurrentFrame} from 'remotion';
import {C} from '../theme';
import {lerp, talkOpen} from '../lib/anim';
import {Portal, Shake} from '../fx';
import {DeepSeek, Hand, Herring} from '../characters';
import {SandboxHub} from '../sets';
import {Line, Sfx, SFX} from '../ui';
import {BX, BW, BY, Scoreboard, badgeTime, rowStart} from './_b';
import {RESULTS} from '../data/results';

export const S11: React.FC = () => {
  const frame = useCurrentFrame();
  const CX = BX + BW / 2;

  // board lowers (hard stop at 40), hand lets go and retracts
  const dy = lerp(frame, [8, 40], [-1000, 0], Easing.in(Easing.quad));
  const boardTop = BY + dy;
  const ringY = boardTop + 50;
  const handY = frame < 46 ? ringY : lerp(frame, [46, 62], [ringY, -200], Easing.linear);
  const shake = frame >= 40 && frame < 42;

  const closeGulp = frame >= 172 && frame < 196;
  const closeRelief = frame >= 428 && frame < 472;

  // herring hop onto the Gemini 3.1 row
  const hopT = lerp(frame, [400, 418], [0, 1], Easing.linear);
  const hopX = 1960 - hopT * 540;
  const hopY = 770 - Math.sin(hopT * Math.PI) * 120;

  const gulp = lerp(frame, [182, 185, 190], [0, 1, 0], Easing.linear);

  return (
    <AbsoluteFill>
      <SandboxHub />
      <div style={{position: 'absolute', inset: 0, background: C.teal, opacity: 0.45}} />
      <Portal x={CX} y={40} size={300} openAt={2} closeAt={64} />

      {!closeGulp && !closeRelief ? (
        <>
          <DeepSeek
            x={1790}
            y={1150}
            height={250}
            expr={frame < 84 ? 'neutral' : frame < 172 ? 'happy' : 'neutral'}
            spout={frame >= 84 && frame < 172 ? 'spray' : 'off'}
            talking={talkOpen(frame, 84, 34)}
          />
          <Shake active={shake} amount={9}>
            <Scoreboard t={frame} dy={dy} />
            {frame < 70 ? (
              <>
                <Hand x={CX} y={handY} height={460} pose={frame < 46 ? 'grab' : 'open'} />
              </>
            ) : null}
            {frame >= 400 ? <Herring x={frame < 418 ? hopX : 1420} y={frame < 418 ? hopY : 770} height={120} flip squeak={frame >= 418 && frame < 436} /> : null}
          </Shake>
        </>
      ) : null}

      {closeGulp ? (
        <AbsoluteFill style={{background: C.teal}}>
          <DeepSeek x={960} y={1220} height={1000} expr="surprised" spout="sputter" squash={gulp} />
        </AbsoluteFill>
      ) : null}
      {closeRelief ? (
        <AbsoluteFill style={{background: C.teal}}>
          <DeepSeek x={960} y={1220} height={1000} expr={frame < 448 ? 'happy' : 'neutral'} spout={frame < 448 ? 'sputter' : 'droop'} talking={talkOpen(frame, 428, 46)} />
        </AbsoluteFill>
      ) : null}

      <Line who="deepseek" from={84} dur={34} text="We're all geniuses!" />
      <Line who="deepseek" from={428} dur={46} text="Third… but fastest!" />

      <Sfx src={SFX.drumroll} at={0} />
      <Sfx src={SFX.fwump} at={2} />
      <Sfx src={SFX.tick} at={40} />
      {[28, 34, 40, 46, 52, 58].map((a) => (
        <Sfx key={a} src={SFX.clack} at={a} volume={0.5} />
      ))}
      {RESULTS.map((_, i) => (
        <Sfx key={i} src={SFX.clack} at={rowStart(i).s2} volume={0.6} />
      ))}
      <Sfx src={SFX.pop} at={184} />
      {RESULTS.flatMap((r, i) => r.badges.map((_, k) => <Sfx key={`${i}-${k}`} src={SFX.stamp} at={badgeTime(i, k)} volume={0.5} />))}
      <Sfx src={SFX.squeak} at={410} />
    </AbsoluteFill>
  );
};
