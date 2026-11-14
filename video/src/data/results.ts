export type ModelResult = {
  id: string;
  displayName: string;
  all: number;
  medium: number;
  expert: number;
  rAvail: number;
  rFixed: number;
  rDiag: number;
  pCollateral: number;
  callsPerShift: number;
  badges: string[];
};

export const RESULTS: ModelResult[] = [
  {id: 'gemini-4-carbon', displayName: 'Gemini 4 Carbon', all: 0.871, medium: 0.934, expert: 0.812, rAvail: 0.848, rFixed: 0.981, rDiag: 0.806, pCollateral: 0.013, callsPerShift: 76.9, badges: ['BEST OVERALL', 'finds the root cause 81%', 'cleanest hands']},
  {id: 'kimi-k3-1-pro', displayName: 'Kimi K3.1 Pro', all: 0.759, medium: 0.93, expert: 0.746, rAvail: 0.789, rFixed: 0.903, rDiag: 0.514, pCollateral: 0.037, callsPerShift: 58.3, badges: ['SOLID #2', '2nd-best diagnosis (51%)']},
  {id: 'deepseek-4-1-flash-1017', displayName: 'DeepSeek 4.1 Flash', all: 0.724, medium: 0.905, expert: 0.687, rAvail: 0.769, rFixed: 0.905, rDiag: 0.347, pCollateral: 0.058, callsPerShift: 48.6, badges: ['FASTEST: 49 calls / shift', 'strong on medium (0.905)']},
  {id: 'gemini-3.1-pro-preview', displayName: 'Gemini 3.1 Pro', all: 0.582, medium: 0.635, expert: 0.551, rAvail: 0.773, rFixed: 0.905, rDiag: 0.125, pCollateral: 0.199, callsPerShift: 63.1, badges: ['FIXES 91%... BREAKS STUFF', 'most collateral']},
];

export const REFERENCE = 0.969;
export const NOOP = 0;
