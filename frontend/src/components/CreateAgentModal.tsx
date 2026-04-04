import { useState } from 'react';
import { X } from 'lucide-react';
import { createAgent } from '../api/client';

interface Props {
  onClose: () => void;
  onCreate: () => void;
}

export function CreateAgentModal({ onClose, onCreate }: Props) {
  const [strategy, setStrategy] = useState('ma_crossover');
  const [budget, setBudget] = useState(1000);
  const [fastPeriod, setFastPeriod] = useState(9);
  const [slowPeriod, setSlowPeriod] = useState(21);
  const [rsiPeriod, setRsiPeriod] = useState(14);
  const [loading, setLoading] = useState(false);

  const handleCreate = async () => {
    setLoading(true);
    const params: Record<string, number> =
      strategy === 'ma_crossover'
        ? { fast_period: fastPeriod, slow_period: slowPeriod }
        : { period: rsiPeriod };
    try {
      await createAgent({ strategy, params, budget });
      onCreate();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700 w-full max-w-md">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-white font-bold">Create Agent</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">
            <X size={20} />
          </button>
        </div>
        <div className="space-y-4">
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
            <label className="block text-xs text-gray-400 mb-1">Budget (USD)</label>
            <input
              type="number"
              value={budget}
              onChange={e => setBudget(Number(e.target.value))}
              className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm"
            />
          </div>
          {strategy === 'ma_crossover' && (
            <div className="grid grid-cols-2 gap-3">
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
            </div>
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
          <button
            onClick={handleCreate}
            disabled={loading}
            className="w-full py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-600 text-white rounded font-medium text-sm"
          >
            {loading ? 'Creating...' : 'Create Agent'}
          </button>
        </div>
      </div>
    </div>
  );
}
