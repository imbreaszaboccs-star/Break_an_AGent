import React from 'react';
import {AbsoluteFill} from 'remotion';
import {BoilDefs} from './fx';
import {SandboxHub} from './sets';
import {DeepSeek, Hand, Herring, Opus, Pager} from './characters';
import {ScreenTag} from './ui';

/** Character reference sheet for visual review. */
export const Sheet: React.FC = () => (
  <AbsoluteFill>
    <BoilDefs />
    <SandboxHub tvOn />
    {/* Opus row */}
    <Opus x={240} y={400} height={320} expr="deadpan" />
    <Opus x={720} y={400} height={320} expr="surprised" arm="up" />
    <Opus x={1200} y={400} height={320} expr="happy" talking />
    <Opus x={1680} y={400} height={320} expr="smug" arm="lever" mug={false} />
    {/* DeepSeek row */}
    <DeepSeek x={240} y={740} height={260} expr="panic" spout="spray" flail />
    <DeepSeek x={720} y={740} height={260} expr="happy" spout="sputter" talking />
    <DeepSeek x={1200} y={740} height={260} expr="sad" spout="droop" />
    <DeepSeek x={1680} y={740} height={260} expr="neutral" sticker="UNNEEDED ROLLBACK -0.10" />
    {/* Props row */}
    <Herring x={150} y={1050} height={150} sign="DEPLOY v2.8.1" />
    <Hand x={520} y={1060} height={300} pose="open" />
    <Hand x={760} y={1060} height={300} pose="grab" />
    <Pager x={1420} y={810} width={400} lines={['03:12  PROD IS DOWN', '12 SERVICES DOWN']} string={false} />
    <ScreenTag x={240} y={440} text="OPUS deadpan" size={30} tone="cream" />
    <ScreenTag x={720} y={440} text="surprised + arm up" size={30} tone="cream" />
    <ScreenTag x={1200} y={440} text="happy + talking" size={30} tone="cream" />
    <ScreenTag x={1680} y={440} text="smug + lever" size={30} tone="cream" />
    <ScreenTag x={240} y={760} text="DEEPSEEK panic+spray" size={30} tone="cream" />
    <ScreenTag x={720} y={760} text="happy+sputter" size={30} tone="cream" />
    <ScreenTag x={1200} y={760} text="sad+droop" size={30} tone="cream" />
    <ScreenTag x={1680} y={760} text="sticker" size={30} tone="cream" />
    <ScreenTag x={150} y={1068} text="HERRING" size={26} tone="amber" />
    <ScreenTag x={640} y={1068} text="HAND open / grab" size={26} tone="amber" />
    <ScreenTag x={1420} y={1060} text="PAGER" size={26} tone="amber" />
  </AbsoluteFill>
);
