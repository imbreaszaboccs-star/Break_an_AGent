import React from 'react';
import {AbsoluteFill, Easing, random, Sequence, staticFile, useCurrentFrame} from 'remotion';
import {Audio} from '@remotion/media';
import {BALOO, C, H, VT323, W} from '../theme';
import {lerp, talkOpen, twos} from '../lib/anim';
import {Shake, useBoil} from '../fx';
import {DeepSeek, Opus} from '../characters';
import {Line, ScreenTag, Sfx, SFX, Typewriter} from '../ui';
import {Lever} from '../sets';

const MUSIC = staticFile('music/volatile-reaction.mp3');
const VOL = 0.22;

const Corridor: React.FC<{flash?: boolean}> = ({flash}) => {
  const boil = useBoil(true);
  return (
    <svg width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
      <g filter={boil}>
        <rect width={W} height={H} fill={flash ? C.navy : C.loopRed} />
        {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
          <rect key={i} x={i * 280 + 120} y={0} width={60} height={800} fill={C.loopCream} opacity={0.18} />
        ))}
        <rect y={800} width={W} height={280} fill={C.navy} />
        <rect y={780} width={W} height={26} fill={C.loopCream} stroke={C.line} strokeWidth={6} />
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <rect key={i} x={i * 400 - 40} y={920} width={200} height={14} fill={C.loopRed} opacity={0.6} />
        ))}
      </g>
    </svg>
  );
};

const Door: React.FC<{x: number}> = ({x}) => {
  const boil = useBoil(true);
  return (
    <svg width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
      <g filter={boil} transform={`translate(${x} 800)`}>
        <rect x={-130} y={-480} width={260} height={480} fill={C.loopCream} stroke={C.line} strokeWidth={8} />
        <rect x={-100} y={-450} width={200} height={450} fill={C.navy} stroke={C.line} strokeWidth={6} />
        <circle cx={70} cy={-220} r={12} fill={C.gold} stroke={C.line} strokeWidth={4} />
        <rect x={-110} y={-540} width={220} height={54} rx={6} fill={C.loopCream} stroke={C.line} strokeWidth={6} />
        <text x={0} y={-499} textAnchor="middle" fontFamily={VT323} fontSize={48} fill={C.loopRed}>
          CACHE
        </text>
      </g>
    </svg>
  );
};

const COLS = 8;
const ROWS = 5;
const CW = W / COLS;
const CH = 216;

const Grid: React.FC<{revealFrom: number; popFrom?: number; popTo?: number}> = ({revealFrom, popFrom = 9999, popTo = 9999}) => {
  const frame = useCurrentFrame();
  const out: React.ReactNode[] = [];
  const g = twos(frame);
  for (let k = 0; k < COLS * ROWS; k++) {
    const c = k % COLS;
    const r = Math.floor(k / COLS);
    const show = revealFrom + Math.floor(random(`gr-${k}`) * 14);
    const pop = popFrom + Math.floor(random(`gp-${k}`) * (popTo - popFrom));
    if (frame < show) continue;
    const cx = c * CW + CW / 2;
    const cy = 150 + r * CH;
    if (g >= pop + 4) continue;
    if (g >= pop) {
      out.push(
        <svg key={k} width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
          <circle cx={cx} cy={cy + 40} r={60 + (g - pop) * 14} fill="none" stroke={C.loopCream} strokeWidth={6} />
        </svg>,
      );
      continue;
    }
    out.push(
      <React.Fragment key={k}>
        <Opus x={cx - 50} y={cy + 100} height={110} expr="surprised" mug={false} />
        <DeepSeek x={cx + 50} y={cy + 100} height={90} expr="panic" flip />
      </React.Fragment>,
    );
  }
  return <>{out}</>;
};

