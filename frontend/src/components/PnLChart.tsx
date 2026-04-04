import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import type { Trade } from '../types';

interface Props {
  trades: Trade[];
}

export function PnLChart({ trades }: Props) {
  const sorted = [...trades]
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

  let cumPnl = 0;
  const data = sorted
    .filter(t => t.pnl !== null)
    .map(t => {
      cumPnl += t.pnl!;
      return {
        time: new Date(t.timestamp).toLocaleDateString(),
        pnl: parseFloat(cumPnl.toFixed(2)),
      };
    });

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-40 text-gray-500 text-sm">
        No trade data yet
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
        <XAxis dataKey="time" tick={{ fill: '#9CA3AF', fontSize: 11 }} />
        <YAxis tick={{ fill: '#9CA3AF', fontSize: 11 }} />
        <Tooltip
          contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151', borderRadius: '6px' }}
          labelStyle={{ color: '#9CA3AF' }}
          itemStyle={{ color: '#10B981' }}
        />
        <Line
          type="monotone"
          dataKey="pnl"
          stroke="#10B981"
          strokeWidth={2}
          dot={false}
          name="Cumulative P&L ($)"
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
