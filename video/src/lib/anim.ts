import {Easing, interpolate} from 'remotion';

/** Default ease: fast out, no overshoot. */
export const EASE = Easing.bezier(0.16, 1, 0.3, 1);

/** Quantize a frame to "twos" (12 fps animation). */
export const twos = (frame: number): number => frame - (frame % 2);

/** Clamped interpolate with the default ease. */
export const lerp = (
  frame: number,
  input: number[],
  output: number[],
  easing: (t: number) => number = EASE,
): number =>
  interpolate(frame, input, output, {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing,
  });

export const inRange = (frame: number, from: number, dur: number): boolean =>
  frame >= from && frame < from + dur;

/** True while speaking: mouth flaps open every other 4 frames. */
export const talkOpen = (frame: number, from: number, dur: number): boolean =>
  inRange(frame, from, dur) && Math.floor(frame / 4) % 2 === 0;
