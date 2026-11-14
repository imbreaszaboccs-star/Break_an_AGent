import React from 'react';
import {AbsoluteFill, Sequence, Series} from 'remotion';
import {SCENES} from './theme';
import {BoilDefs, SwirlWipe} from './fx';
import {Soundtrack} from './Soundtrack';
import {S01} from './scenes/S01';
import {S02} from './scenes/S02';
import {S03} from './scenes/S03';
import {S04} from './scenes/S04';
import {S05} from './scenes/S05';
import {S06} from './scenes/S06';
import {S07} from './scenes/S07';
import {S08} from './scenes/S08';
import {S09} from './scenes/S09';
import {S10} from './scenes/S10';
import {S11} from './scenes/S11';
import {S12} from './scenes/S12';

const COMPONENTS: Record<string, React.FC> = {S01, S02, S03, S04, S05, S06, S07, S08, S09, S10, S11, S12};
const WIPES = [1200, 1368, 2088, 2808];

export const Film: React.FC = () => (
  <AbsoluteFill style={{background: '#000'}}>
    <BoilDefs />
    <Series>
      {SCENES.map((s) => {
        const Scene = COMPONENTS[s.id];
        return (
          <Series.Sequence key={s.id} durationInFrames={s.durationInFrames} name={`${s.id} ${s.name}`}>
            <Scene />
          </Series.Sequence>
        );
      })}
    </Series>
    <Soundtrack />
    {WIPES.map((cut) => (
      <Sequence key={cut} from={cut - 8} durationInFrames={16} name={`SwirlWipe @${cut}`}>
        <SwirlWipe />
      </Sequence>
    ))}
  </AbsoluteFill>
);