export const S08: React.FC = () => {
  const frame = useCurrentFrame();
  const run = (f: number) => (Math.floor(f / 2) % 2 ? -10 : 0);

  // ---- music ----
  const music = (
    <>
      <Sequence from={0} durationInFrames={48} layout="none">
        <Audio src={MUSIC} volume={VOL} trimBefore={0} trimAfter={48} />
      </Sequence>
      {[0, 1, 2, 3, 4].map((k) => (
        <Sequence key={k} from={48 + 12 * k} durationInFrames={12} layout="none">
          <Audio src={MUSIC} volume={VOL} trimBefore={48} trimAfter={60} />
        </Sequence>
      ))}
      <Sequence from={175} durationInFrames={65} layout="none">
        <Audio src={MUSIC} volume={VOL} trimBefore={60} trimAfter={125} />
      </Sequence>
    </>
  );

  // ---- shot 1: door run (0..48) ----
  const shot1 = () => {
    const opusIn = lerp(frame, [2, 12], [-300, 220], Easing.linear);
    const dsIn = lerp(frame, [0, 10], [-120, 220], Easing.linear);
    const opusOut = lerp(frame, [14, 26], [1700, 1520], Easing.linear);
    const dsOut = lerp(frame, [12, 24], [1700, 1330], Easing.linear);
    const settled = frame >= 26;
    return (
      <>
        <Corridor />
        <Door x={220} />
        <Door x={1700} />
        {frame < 24 ? (
          <>
            {frame < 10 ? <DeepSeek x={dsIn} y={880 + run(frame)} height={260} expr="panic" flail /> : null}
            {frame < 12 ? <Opus x={opusIn} y={880 + run(frame)} height={380} expr="surprised" /> : null}
          </>
        ) : null}
        {/* exits on the right, facing left */}
        {frame >= 12 ? <DeepSeek x={settled ? 1330 : dsOut} y={880 + (settled ? 0 : run(frame))} height={260} flip expr={settled ? 'surprised' : 'panic'} /> : null}
        {frame >= 14 ? <Opus x={settled ? 1520 : opusOut} y={880 + (settled ? 0 : run(frame))} height={380} flip expr={settled ? 'surprised' : 'deadpan'} /> : null}
        {/* the copies */}
        {frame >= 20 ? (
          <>
            <Opus x={560} y={880} height={380} expr="surprised" mug />
            <DeepSeek x={790} y={880} height={260} expr="panic" />
          </>
        ) : null}
      </>
    );
  };

  // ---- shot 2: multiplication (48..96) ----
  const shot2 = () => {
    const stage = frame < 66 ? 0 : frame < 84 ? 1 : 2;
    return (
      <Shake active amount={frame < 66 ? 4 : 10}>
        <Corridor flash={frame >= 84 && Math.floor(frame / 2) % 2 === 0} />
        {stage >= 1 ? (
          <>
            <Opus x={400} y={640} height={230} expr="panic" />
            <DeepSeek x={560} y={640} height={170} expr="panic" />
            <Opus x={1360} y={640} height={230} flip expr="panic" />
            <DeepSeek x={1200} y={640} height={170} flip expr="panic" />
          </>
        ) : null}
        {stage >= 2 ? <Grid revealFrom={84} /> : null}
        <Opus x={620} y={880} height={380} expr="panic" />
        <DeepSeek x={850} y={860} height={260} expr="panic" flail talking={talkOpen(frame, 39, 63)} spout="spray" />
        <Opus x={1480} y={880} height={380} flip expr="panic" />
        <DeepSeek x={1250} y={860} height={260} flip expr="panic" flail spout="spray" />
      </Shake>
    );
  };

  // ---- shot 3: DS close (96..108) ----
  const shot3 = () => (
    <Shake active amount={12}>
      <Corridor flash={Math.floor(frame / 2) % 2 === 0} />
      <Grid revealFrom={0} />
      <DeepSeek x={960} y={1230} height={1000} expr="panic" flail={false} spout="spray" talking={talkOpen(frame, 39, 63)} />
    </Shake>
  );

  // ---- shot 4: Opus silence close (108..127) ----
  const shot4 = () => (
    <>
      <Corridor />
      <Opus x={960} y={1300} height={1150} expr="deadpan" mug />
    </>
  );

  // ---- shot 5: lever (127..175) ----
  const pulled = lerp(frame, [140, 150], [0, 1]);
  const shot5 = () => (
    <>
      <Corridor />
      <Opus x={960} y={880} height={600} expr="deadpan" arm="lever" mug={false} talking={talkOpen(frame, 127, 37)} />
      <Lever x={960 - 192} y={880 - 153 + 204} pulled={pulled} />
      <div style={{position: 'absolute', left: 190, top: 90, width: 1540, padding: '10px 26px', background: C.line, border: `6px solid ${C.loopCream}`, borderRadius: 10, fontFamily: VT323, fontSize: 44, color: C.amber, whiteSpace: 'pre'}}>
        <Typewriter text={'set_config(service="redis-main", key="timeout_ms", value=1500)'} startAt={128} cps={60} />
      </div>
    </>
  );

  // ---- shot 6: pop (175..204) ----
  const shot6 = () => {
    const copyGone = twos(frame) >= 196;
    return (
      <>
        <Corridor />
        <Grid revealFrom={0} popFrom={176} popTo={198} />
        {!copyGone ? (
          <>
            <Opus x={1480} y={880} height={380} flip expr="surprised" />
            <DeepSeek x={1250} y={860} height={260} flip expr="panic" />
          </>
        ) : null}
        <Opus x={620} y={880} height={380} expr="deadpan" arm="lever" />
        <DeepSeek x={850} y={860} height={260} expr="surprised" />
      </>
    );
  };

  // ---- shot 7: DS reaction (204..240) ----
  const shot7 = () => (
    <>
      <Corridor />
      <DeepSeek x={960} y={1230} height={920} expr="sad" spout="droop" />
      <ScreenTag x={960} y={90} text="R9 CACHE LOOP: hardest family in the test (avg 0.29)" appearAt={206} />
      <ScreenTag x={960} y={180} text="DeepSeek: 0.05" tone="amber" appearAt={218} />
    </>
  );

  return (
    <AbsoluteFill>
      {music}
      {frame < 30 ? shot1() : null}
      {frame >= 30 && frame < 39 ? (
        <>
          <Corridor />
          <Opus x={960} y={1300} height={1150} expr="surprised" />
        </>
      ) : null}
      {frame >= 39 && frame < 48 ? (
        <>
          <Corridor />
          <DeepSeek x={960} y={1260} height={1000} expr="panic" spout="spray" />
        </>
      ) : null}
      {frame >= 48 && frame < 96 ? shot2() : null}
      {frame >= 96 && frame < 108 ? shot3() : null}
      {frame >= 108 && frame < 127 ? shot4() : null}
      {frame >= 127 && frame < 175 ? shot5() : null}
      {frame >= 175 && frame < 204 ? shot6() : null}
      {frame >= 204 ? shot7() : null}

      <Line who="deepseek" from={36} dur={64} text="We've been here. We've been HERE. WE'VE BEEN—" />
      <Line who="opus" from={127} dur={37} text="Set the timeout." />
      <Sfx src={SFX.switch} at={146} />
      <Sfx src={SFX.whoosh} at={14} volume={0.5} />
      {[176, 180, 184, 188, 192, 196].map((a) => (
        <Sfx key={a} src={SFX.pop} at={a} volume={0.6} />
      ))}
    </AbsoluteFill>
  );
};

void BALOO;
