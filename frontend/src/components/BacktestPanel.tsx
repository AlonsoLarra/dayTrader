import { useState } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import type { BacktestResult } from '../types';
import { runBacktest } from '../api/client';

export function BacktestPanel() {
  const [strategy, setStrategy] = useState('ma_crossover');
  const [symbol, setSymbol] = useState('BTC/USDT');
  const [timeframe, setTimeframe] = useState('1h');
  const [startDate, setStartDate] = useState('2024-01-01');
  const [endDate, setEndDate] = useState('2024-06-01');
  const [capital, setCapital] = useState(10000);
  const [fastPeriod, setFastPeriod] = useState(9);
  const [slowPeriod, setSlowPeriod] = useState(21);
  const [rsiPeriod, setRsiPeriod] = useState(14);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    const params: Record<string, number> =
      strategy === 'ma_crossover'
        ? { fast_period: fastPeriod, slow_period: slowPeriod }
        : { period: rsiPeriod };

    try {
      const data = await runBacktest({
        strategy,
        params,
        symbol,
        timeframe,
        start_date: startDate,
        end_date: endDate,
        initial_capital: capital,
      });
      if (data.error) {
        setError(data.error);
      } else {
        setResult(data);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Backtest failed');
    } finally {
      setLoading(false);
    }
  };

  const equityData =
    result?.equity_curve.map(([ts, val]) => ({
      time: new Date(ts).toLocaleDateString(),
      equity: parseFloat(val.toFixed(2)),
    })) ?? [];

  return (
    <div className="space-y-6">
      <form onSubmit={handleSubmit} className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h2 className="text-lg font-bold text-white mb-4">Backtest Configuration</h2>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Strategy</label>
            <select
              value={strategy}
              onChange={e => setStrategy(e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm"
            >
              <option value="ma_crossover">MA Crossover</option>
              <option value="rsi">RSI</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Symbol</label>
            <select
              value={symbol}
              onChange={e => setSymbol(e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm"
            >
              <option value="BTC/USDT">BTC/USDT</option>
              <option value="ETH/USDT">ETH/USDT</option>
              <option value="SOL/USDT">SOL/USDT</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Timeframe</label>
            <select
              value={timeframe}
              onChange={e => setTimeframe(e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm"
            >
              <option value="1h">1h</option>
              <option value="4h">4h</option>
              <option value="1d">1d</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Start Date</label>
            <input
              type="date"
              value={startDate}
              onChange={e => setStartDate(e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">End Date</label>
            <input
              type="date"
              value={endDate}
              onChange={e => setEndDate(e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Initial Capital ($)</label>
            <input
              type="number"
              value={capital}
              onChange={e => setCapital(Number(e.target.value))}
              className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm"
            />
          </div>

          {strategy === 'ma_crossover' && (
            <>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Fast Period</label>
                <input
                  type="number"
                  value={fastPeriod}
                  onChange={e => setFastPeriod(Number(e.target.value))}
                  className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Slow Period</label>
                <input
                  type="number"
                  value={slowPeriod}
                  onChange={e => setSlowPeriod(Number(e.target.value))}
                  className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm"
                />
              </div>
            </>
          )}

          {strategy === 'rsi' && (
            <div>
              <label className="block text-xs text-gray-400 mb-1">RSI Period</label>
              <input
                type="number"
                value={rsiPeriod}
                onChange={e => setRsiPeriod(Number(e.target.value))}
                className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm"
              />
            </div>
          )}
        </div>

        <button
          type="submit"
          disabled={loading}
          className="mt-4 px-6 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-600 text-white rounded font-medium text-sm"
        >
          {loading ? 'Running...' : 'Run Backtest'}
        </button>
      </form>

      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300 text-sm">
          {error}
        </div>
      )}

      {result && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {[
              {
                label: 'Total Return',
                value: `${result.total_return_pct > 0 ? '+' : ''}${result.total_return_pct}%`,
                positive: result.total_return_pct > 0,
              },
              {
                label: 'Win Rate',
                value: `${result.win_rate}%`,
                positive: result.win_rate > 50,
              },
              {
                label: 'Total Trades',
                value: String(result.total_trades),
                positive: true,
              },
              {
                label: 'Max Drawdown',
                value: `${result.max_drawdown_pct}%`,
                positive: false,
              },
              {
                label: 'Sharpe Ratio',
                value: String(result.sharpe_ratio),
                positive: result.sharpe_ratio > 1,
              },
            ].map(stat => (
              <div key={stat.label} className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                <div className="text-xs text-gray-400 mb-1">{stat.label}</div>
                <div
                  className={`text-xl font-bold ${stat.positive ? 'text-green-400' : 'text-red-400'}`}
                >
                  {stat.value}
                </div>
              </div>
            ))}
          </div>

          <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <h3 className="text-sm font-medium text-gray-300 mb-4">Equity Curve</h3>
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={equityData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="time" tick={{ fill: '#9CA3AF', fontSize: 11 }} />
                <YAxis tick={{ fill: '#9CA3AF', fontSize: 11 }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1F2937',
                    border: '1px solid #374151',
                    borderRadius: '6px',
                  }}
                  labelStyle={{ color: '#9CA3AF' }}
                />
                <Line
                  type="monotone"
                  dataKey="equity"
                  stroke="#3B82F6"
                  strokeWidth={2}
                  dot={false}
                  name="Equity ($)"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}
