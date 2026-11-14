import React from 'react';
import {AbsoluteFill, Easing, useCurrentFrame} from 'remotion';
import {BALOO, C, H, VT323, W} from '../theme';
import {lerp, twos} from '../lib/anim';
import {Crt, useBoil} from '../fx';
import {Line, Sfx, SFX} from '../ui';

const BAR_X = 160;
const BAR_W = 1600;
const BAR_Y = 470;
const BAR_H = 150;

const Anvil: React.FC<{x: number; bottom: number}> = ({x, bottom}) => (
  <g transform={`translate(${x} ${bottom})`}>
    <path d="M-190 -200 L190 -200 L190 -140 L90 -120 L60 -50 L120 -50 L120 0 L-120 0 L-120 -50 L-60 -50 L-90 -120 L-190 -140 Z" fill="#6D7585" stroke={C.line} strokeWidth={8} strokeLinejoin="round" />
    <path d="M-190 -200 L190 -200 L190 -175 L-190 -175 Z" fill="#8D99AE" />
    <text x={0} y={-218} textAnchor="middle" fontFamily={VT323} fontSize={58} fill={C.line}>
      DATA LOSS ×0.25
    </text>
  </g>
);

const Bomb: React.FC<{x: number; y: number}> = ({x, y}) => (
  <g transform={`translate(${x} ${y})`}>
    <circle r={46} fill={C.line} stroke={C.line} strokeWidth={6} />
    <circle cx={-14} cy={-14} r={12} fill="#4A4060" />
    <rect x={-8} y={-66} width={16} height={26} fill={C.cream} stroke={C.line} strokeWidth={5} />
    <path d="M0 -66 q12 -22 30 -18" fill="none" stroke={C.line} strokeWidth={5} />
    <path d="M32 -88 l8 -14 l4 14 l14 4 l-14 6 l-4 14 l-8 -14 z" fill={C.amber} stroke={C.line} strokeWidth={3} />
  </g>
);

