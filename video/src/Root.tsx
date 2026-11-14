import React from 'react';
import {Composition} from 'remotion';
import {FPS, H, W} from './theme';
import {Film} from './Film';
import {Sheet} from './Sheet';

export const RemotionRoot: React.FC = () => (
  <>
    <Composition id="Film" component={Film} durationInFrames={2880} fps={FPS} width={W} height={H} />
    <Composition id="Sheet" component={Sheet} durationInFrames={48} fps={FPS} width={W} height={H} />
  </>
);
