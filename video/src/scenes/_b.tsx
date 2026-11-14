import React from 'react';
import {Easing, random} from 'remotion';
import {BALOO, C, VT323} from '../theme';
import {EASE, lerp, twos} from '../lib/anim';
import {RESULTS, REFERENCE} from '../data/results';
import {useBoil} from '../fx';
import {Typewriter} from '../ui';

/* Scoreboard shared by S11 (animated) and S12 (final state, t = 999). */

export const BX = 80;
export const BW = 1760;
export const BY = 30;
export const BH = 880;
export const BAR_X = 560;
export const BAR_PX = 1080;
export const ROW_Y = 225;
export const ROW_H = 152;

export const HEADER = 'THE REVIEW · 24 SCENARIOS × 3 RUNS = 72 SHIFTS PER MODEL';
const ALPHA = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';

/** Start frames of the three bar phases for a row (bottom row first). */
export const rowStart = (r: number) => ({
  s1: 72 + (3 - r) * 6,
  s2: 168 + (3 - r) * 6,
  s3: 264 + (3 - r) * 6,
});

/** Badge appear frame, in global badge order (3,2,2,2 badges). */
export const badgeTime = (row: number, k: number): number => {
  let n = 0;
  for (let i = 0; i < row; i++) n += RESULTS[i].badges.length;
  return 360 + 12 * (n + k);
};

const badgeW = (s: string) => s.length * 12.6 + 30;

