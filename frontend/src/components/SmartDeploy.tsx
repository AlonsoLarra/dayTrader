import { useState } from 'react';
import { Zap, CheckCircle, BarChart2 } from 'lucide-react';
import type { PairAnalysis, DeployResult } from '../types';
import { analyzeMarket, deployPortfolio } from '../api/client';

type Status = 'idle' | 'working' | 'deployed';
type BudgetMode = 'fixed' | 'percent';

interface Props {
  walletBalance: number;
  onDeployed: () => void;
}

export function SmartDeploy({ walletBalance, onDeployed }: Props) {
  const [budgetMode, setBudgetMode] = useState<BudgetMode>('fixed');
  const [fixedAmount, setFixedAmount] = useState<string>(
    walletBalance > 0 ? String(Math.floor(walletBalance)) : '100'
  );
  const [percentAmount, setPercentAmount] = useState<number>(100);
  const [status, setStatus] = useState<Status>('idle');
  const [deployResult, setDeployResult] = useState<DeployResult | null>(null);
  const [pairs, setPairs] = useState<PairAnalysis[]>([]);
  const [error, setError] = useState<string | null>(null);

  const computedBudget =
    budgetMode === 'fixed'
      ? parseFloat(fixedAmount) || 0
      : Math.round((walletBalance || 0) * (percentAmount / 100));

  const overBudget = walletBalance > 0 && computedBudget > walletBalance;

  async function handleStart() {
    if (computedBudget <= 0) { setError('Enter a budget amount'); return; }
    if (overBudget) { setError(`Only $${walletBalance.toFixed(2)} MXN available`); return; }
    setError(null);
    setStatus('working');
    setPairs([]);

    try {
      // Step 1: Analyze
      const analysis = await analyzeMarket(10);
      setPairs(analysis.pairs);

      // Step 2: Deploy top picks automatically
      const result = await deployPortfolio({
        budget: computedBudget,
        max_agents: 3,   // sensible default — up to 3 pairs
        min_score: 20,   // low threshold so it always finds something
      });
      setDeployResult(result);
      setStatus('deployed');
      setTimeout(() => {
        setStatus('idle');
        setDeployResult(null);
        setPairs([]);
        onDeployed();
      }, 4000);
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
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-5">
      <div className="flex items-center gap-2 mb-1">
        <Zap className="w-4 h-4 text-blue-400" />
        <span className="text-sm font-semibold text-gray-200 uppercase tracking-wide">Auto-Trade</span>
      </div>
      <p className="text-xs text-gray-500 mb-5">
        Set a budget, click Start — the system analyzes all crypto pairs and automatically opens the best positions.
      </p>

      {/* Success */}
      {status === 'deployed' && deployResult && (
        <div className="flex flex-col items-center gap-3 py-4">
          <CheckCircle className="w-10 h-10 text-green-400" />
          <div className="text-green-400 font-semibold text-sm">Agents started</div>
          <div className="text-xs text-gray-400 text-center">
            ${deployResult.total_budget.toLocaleString('es-MX')} MXN spread across{' '}
            {deployResult.agent_ids.length} crypto pair{deployResult.agent_ids.length !== 1 ? 's' : ''}.
            They will start trading within 30 seconds.
          </div>
          <div className="flex flex-wrap justify-center gap-1.5 mt-1">
            {deployResult.pairs.map(p => (
              <span key={p.symbol} className="text-xs bg-blue-900/40 text-blue-300 border border-blue-800/40 rounded px-2 py-0.5 font-mono">
                {p.symbol.replace('/MXN', '')} · ${p.budget_allocated.toFixed(0)}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Working */}
      {status === 'working' && (
        <div className="flex flex-col items-center gap-3 py-4">
          <div className="flex items-center gap-3">
            <svg className="animate-spin w-5 h-5 text-blue-400" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
            </svg>
            <span className="text-sm text-gray-400">
              {pairs.length === 0 ? 'Analyzing market conditions…' : `Found ${pairs.length} pairs — creating agents…`}
            </span>
          </div>
          {pairs.length > 0 && (
            <div className="text-xs text-gray-500">
              Top picks: {pairs.slice(0, 3).map(p => p.symbol.replace('/MXN', '')).join(', ')}
            </div>
          )}
        </div>
      )}

      {/* Idle */}
      {status === 'idle' && (
        <div className="space-y-4">
          {/* Budget selector */}
          <div>
            <label className="block text-xs text-gray-500 mb-2">How much do you want to trade with?</label>
            <div className="flex gap-2">
              <div className="flex rounded overflow-hidden border border-gray-600 text-xs font-medium shrink-0">
                <button
                  onClick={() => setBudgetMode('fixed')}
                  className={`px-3 py-2 ${budgetMode === 'fixed' ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'}`}
                >
                  Fixed $
                </button>
                <button
                  onClick={() => setBudgetMode('percent')}
                  className={`px-3 py-2 ${budgetMode === 'percent' ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'}`}
                >
                  % of wallet
                </button>
              </div>

              {budgetMode === 'fixed' ? (
                <input
                  type="number"
                  min={1}
                  max={walletBalance || undefined}
                  step={10}
                  value={fixedAmount}
                  onChange={e => setFixedAmount(e.target.value)}
                  className={`flex-1 bg-gray-700 border rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500 ${overBudget ? 'border-red-500' : 'border-gray-600'}`}
                  placeholder="MXN"
                />
              ) : (
                <div className="flex-1 flex items-center gap-3">
                  <input
                    type="range" min={10} max={100} step={5}
                    value={percentAmount}
                    onChange={e => setPercentAmount(Number(e.target.value))}
                    className="flex-1 accent-blue-500"
                  />
                  <span className="text-sm text-white font-medium w-8 text-right">{percentAmount}%</span>
                </div>
              )}
            </div>

            <div className="flex items-center justify-between mt-1.5">
              <p className="text-xs text-gray-600">
                Budget will be split across the best 1–3 crypto pairs automatically.
              </p>
              <div className="text-xs">
                {computedBudget > 0 && (
                  <span className={overBudget ? 'text-red-400' : 'text-gray-500'}>
                    ${computedBudget.toFixed(2)} MXN
                    {walletBalance > 0 && ` / ${walletBalance.toFixed(2)} available`}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* What happens explanation */}
          <div className="text-xs text-gray-600 bg-gray-900/50 rounded p-3 space-y-1">
            <div className="flex items-start gap-2">
              <BarChart2 className="w-3 h-3 mt-0.5 shrink-0 text-gray-500" />
              <span>Scans 10 crypto pairs for opportunities using RSI and trend analysis</span>
            </div>
            <div className="flex items-start gap-2">
              <Zap className="w-3 h-3 mt-0.5 shrink-0 text-gray-500" />
              <span>Picks the best 1–3 and starts agents that trade automatically on your behalf</span>
            </div>
          </div>

          {error && (
            <div className="text-xs text-red-400 bg-red-950/40 border border-red-800 rounded px-3 py-2">{error}</div>
          )}

          <button
            onClick={handleStart}
            disabled={computedBudget <= 0 || overBudget}
            className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm rounded font-medium transition-colors"
          >
            Start Trading with ${computedBudget > 0 ? computedBudget.toFixed(2) : '—'} MXN
          </button>
        </div>
      )}
    </div>
  );
}
