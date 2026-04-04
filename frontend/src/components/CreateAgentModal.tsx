import { useState, useEffect } from 'react';
import { X, Info } from 'lucide-react';
import { createAgent, getMarkets } from '../api/client';

interface Props {
  onClose: () => void;
  onCreate: () => void;
}

const STRATEGIES = [
  {
    value: 'auto',
    label: '🤖 Auto (Recommended)',
    description: 'Automatically picks the best strategy based on current market conditions. High volatility → RSI. Trending market → MA Crossover.',
  },
  {
    value: 'ma_crossover',
    label: '📈 MA Crossover',
    description: 'Buys when the market is trending up, sells when trending down. Works best in steady trending markets.',
  },
  {
    value: 'rsi',
    label: '⚡ RSI',
    description: 'Buys when a coin is oversold (beaten down too much), sells when overbought. Works best in volatile, sideways markets.',
  },
];

export function CreateAgentModal({ onClose, onCreate }: Props) {
  const [strategy, setStrategy] = useState('auto');
  const [symbol, setSymbol] = useState('BTC/MXN');
  const [budget, setBudget] = useState(1000);
  const [loading, setLoading] = useState(false);
  const [markets, setMarkets] = useState<string[]>(['BTC/MXN']);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMarkets().then(d => setMarkets(d.symbols)).catch(() => {});
  }, []);

  const handleCreate = async () => {
    setError(null);
    setLoading(true);
    try {
      await createAgent({ strategy, params: {}, budget, symbol });
      onCreate();
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Failed to create agent';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700 w-full max-w-md">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-white font-bold text-lg">New Trading Agent</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">
            <X size={20} />
          </button>
        </div>

        <div className="space-y-4">
          {/* Budget */}
          <div>
            <label className="block text-sm text-gray-300 font-medium mb-1">
              Budget <span className="text-gray-500 font-normal">(MXN)</span>
            </label>
            <input
              type="number"
              value={budget}
              min={100}
              onChange={e => setBudget(Number(e.target.value))}
              className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm"
              placeholder="e.g. 1000"
            />
            <p className="text-xs text-gray-500 mt-1">Paper money — no real funds at risk until you enable live mode.</p>
          </div>

          {/* Trading Pair */}
          <div>
            <label className="block text-sm text-gray-300 font-medium mb-1">Crypto</label>
            <select
              value={symbol}
              onChange={e => setSymbol(e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm"
            >
              {markets.map(s => (
                <option key={s} value={s}>{s.replace('/MXN', '')} ({s})</option>
              ))}
            </select>
          </div>

          {/* Strategy */}
          <div>
            <label className="block text-sm text-gray-300 font-medium mb-2">Strategy</label>
            <div className="space-y-2">
              {STRATEGIES.map(s => (
                <label
                  key={s.value}
                  className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                    strategy === s.value
                      ? 'border-blue-500 bg-blue-900/20'
                      : 'border-gray-600 hover:border-gray-500'
                  }`}
                >
                  <input
                    type="radio"
                    name="strategy"
                    value={s.value}
                    checked={strategy === s.value}
                    onChange={() => setStrategy(s.value)}
                    className="mt-0.5 accent-blue-500"
                  />
                  <div>
                    <div className="text-sm text-white font-medium">{s.label}</div>
                    <div className="text-xs text-gray-400 mt-0.5">{s.description}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* Auto-guardrails info */}
          <div className="bg-gray-900 rounded-lg p-3 text-xs text-gray-400 flex gap-2">
            <Info size={14} className="text-blue-400 shrink-0 mt-0.5" />
            <div>
              <span className="text-gray-300 font-medium">Auto-guardrails enabled:</span>
              {' '}Stop-loss at 3% · Max 10 trades/day · Paper mode (safe)
            </div>
          </div>

          {error && (
            <div className="text-xs text-red-400 bg-red-900/30 border border-red-800 rounded px-3 py-2">{error}</div>
          )}

          <button
            onClick={handleCreate}
            disabled={loading || budget < 100}
            className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-600 text-white rounded-lg font-medium text-sm transition-colors"
          >
            {loading ? 'Creating…' : `▶ Start Agent with $${budget.toLocaleString()} MXN`}
          </button>
        </div>
      </div>
    </div>
  );
}
