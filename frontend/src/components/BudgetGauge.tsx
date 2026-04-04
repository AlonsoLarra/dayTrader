import clsx from 'clsx';

interface Props {
  allocated: number;
  used: number;
}

export function BudgetGauge({ allocated, used }: Props) {
  const pct = allocated > 0 ? Math.min((used / allocated) * 100, 100) : 0;
  return (
    <div className="mt-2">
      <div className="flex justify-between text-xs text-gray-400 mb-1">
        <span>Budget Used</span>
        <span>${used.toFixed(2)} / ${allocated.toFixed(2)}</span>
      </div>
      <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
        <div
          className={clsx('h-full rounded-full transition-all', {
            'bg-green-500': pct < 60,
            'bg-yellow-500': pct >= 60 && pct < 80,
            'bg-red-500': pct >= 80,
          })}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
