import React from 'react';
import {AbsoluteFill, Easing, useCurrentFrame} from 'remotion';
import {C, H, W} from '../theme';
import {lerp, twos} from '../lib/anim';
import {DeepSeek, Hand, Opus} from '../characters';
import {Letterbox, Portal, SpeedLines, useBoil} from '../fx';
import {Box, NightExterior} from '../sets';
import {SFX, Sfx} from '../ui';

const BOX_Y = 900;

const Room: React.FC<{oy: number; flaps: number; box?: boolean}> = ({oy, flaps, box = true}) => {
  const boil = useBoil(true);
  return (
    <>
      <svg width={W} height={H} style={{position: 'absolute', left: 0, top: oy}}>
        <g filter={boil}>
          <rect width={W} height={H} fill="#2B3350" />
          <rect y={200} width={W} height={20} fill="#3A4468" />
          <rect x={120} y={120} width={380} height={420} fill={C.sky2} stroke={C.line} strokeWidth={7} />
          <line x1={310} x2={310} y1={120} y2={540} stroke={C.line} strokeWidth={7} />
          <line x1={120} x2={500} y1={330} y2={330} stroke={C.line} strokeWidth={7} />
          <rect y={900} width={W} height={180} fill={C.brown} stroke={C.line} strokeWidth={7} />
          <rect x={1300} y={780} width={200} height={120} fill={C.boardCream} stroke={C.line} strokeWidth={7} />
        </g>
      </svg>
      {box ? <Box x={960} y={oy + BOX_Y} flaps={flaps} /> : null}
    </>
  );
};

const Clouds: React.FC<{frame: number}> = ({frame}) => (
  <svg width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
    <g fill={C.sky3} stroke={C.line} strokeWidth={6}>
      <rect x={200 - frame * 0.4} y={120} width={380} height={46} rx={23} />
      <rect x={1300 - frame * 0.4} y={190} width={300} height={40} rx={20} />
    </g>
    <g fill={C.sky2} stroke={C.line} strokeWidth={6}>
      <rect x={760 - frame * 0.9} y={80} width={460} height={52} rx={26} />
      <rect x={1650 - frame * 0.9} y={300} width={360} height={44} rx={22} />
    </g>
  </svg>
);

export const S02: React.FC = () => {
  const frame = useCurrentFrame();
  const f = twos(frame);

  // whip pan 120..156
  const pan = lerp(frame, [120, 156], [0, 1], Easing.inOut(Easing.cubic));
  const camY = -pan * H;
  const zoom = lerp(frame, [0, 156], [1, 1.06], (t) => t);

  // hand (fingertip y = fingerY; Hand y param is below the tips)
  const HH = 700;
  const handTip = lerp(frame, [72, 96], [120, 430], Easing.out(Easing.cubic));
  const lift = lerp(frame, [112, 116], [0, -34], (t) => t);
  const fingerY = frame < 112 ? handTip : handTip + lift;
  const handUp = lerp(frame, [120, 130], [0, -800], Easing.in(Easing.quad));
  const showHand = frame >= 72 && frame < 132;
  const hy = fingerY + HH * 0.22 + (frame >= 120 ? handUp : 0);

  // hanging characters
  const hang = frame < 120;
  const present = frame >= 72;
  const fall = lerp(frame, [120, 156], [0, 1], Easing.in(Easing.quad));
  const sway = hang ? Math.sin(f * 0.5) * 3 : 0;
  const oy = hang ? fingerY + 340 : fingerY + 340 + fall * (H + 760 - 340 + 100);
  const dy = hang ? fingerY + 250 : fingerY + 250 + fall * (H + 760 - 250 + 100);

  const world = frame < 156;

  // final shot 156..168
  const lf = frame - 156;
  const dropY = lerp(frame, [156, 161], [-60, 780], Easing.in(Easing.quad));
  const sq = lerp(frame, [161, 163, 166], [0, 1, 0], (t) => t);
  const flaps = frame < 163 ? 0 : [0.33, 0.66, 1][Math.min(2, Math.floor((frame - 163) / 2))];
  void lf;

  return (
    <AbsoluteFill style={{background: '#0A0612'}}>
      {world ? (
        <AbsoluteFill style={{scale: String(zoom), translate: `0 ${camY}px`, filter: pan > 0 && pan < 1 ? 'blur(3px)' : undefined}}>
          <NightExterior />
          <Clouds frame={frame} />
          <Room oy={H} flaps={0} />
          <Portal x={960} y={180} size={340} openAt={48} />
          {showHand ? <Hand x={960} y={hy} height={HH} pose="grab" /> : null}
          {present ? <Opus x={820 + sway} y={oy} height={420} expr="deadpan" arm="down" /> : null}
          {present ? <DeepSeek x={1090 - sway} y={dy} height={300} expr="panic" spout="spray" flail={hang} /> : null}
        </AbsoluteFill>
      ) : (
        <AbsoluteFill>
          <Room oy={0} flaps={flaps} box={false} />
          <Opus x={820} y={Math.min(dropY, 790)} height={420} expr={sq > 0 ? 'surprised' : 'deadpan'} squash={sq} />
          <DeepSeek x={1090} y={Math.min(dropY - 20, 770)} height={300} expr="panic" spout="spray" squash={sq} />
          <Box x={960} y={BOX_Y} flaps={flaps} />
        </AbsoluteFill>
      )}
      {pan > 0 && pan < 1 ? <SpeedLines direction="down" opacity={0.6} /> : null}
      <Letterbox progress={1} />
      <Sfx src={SFX.cricket} at={0} volume={0.6} />
      <Sfx src={SFX.portalBoom} at={48} />
      <Sfx src={SFX.fwump} at={48} />
      <Sfx src={SFX.whoosh} at={120} />
      <Sfx src={SFX.whip} at={122} volume={0.6} />
      <Sfx src={SFX.fwump} at={162} />
    </AbsoluteFill>
  );
};
