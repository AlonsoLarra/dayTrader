interface RiskLevel {
  label: string;
  stopLoss: string;
  positionSize: string;
  maxBots: number;
  minScore: number;
  color: string;
}

export const RISK_LEVELS: Record<number, RiskLevel> = {
  1: { label: 'Conservative', stopLoss: '2%',   positionSize: '10%', maxBots: 1, minScore: 50, color: 'text-blue-400' },
  2: { label: 'Careful',      stopLoss: '2.5%', positionSize: '15%', maxBots: 2, minScore: 40, color: 'text-cyan-400' },
  3: { label: 'Balanced',     stopLoss: '3%',   positionSize: '25%', maxBots: 3, minScore: 30, color: 'text-green-400' },
  4: { label: 'Aggressive',   stopLoss: '4%',   positionSize: '35%', maxBots: 4, minScore: 20, color: 'text-yellow-400' },
  5: { label: 'High Risk',    stopLoss: '5%',   positionSize: '45%', maxBots: 6, minScore: 15, color: 'text-orange-400' },
};

interface Props {
  value: number;
  onChange: (level: number) => void;
}

export function RiskSlider({ value, onChange }: Props) {
  const level = RISK_LEVELS[value] ?? RISK_LEVELS[3];

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <label className="text-xs text-gray-500">Risk Level</label>
        <span className={`text-xs font-semibold ${level.color}`}>{level.label}</span>
      </div>

      <input
        type="range"
        min={1}
        max={5}
        step={1}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="w-full h-1.5 rounded-full appearance-none cursor-pointer accent-blue-500 bg-gray-600"
      />

      {/* Tick labels */}
      <div className="flex justify-between mt-1 px-0.5">
        {Object.values(RISK_LEVELS).map((l, i) => (
          <span
            key={i}
            className={`text-[10px] ${value === i + 1 ? l.color + ' font-semibold' : 'text-gray-600'}`}
          >
            {l.label.split(' ')[0]}
          </span>
        ))}
      </div>

      {/* Stats summary */}
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
        <span>Stop loss: <span className="text-gray-300">{level.stopLoss}</span></span>
        <span>Position size: <span className="text-gray-300">{level.positionSize}</span></span>
        <span>Up to <span className="text-gray-300">{level.maxBots} bot{level.maxBots !== 1 ? 's' : ''}</span></span>
        <span>Min score: <span className="text-gray-300">{level.minScore}</span></span>
      </div>
    </div>
  );
}