const Content: React.FC = () => {
  const frame = useCurrentFrame();
  const boil = useBoil(true);
  const g = twos(frame);
  const title = frame < 36;

  const w1 = lerp(g, [40, 84], [0, 0.6 * BAR_W], Easing.linear);
  const w2 = lerp(g, [84, 116], [0, 0.3 * BAR_W], Easing.linear);
  const w3 = lerp(g, [116, 140], [0, 0.1 * BAR_W], Easing.linear);

  const hit = 172;
  const anvilBottom = frame < hit ? lerp(frame, [150, hit], [-30, BAR_Y], Easing.in(Easing.quad)) : BAR_Y + (BAR_H * 0.75) * lerp(frame, [hit, hit + 4], [0, 1], Easing.linear);
  const sq = frame < hit ? 1 : lerp(frame, [hit, hit + 4], [1, 0.25], Easing.linear);
  const bombIn = frame >= 190 ? lerp(frame, [190, 193], [0.75, 1]) : 0;
  const sackIn = frame >= 204 ? lerp(frame, [204, 207], [0.75, 1]) : 0;

  return (
    <AbsoluteFill style={{background: C.cream}}>
      <svg width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
        <g filter={boil}>
          {title ? (
            <>
              {[900, 700, 500, 300].map((r, i) => (
                <circle key={r} cx={960} cy={540} r={r} fill={i % 2 ? C.cream : C.coral} opacity={0.35} />
              ))}
            </>
          ) : (
            <>
              <rect x={0} y={0} width={W} height={20} fill={C.coral} />
              <rect x={0} y={H - 20} width={W} height={20} fill={C.coral} />
            </>
          )}
        </g>
      </svg>
      {title ? (
        <div style={{position: 'absolute', left: 160, right: 160, top: 250, textAlign: 'center', fontFamily: BALOO, fontWeight: 800, fontSize: 150, lineHeight: '150px', color: C.blue, WebkitTextStroke: `16px ${C.line}`, paintOrder: 'stroke fill', strokeLinejoin: 'round'}}>
          How is your shift graded?
        </div>
      ) : (
        <>
          <div style={{position: 'absolute', left: 0, right: 0, top: 70, textAlign: 'center', fontFamily: BALOO, fontWeight: 800, fontSize: 84, color: C.blue, WebkitTextStroke: '10px #1F1630', paintOrder: 'stroke fill', strokeLinejoin: 'round'}}>
            How is your shift graded?
          </div>
          <svg width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
            <g filter={boil}>
              <g transform={`translate(0 ${BAR_Y + BAR_H}) scale(1 ${sq}) translate(0 ${-(BAR_Y + BAR_H)})`}>
                <rect x={BAR_X} y={BAR_Y} width={BAR_W} height={BAR_H} fill="#FFFDF7" stroke={C.line} strokeWidth={8} />
                {w1 > 0 ? <rect x={BAR_X} y={BAR_Y} width={w1} height={BAR_H} fill={C.coral} stroke={C.line} strokeWidth={8} /> : null}
                {w2 > 0 ? <rect x={BAR_X + 0.6 * BAR_W} y={BAR_Y} width={w2} height={BAR_H} fill={C.sage} stroke={C.line} strokeWidth={8} /> : null}
                {w3 > 0 ? <rect x={BAR_X + 0.9 * BAR_W} y={BAR_Y} width={w3} height={BAR_H} fill={C.blue} stroke={C.line} strokeWidth={8} /> : null}
              </g>
              {g >= 44 ? (
                <text x={BAR_X + 0.3 * BAR_W} y={BAR_Y + BAR_H + 56} textAnchor="middle" fontFamily={VT323} fontSize={62} fill={C.line} opacity={frame >= hit ? 0 : 1}>
                  60% TRAFFIC SERVED
                </text>
              ) : null}
              {g >= 86 ? (
                <text x={BAR_X + 0.75 * BAR_W} y={BAR_Y + BAR_H + 56} textAnchor="middle" fontFamily={VT323} fontSize={62} fill={C.line} opacity={frame >= hit ? 0 : 1}>
                  30% FAULTS FIXED
                </text>
              ) : null}
              {g >= 118 ? (
                <text x={BAR_X + BAR_W} y={BAR_Y + BAR_H + 110} textAnchor="end" fontFamily={VT323} fontSize={62} fill={C.line} opacity={frame >= hit ? 0 : 1}>
                  10% ROOT CAUSE
                </text>
              ) : null}
              {frame >= 150 ? <Anvil x={960} bottom={anvilBottom} /> : null}
              {bombIn > 0 ? (
                <g transform={`translate(0 700) scale(${bombIn})`} style={{transformOrigin: '420px 700px'}}>
                  <Bomb x={300} y={0} />
                  <Bomb x={420} y={0} />
                </g>
              ) : null}
              {sackIn > 0 ? (
                <g transform={`translate(1360 700) scale(${sackIn})`}>
                  <path d="M-60 40 C-90 -10 -50 -40 -20 -60 L-34 -90 L34 -90 L20 -60 C50 -40 90 -10 60 40 Z" fill={C.gold} stroke={C.line} strokeWidth={8} strokeLinejoin="round" />
                  <text x={0} y={22} textAnchor="middle" fontFamily={BALOO} fontWeight={800} fontSize={60} fill={C.line}>
                    $
                  </text>
                </g>
              ) : null}
            </g>
          </svg>
          {bombIn > 0 ? (
            <div style={{position: 'absolute', left: 520, top: 650, fontFamily: VT323, fontSize: 44, lineHeight: '46px', color: C.line, whiteSpace: 'pre'}}>
              {'−0.05 / −0.10\nPER UNNEEDED CHANGE'}
            </div>
          ) : null}
          {sackIn > 0 ? (
            <div style={{position: 'absolute', left: 1450, top: 650, fontFamily: VT323, fontSize: 44, lineHeight: '46px', color: C.line, whiteSpace: 'pre'}}>
              {'OVERSPEND\n−0.10'}
            </div>
          ) : null}
        </>
      )}
    </AbsoluteFill>
  );
};

export const S10: React.FC = () => {
  return (
    <AbsoluteFill>
      <Crt onAt={0} offAt={234}>
        <Content />
      </Crt>
      <Line who="narrator" from={4} dur={39} text="How is your shift graded?" />
      <Line who="narrator" from={48} dur={98} text="Sixty: traffic actually served. Thirty: faults truly fixed. Ten: the exact root cause." />
      <Line who="narrator" from={158} dur={48} text="Lose data? Quartered. Break things? Points off." />
      <Sfx src={SFX.tick} at={40} volume={0.5} />
      <Sfx src={SFX.tick} at={84} volume={0.5} />
      <Sfx src={SFX.tick} at={116} volume={0.5} />
      <Sfx src={SFX.stamp} at={172} />
      <Sfx src={SFX.pop} at={190} />
      <Sfx src={SFX.pop} at={204} />
    </AbsoluteFill>
  );
};
