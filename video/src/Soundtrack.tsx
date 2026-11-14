import React from 'react';
import {Sequence, staticFile} from 'remotion';
import {Audio} from '@remotion/media';
import {FPS, MUSIC_SECONDS} from './theme';

const M = (n: string) => staticFile(`music/${n}.mp3`);

const Cue: React.FC<{src: string; from: number; to: number; volume: number; trimBefore?: number}> = ({
  src,
  from,
  to,
  volume,
  trimBefore = 0,
}) => (
  <Sequence from={from} durationInFrames={to - from} layout="none">
    <Audio src={src} volume={volume} trimBefore={trimBefore} trimAfter={trimBefore + (to - from)} />
  </Sequence>
);

/** Global music. S8 and S9 own their music (C4, C5), not here. */
export const Soundtrack: React.FC = () => {
  const c1 = M('space-fighter-loop');
  const c2 = M('local-forecast-elevator');
  const c3 = M('pixelland');
  const tail = Math.floor((MUSIC_SECONDS['space-fighter-loop'] - 3) * FPS);
  return (
    <>
      <Cue src={c1} from={144} to={480} volume={0.22} />
      <Cue src={c2} from={480} to={720} volume={0.16} />
      <Cue src={c3} from={720} to={1368} volume={0.22} />
      <Cue src={c2} from={1848} to={2088} volume={0.16} trimBefore={240} />
      <Cue src={c1} from={2088} to={2664} volume={0.22} />
      <Cue src={c1} from={2808} to={2880} volume={0.22} trimBefore={tail} />
    </>
  );
};
