import {loadFont as loadBaloo} from '@remotion/google-fonts/Baloo2';
import {loadFont as loadVT} from '@remotion/google-fonts/VT323';

export const FPS = 24;
export const W = 1920;
export const H = 1080;

const baloo = loadBaloo('normal', {weights: ['800'], subsets: ['latin']});
const vt = loadVT('normal', {weights: ['400'], subsets: ['latin']});
export const BALOO = baloo.fontFamily;
export const VT323 = vt.fontFamily;

export const C = {
  line: '#1F1630',
  eye: '#FFFDF7',
  amber: '#FFB703',
  white: '#FFFFFF',
  black: '#000000',
  // characters
  opus: '#D97757',
  opusShadow: '#B85C3E',
  robe: '#9C8FD1',
  robeShadow: '#7D70B5',
  slipper: '#F4EEE0',
  deepseek: '#4D6BFE',
  deepseekShadow: '#3550D4',
  deepseekBelly: '#9DB0FF',
  headband: '#E8484B',
  herring: '#E2483D',
  herringShadow: '#B92F28',
  herringBelly: '#F6C9B8',
  narrator: '#3D5A80',
  portal: '#5CF2FF',
  portalCore: '#E8FFFF',
  // night exterior (S2)
  sky1: '#1B2A4A',
  sky2: '#2E4170',
  sky3: '#4A5F94',
  building: '#6B6F7E',
  buildingDark: '#575B69',
  // sandbox (S3 S5 S6 S12)
  wall: '#E9DCC2',
  floor: '#C9B58F',
  cardboard: '#C9B58F',
  brown: '#8C7556',
  rack: '#5E8C7A',
  rackDark: '#496E60',
  fireRed: '#E5383B',
  okCream: '#FFF1CC',
  // CRT film (S4 S10)
  cream: '#F2E3B3',
  coral: '#E07A5F',
  blue: '#3D5A80',
  sage: '#81B29A',
  // silent harm (S7)
  mint: '#A8E6CF',
  okGreen: '#6CC08B',
  gold: '#F2C14E',
  pink: '#F7A8B8',
  // loop (S8)
  loopRed: '#C1121F',
  navy: '#14213D',
  loopCream: '#FDF0D5',
  // noir (S9)
  slate: '#2B2D42',
  grey: '#8D99AE',
  stampRed: '#D62828',
  // scoreboard (S11)
  teal: '#0B3D4A',
  boardAmber: '#FFB703',
  boardCream: '#FFF4E0',
} as const;

/** Length in seconds of each music file in public/music. */
export const MUSIC_SECONDS = {
  'space-fighter-loop': 101.12,
  'local-forecast-elevator': 189.2049,
  pixelland: 233.795938,
  'volatile-reaction': 165.355125,
  'sneaky-snitch': 136.620425,
} as const;

export const SCENES = [
  {id: 'S01', name: '03:12', durationInFrames: 96},
  {id: 'S02', name: 'The Fall', durationInFrames: 168},
  {id: 'S03', name: 'Containerized', durationInFrames: 216},
  {id: 'S04', name: 'Orientation Film #1', durationInFrames: 240},
  {id: 'S05', name: 'The Shift', durationInFrames: 264},
  {id: 'S06', name: 'The Herring', durationInFrames: 216},
  {id: 'S07', name: 'Silent Harm', durationInFrames: 168},
  {id: 'S08', name: 'The Loop', durationInFrames: 240},
  {id: 'S09', name: 'Cheating', durationInFrames: 240},
  {id: 'S10', name: 'Orientation Film #2', durationInFrames: 240},
  {id: 'S11', name: 'The Review', durationInFrames: 504},
  {id: 'S12', name: 'The Punchline', durationInFrames: 288},
] as const;

export type SceneId = (typeof SCENES)[number]['id'];

/** Global start frame of a scene. */
export const sceneStart = (id: SceneId): number => {
  let s = 0;
  for (const sc of SCENES) {
    if (sc.id === id) return s;
    s += sc.durationInFrames;
  }
  throw new Error('unknown scene ' + id);
};
