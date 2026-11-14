import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {C} from '../theme';
import {Pager} from '../characters';
import {Letterbox} from '../fx';
import {SFX, Sfx} from '../ui';

export const S01: React.FC = () => {
  const frame = useCurrentFrame();
  const chars = Math.max(0, Math.floor((frame - 6) * 0.5));
  return (
    <AbsoluteFill style={{background: '#0A0612'}}>
      {/* wooden nightstand edge */}
      <div style={{position: 'absolute', left: 0, top: 800, width: 1920, height: 280, background: C.brown, borderTop: `8px solid ${C.line}`}} />
      <div style={{position: 'absolute', left: 0, top: 880, width: 1920, height: 6, background: C.line, opacity: 0.5}} />
      <Pager x={960} y={170} width={880} lines={['03:12  PROD IS DOWN']} chars={chars} string={false} shake />
      <Sfx src={SFX.pagerBeep} at={10} />
      <Sfx src={SFX.pagerBeep} at={46} />
      <Sfx src={SFX.pagerBeep} at={84} />
      <Letterbox progress={1} />
    </AbsoluteFill>
  );
};
