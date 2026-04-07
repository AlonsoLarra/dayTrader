import { useState } from 'react';
import { X, Zap, CheckCircle, BarChart2 } from 'lucide-react';
import { analyzeMarket, deployPortfolio } from '../api/client';
import type { PairAnalysis, DeployResult } from '../types';

interface Props {
  available: number;
  onClose: () => void;
  onDeployed: () => void;
}

type Status = 'idle' | 'working' | 'done';
type BudgetMode = 'fixed' | 'percent';

export function AutoTradeModal({ available, onClose, onDeployed }: Props) {
  const [budgetMode, setBudgetMode] = useState<BudgetMode>('fixed');
  const [fixedAmount, setFixedAmount] = useState<string>(
    available > 0 ? String(Math.floor(available)) : '100'
  );
  const [pct, setPct] = useState<number>(100);
  const [status, setStatus] = useState<Status>('idle');
  const [pairs, setPairs] = useState<PairAnalysis[]>([]);
  const [result, setResult] = useState<DeployResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const budget =
    budgetMode === 'fixed'
      ? parseFloat(fixedAmount) || 0
      : Math.round((available || 0) * (pct / 100));

  const overBudget = available > 0 && budget > available;

  async function handleStart() {
    if (budget <= 0) { setError('Enter a valid amount'); return; }
    if (overBudget) { setError(`Only $${available.toFixed(2)} MXN available`); return; }
    setError(null);
    setStatus('working');
    setPairs([]);
    setResult(null);
    try {
      const analysis = await analyzeMarket(10);
      setPairs(analysis.pairs);
      const r = await deployPortfolio({
        budget,
        max_agents: 3,
        min_score: 20,
        rotation_enabled: true,
        rotation_interval_minutes: 1,
        aggressive_rotation: true,
        min_rotation_score_delta: 1,
      });
      setResult(r);
      setStatus('done');
    } catch (e: unknown) {
      const msg =
        typeof e === 'object' && e !== null && 'response' in e
          ? String((e as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Failed')
          : e instanceof Error ? e.message : 'Failed';
      setError(msg);
      setStatus('idle');
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-gray-800 border border-gray-700 rounded-xl shadow-2xl w-full max-w-md mx-4 p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-blue-400" />
            <span className="font-semibold text-gray-100">Auto-Trade</span>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 transition-colors">
            <X size={18} />
          </button>
        </div>

        {/* Done state */}
        {status === 'done' && result && (
          <div className="flex flex-col items-center gap-4 py-4 text-center">
            <CheckCircle className="w-12 h-12 text-green-400" />
            <div className="text-green-400 font-semibold">Agents started</div>
            <p className="text-sm text-gray-400">
              ${result.total_budget.toLocaleString('es-MX')} MXN spread across{' '}
              {result.agent_ids.length} pair{result.agent_ids.length !== 1 ? 's' : ''}.
              They will begin trading within 30 seconds and re-check the full market every minute.
            </p>
            <div className="flex flex-wrap justify-center gap-2 mt-1">
              {result.pairs.map(p => (
                <span key={p.symbol}
                  className="text-xs bg-blue-900/40 text-blue-300 border border-blue-800/40 rounded-full px-3 py-1 font-mono">
                  {p.symbol.replace('/MXN', '')} · ${p.budget_allocated.toFixed(0)} MXN
                </span>
              ))}
            </div>
            <button
              onClick={onDeployed}
              className="mt-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-sm text-gray-200 rounded-lg transition-colors"
            >
              Close
            </button>
          </div>
        )}

        {/* Working state */}
        {status === 'working' && (
          <div className="flex flex-col items-center gap-4 py-6 text-center">
            <svg className="animate-spin w-8 h-8 text-blue-400" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
            </svg>
            <p className="text-sm text-gray-400">
              {pairs.length === 0
                ? 'Scanning crypto pairs for opportunities…'
                : `Found ${pairs.length} pairs — opening best positions…`}
            </p>
            {pairs.length > 0 && (
              <p className="text-xs text-gray-500">
                Top picks: {pairs.slice(0, 3).map(p => p.symbol.replace('/MXN', '')).join(', ')}
              </p>
            )}
          </div>
        )}

        {/* Idle state */}
        {status === 'idle' && (
          <div className="space-y-5">
            <p className="text-sm text-gray-400">
              Set a budget and the system will automatically find the best crypto positions now, then keep re-evaluating the market every minute.
            </p>

            {/* Budget mode toggle */}
            <div>
              <label className="block text-xs text-gray-500 mb-2">How much to trade with?</label>
              <div className="flex gap-2">
                <div className="flex rounded-lg overflow-hidden border border-gray-600 text-xs font-medium shrink-0">
                  <button
                    onClick={() => setBudgetMode('fixed')}
                    className={`px-3 py-2 transition-colors ${budgetMode === 'fixed' ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'}`}
                  >
                    Fixed $
                  </button>
                  <button
                    onClick={() => setBudgetMode('percent')}
                    className={`px-3 py-2 transition-colors ${budgetMode === 'percent' ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'}`}
                  >
                    % of wallet
                  </button>
                </div>

                {budgetMode === 'fixed' ? (
                  <input
                    type="number"
                    min={1}
                    step={10}
                    value={fixedAmount}
                    onChange={e => setFixedAmount(e.target.value)}
                    className={`flex-1 bg-gray-700 border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500 ${overBudget ? 'border-red-500' : 'border-gray-600'}`}
                    placeholder="MXN"
                  />
                ) : (
                  <div className="flex-1 flex items-center gap-3">
                    <input
                      type="range" min={10} max={100} step={5}
                      value={pct}
                      onChange={e => setPct(Number(e.target.value))}
                      className="flex-1 accent-blue-500"
                    />
                    <span className="text-sm text-white font-medium w-8 text-right">{pct}%</span>
                  </div>
                )}
              </div>

              <div className="flex justify-between mt-1.5 text-xs">
                <span className="text-gray-600">Split across up to 3 pairs automatically</span>
                <span className={overBudget ? 'text-red-400' : 'text-gray-500'}>
                  ${budget.toFixed(2)} / {available.toFixed(2)} MXN available
                </span>
              </div>
            </div>

            {/* What happens */}
            <div className="bg-gray-900/50 rounded-lg p-3 text-xs text-gray-500 space-y-1.5">
              <div className="flex items-start gap-2">
                <BarChart2 className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                <span>Scans 10 pairs using RSI and trend signals to find the best opportunities now</span>
              </div>
              <div className="flex items-start gap-2">
                <Zap className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                <span>Automatically opens positions across 1-3 top-ranked pairs, then rechecks every minute and can rotate into stronger setups</span>
              </div>
            </div>

            {error && (
              <div className="text-xs text-red-400 bg-red-950/40 border border-red-800 rounded-lg px-3 py-2">{error}</div>
            )}

            <div className="flex gap-3">
              <button
                onClick={onClose}
                className="flex-1 py-2.5 bg-gray-700 hover:bg-gray-600 text-sm text-gray-300 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleStart}
                disabled={budget <= 0 || overBudget}
                className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
              >
                <Zap size={14} />
                Start Trading
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