export const Scoreboard: React.FC<{t: number; dy?: number}> = ({t, dy = 0}) => {
  const boil = useBoil(true);
  const f = twos(t);
  const tab = t < 72 ? -1 : t < 168 ? 0 : t < 264 ? 1 : 2;
  const caption = t >= 264 ? '' : t >= 168 ? 'EXPERT: THE GAP OPENS' : t >= 72 ? 'MEDIUM: TOP 3 WITHIN 0.03' : '';
  const captionAt = t >= 168 ? 168 : 72;

  // split-flap header
  const tiles = HEADER.split('').map((ch, i) => {
    const resolve = 22 + Math.floor(i * 0.7);
    let shown = ch;
    if (ch !== ' ') {
      if (t < 20) shown = ' ';
      else if (f < resolve) shown = ALPHA[Math.floor(random(`flap-${i}-${f}`) * ALPHA.length)];
    }
    return shown;
  });

  const rows = RESULTS.map((r, i) => {
    const {s1, s2, s3} = rowStart(i);
    const v = lerp(t, [s1, s1 + 30, s2, s2 + 18, s3, s3 + 24], [0, r.medium, r.medium, r.expert, r.expert, r.all]);
    const w = v * BAR_PX;
    const y = ROW_Y + i * ROW_H;
    const fill = i === 0 ? C.boardAmber : r.id.startsWith('deepseek') ? C.deepseek : C.boardCream;
    const rankAt = 276 + i * 3;
    let bx = BAR_X;
    return (
      <g key={r.id}>
        {i > 0 ? <line x1={BX + 30} x2={BX + BW - 30} y1={y - 2} y2={y - 2} stroke={C.boardCream} strokeWidth={2} opacity={0.25} /> : null}
        {t >= rankAt ? (
          <text x={BX + 56} y={y + 66} textAnchor="middle" fontFamily={BALOO} fontWeight={800} fontSize={76} fill={C.boardAmber} stroke={C.line} strokeWidth={8} paintOrder="stroke">
            {i + 1}
          </text>
        ) : null}
        <text x={BX + 100} y={y + 38} fontFamily={BALOO} fontWeight={800} fontSize={36} fill={C.boardCream}>
          {r.displayName}
        </text>
        <text x={BX + 100} y={y + 66} fontFamily={VT323} fontSize={26} fill={C.boardCream} opacity={0.75}>
          {r.id}
        </text>
        <rect x={BAR_X} y={y + 6} width={Math.max(0, w)} height={62} fill={fill} stroke={w > 0 ? C.line : 'none'} strokeWidth={6} />
        {t >= s1 ? (
          <text x={BAR_X + BAR_PX + 44} y={y + 56} fontFamily={VT323} fontSize={56} fill={C.boardAmber}>
            {v.toFixed(3)}
          </text>
        ) : null}
        {r.badges.map((b, k) => {
          const at = badgeTime(i, k);
          if (t < at) {
            bx += badgeW(b) + 12;
            return null;
          }
          const s = lerp(t, [at, at + 3], [1.5, 1], Easing.in(Easing.quad));
          const x = bx;
          bx += badgeW(b) + 12;
          const hot = k === 0;
          return (
            <g key={k} transform={`translate(${x + badgeW(b) / 2} ${y + 112}) scale(${s})`} opacity={lerp(t, [at, at + 2], [0.4, 1])}>
              <rect x={-badgeW(b) / 2} y={-22} width={badgeW(b)} height={44} rx={8} fill={hot ? C.boardAmber : C.boardCream} stroke={C.line} strokeWidth={5} />
              <text x={0} y={10} textAnchor="middle" fontFamily={VT323} fontSize={30} fill={C.line}>
                {b}
              </text>
            </g>
          );
        })}
      </g>
    );
  });

  const refX = BAR_X + REFERENCE * BAR_PX;
  const lineLen = lerp(t, [276, 290], [0, 625]);

  return (
    <div style={{position: 'absolute', left: 0, top: 0, translate: `0 ${dy}px`}}>
      <svg width={1920} height={1080} viewBox="0 0 1920 1080" style={{position: 'absolute', left: 0, top: 0, overflow: 'visible'}}>
        <g filter={boil}>
          {/* chains */}
          <line x1={BX + 90} x2={BX + 90} y1={BY} y2={-1400} stroke={C.line} strokeWidth={14} strokeDasharray="22 10" />
          <line x1={BX + BW - 90} x2={BX + BW - 90} y1={BY} y2={-1400} stroke={C.line} strokeWidth={14} strokeDasharray="22 10" />
          {/* body */}
          <rect x={BX} y={BY} width={BW} height={BH} rx={26} fill={C.teal} stroke={C.line} strokeWidth={10} />
          <rect x={BX + 16} y={BY + 16} width={BW - 32} height={BH - 32} rx={14} fill="none" stroke={C.boardCream} strokeWidth={5} />
          {[[BX + 34, BY + 34], [BX + BW - 34, BY + 34], [BX + 34, BY + BH - 34], [BX + BW - 34, BY + BH - 34]].map(([cx, cy], i) => (
            <circle key={i} cx={cx} cy={cy} r={9} fill={C.boardCream} stroke={C.line} strokeWidth={4} />
          ))}
          {/* header tiles */}
          {tiles.map((ch, i) => (
            <g key={i} transform={`translate(${BX + BW / 2 - (tiles.length * 29) / 2 + i * 29} ${BY + 22})`}>
              <rect width={28} height={58} rx={3} fill={C.line} stroke={C.boardCream} strokeWidth={2} />
              <line x1={0} x2={28} y1={29} y2={29} stroke={C.boardCream} strokeWidth={1.5} opacity={0.5} />
              <text x={14} y={45} textAnchor="middle" fontFamily={VT323} fontSize={52} fill={C.boardAmber}>
                {ch}
              </text>
            </g>
          ))}
          {/* tabs */}
          {['MEDIUM', 'EXPERT', 'ALL'].map((label, i) => (
            <g key={label} transform={`translate(${BX + 40 + i * 202} 120)`}>
              <rect width={190} height={56} rx={8} fill={tab === i ? C.boardAmber : C.line} stroke={C.boardCream} strokeWidth={4} />
              <text x={95} y={42} textAnchor="middle" fontFamily={VT323} fontSize={40} fill={tab === i ? C.line : C.boardCream}>
                {label}
              </text>
            </g>
          ))}
          {caption && t >= captionAt ? (
            <text x={BX + BW - 44} y={162} textAnchor="end" fontFamily={VT323} fontSize={48} fill={C.boardAmber}>
              {caption}
            </text>
          ) : null}
          {/* rows */}
          {rows}
          {/* zero + reference lines */}
          {t >= 276 ? (
            <>
              <line x1={BAR_X} x2={BAR_X} y1={212} y2={836} stroke={C.boardCream} strokeWidth={3} />
              <text x={BAR_X} y={202} textAnchor="middle" fontFamily={VT323} fontSize={32} fill={C.boardCream}>
                DO NOTHING · 11 CHEATS
              </text>
              <line x1={refX} x2={refX} y1={212} y2={212 + lineLen} stroke={C.gold} strokeWidth={6} strokeDasharray="16 10" />
              <text x={refX} y={202} textAnchor="middle" fontFamily={VT323} fontSize={32} fill={C.gold}>
                REFERENCE RUNBOOK
              </text>
            </>
          ) : null}
        </g>
      </svg>
      {t >= 408 ? (
        <div
          style={{
            position: 'absolute',
            left: BX + 44,
            width: BW - 88,
            top: 846,
            fontFamily: VT323,
            fontSize: 34,
            lineHeight: '36px',
            color: C.boardAmber,
            textAlign: 'left',
            paddingLeft: 280,
            whiteSpace: 'nowrap',
          }}
        >
          <Typewriter
            text="EVERYONE FIXES 90%+ OF FAULTS. THE DIFFERENCE: KNOWING WHY, AND NOT BREAKING THINGS."
            startAt={t >= 999 ? -1000 : 408 + (0)}
            cps={t >= 999 ? 9999 : 40}
          />
        </div>
      ) : null}
    </div>
  );
};

export {EASE};
