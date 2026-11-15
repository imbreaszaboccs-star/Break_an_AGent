import React from 'react';
import {Composition} from 'remotion';
import {FPS, H, W} from './theme';
import {Film} from './Film';
import {Sheet} from './Sheet';
import {Show} from './ep2/Show';
import {DURATION as SHOW_FRAMES} from './ep2/cues';
import {Journal} from './ep3/Journal';
import {DURATION as JOURNAL_FRAMES} from './ep3/cues';
import {Spread} from './ep4/Spread';
import {DURATION as SPREAD_FRAMES, FPS as SPREAD_FPS} from './ep4/cues';
import {Pres} from './ep5/Pres';
import {DURATION as PRES_FRAMES} from './ep5/cues';

export const RemotionRoot: React.FC = () => (
  <>
    <Composition id="Film" component={Film} durationInFrames={2880} fps={FPS} width={W} height={H} />
    <Composition id="Sheet" component={Sheet} durationInFrames={48} fps={FPS} width={W} height={H} />
    <Composition id="Show" component={Show} durationInFrames={SHOW_FRAMES} fps={FPS} width={W} height={H} />
    <Composition id="Journal" component={Journal} durationInFrames={JOURNAL_FRAMES} fps={FPS} width={W} height={H} />
    <Composition id="Spread" component={Spread} durationInFrames={SPREAD_FRAMES} fps={SPREAD_FPS} width={W} height={H} />
    <Composition id="Spread2min" component={Pres} durationInFrames={PRES_FRAMES} fps={SPREAD_FPS} width={W} height={H} />
  </>
);
