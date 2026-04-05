import { useState } from 'react';
import { Zap, BarChart2, ChevronRight, CheckCircle } from 'lucide-react';
import type { PairAnalysis, DeployResult } from '../types';
import { analyzeMarket, deployPortfolio } from '../api/client';

type Status = 'idle' | 'analyzing' | 'analyzed' | 'deploying' | 'deployed';
type BudgetMode = 'fixed' | 'percent';

interface Props {
  walletBalance: number;
  onDeployed: () => void;
}

function ScoreBar({ score }: { score: number }) {
  const color =
    score >= 65 ? 'bg-green-500' :
    score >= 40 ? 'bg-yellow-500' :
    'bg-red-500';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${score}%` }} />
      </div>
      <span className="text-xs font-mono text-gray-300 w-7 text-right">{score}</span>
    </div>
  );
}

function StrategyBadge({ strategy }: { strategy: string }) {
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
      strategy === 'rsi'
        ? 'bg-purple-900/60 text-purple-300'
        : 'bg-blue-900/60 text-blue-300'
    }`}>
      {strategy === 'rsi' ? 'RSI' : 'MA Cross'}
    </span>
  );
}

export function SmartDeploy({ walletBalance, onDeployed }: Props) {
  const [budgetMode, setBudgetMode] = useState<BudgetMode>('fixed');
  const [fixedAmount, setFixedAmount] = useState<string>('500');
  const [percentAmount, setPercentAmount] = useState<number>(20);
  const [maxAgents, setMaxAgents] = useState<number>(3);
  const [minScore, setMinScore] = useState<number>(30);
  const [status, setStatus] = useState<Status>('idle');
  const [pairs, setPairs] = useState<PairAnalysis[]>([]);
  const [deployResult, setDeployResult] = useState<DeployResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const computedBudget =
    budgetMode === 'fixed'
      ? parseFloat(fixedAmount) || 0
      : Math.round(walletBalance * (percentAmount / 100));

  async function handleAnalyze() {
    setError(null);
    setStatus('analyzing');
    try {
      const data = await analyzeMarket(10);
      setPairs(data.pairs);
      setStatus('analyzed');
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Analysis failed');
      setStatus('idle');
    }
  }

  async function handleDeploy() {
    if (computedBudget < 50) {
      setError('Minimum budget is $50 MXN');
      return;
    }
    setError(null);
    setStatus('deploying');
    try {
      const result = await deployPortfolio({
        budget: computedBudget,
        max_agents: maxAgents,
        min_score: minScore,
      });
      setDeployResult(result);
      setStatus('deployed');
      setTimeout(() => {
        setStatus('idle');
        setDeployResult(null);
        setPairs([]);
        onDeployed();
      }, 3000);
    } catch (e: unknown) {
      const msg =
        e instanceof Error ? e.message :
        typeof e === 'object' && e !== null && 'response' in e
          ? String((e as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Deploy failed')
          : 'Deploy failed';
      setError(msg);
      setStatus('analyzed');
    }
  }

  function reset() {
    setStatus('idle');
    setPairs([]);
    setDeployResult(null);
    setError(null);
  }

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-5">
      <div className="flex items-center gap-2 mb-4">
        <Zap className="w-4 h-4 text-blue-400" />
        <span className="text-sm font-semibold text-gray-200 uppercase tracking-wide">Smart Deploy</span>
        <span className="text-xs text-gray-500 ml-1">— auto-analyze and allocate budget</span>
      </div>

      {/* Success state */}
      {status === 'deployed' && deployResult && (
        <div className="flex flex-col items-center gap-3 py-6">
          <CheckCircle className="w-10 h-10 text-green-400" />
          <div className="text-green-400 font-semibold">Deployed successfully</div>
          <div className="text-sm text-gray-400">
            {deployResult.agent_ids.length} agent{deployResult.agent_ids.length !== 1 ? 's' : ''} started
            · ${deployResult.total_budget.toLocaleString('es-MX')} MXN allocated
          </div>
          <div className="flex flex-wrap gap-2 mt-1">
            {deployResult.pairs.map(p => (
              <div key={p.symbol} className="text-xs bg-gray-700 rounded px-2 py-1 text-gray-300">
                {p.symbol} · ${p.budget_allocated.toLocaleString('es-MX')}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Loading states */}
      {(status === 'analyzing' || status === 'deploying') && (
        <div className="flex items-center gap-3 py-6 justify-center">
          <svg className="animate-spin w-5 h-5 text-blue-400" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
          </svg>
          <span className="text-sm text-gray-400">
            {status === 'analyzing' ? 'Analyzing market conditions…' : 'Creating agents…'}
          </span>
        </div>
      )}

      {/* Idle / Analyzed */}
      {(status === 'idle' || status === 'analyzed') && (
        <div className="space-y-5">
          {/* Budget config */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Budget input */}
            <div className="md:col-span-2">
              <label className="block text-xs text-gray-500 mb-1.5">Budget</label>
              <div className="flex gap-2">
                {/* Mode toggle */}
                <div className="flex rounded overflow-hidden border border-gray-600 text-xs font-medium">
                  <button
                    onClick={() => setBudgetMode('fixed')}
                    className={`px-3 py-1.5 ${budgetMode === 'fixed' ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'}`}
                  >
                    Fixed $
                  </button>
                  <button
                    onClick={() => setBudgetMode('percent')}
                    className={`px-3 py-1.5 ${budgetMode === 'percent' ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'}`}
                  >
                    % Wallet
                  </button>
                </div>

                {budgetMode === 'fixed' ? (
                  <input
                    type="number"
                    min={50}
                    step={50}
                    value={fixedAmount}
                    onChange={e => setFixedAmount(e.target.value)}
                    className="flex-1 bg-gray-700 border border-gray-600 rounded px-3 py-1.5 text-sm text-white focus:outline-none focus:border-blue-500"
                    placeholder="MXN amount"
                  />
                ) : (
                  <div className="flex-1 flex items-center gap-3">
                    <input
                      type="range"
                      min={5}
                      max={100}
                      step={5}
                      value={percentAmount}
                      onChange={e => setPercentAmount(Number(e.target.value))}
                      className="flex-1 accent-blue-500"
                    />
                    <span className="text-sm text-white font-medium w-8 text-center">{percentAmount}%</span>
                  </div>
                )}
              </div>
              {budgetMode === 'percent' && (
                <div className="text-xs text-gray-500 mt-1">
                  ≈ ${computedBudget.toLocaleString('es-MX')} MXN
                  {walletBalance === 0 && <span className="text-yellow-500 ml-1">(wallet unavailable)</span>}
                </div>
              )}
            </div>

            {/* Max agents */}
            <div>
              <label className="block text-xs text-gray-500 mb-1.5">Max Pairs</label>
              <div className="flex rounded overflow-hidden border border-gray-600 text-xs font-medium">
                {[1, 2, 3].map(n => (
                  <button
                    key={n}
                    onClick={() => setMaxAgents(n)}
                    className={`flex-1 py-1.5 ${maxAgents === n ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'}`}
                  >
                    {n}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Min score */}
          <div className="flex items-center gap-3">
            <label className="text-xs text-gray-500 whitespace-nowrap">Min score</label>
            <input
              type="range"
              min={0}
              max={70}
              step={5}
              value={minScore}
              onChange={e => setMinScore(Number(e.target.value))}
              className="flex-1 accent-blue-500"
            />
            <span className="text-xs text-gray-400 w-6 text-right">{minScore}</span>
          </div>

          {error && (
            <div className="text-xs text-red-400 bg-red-950/40 border border-red-800 rounded px-3 py-2">
              {error}
            </div>
          )}

          {/* Analysis results */}
          {status === 'analyzed' && pairs.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-2">
                <BarChart2 className="w-3.5 h-3.5 text-gray-400" />
                <span className="text-xs text-gray-400 uppercase tracking-wide">Market Analysis</span>
              </div>
              <div className="rounded border border-gray-700 overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-700 bg-gray-750">
                      <th className="text-left text-xs text-gray-500 px-3 py-2 font-medium">Pair</th>
                      <th className="text-left text-xs text-gray-500 px-3 py-2 font-medium w-36">Score</th>
                      <th className="text-left text-xs text-gray-500 px-3 py-2 font-medium">Strategy</th>
                      <th className="text-left text-xs text-gray-500 px-3 py-2 font-medium hidden md:table-cell">Signals</th>
                      <th className="text-right text-xs text-gray-500 px-3 py-2 font-medium">Allocation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pairs.slice(0, maxAgents).filter(p => p.score >= minScore).map((pair, i) => {
                      const totalScore = pairs.slice(0, maxAgents).filter(p => p.score >= minScore).reduce((a, p) => a + p.score, 0);
                      const allocation = totalScore > 0
                        ? Math.max(10, Math.round((computedBudget * pair.score / totalScore) * 100) / 100)
                        : 0;
                      return (
                        <tr key={pair.symbol} className={`border-b border-gray-700/50 ${i === 0 ? 'bg-gray-700/20' : ''}`}>
                          <td className="px-3 py-2.5">
                            <span className="font-mono text-xs font-medium text-white">{pair.symbol.replace('/MXN', '')}</span>
                            <span className="text-gray-600 text-xs">/MXN</span>
                          </td>
                          <td className="px-3 py-2.5">
                            <ScoreBar score={pair.score} />
                          </td>
                          <td className="px-3 py-2.5">
                            <StrategyBadge strategy={pair.strategy} />
                          </td>
                          <td className="px-3 py-2.5 hidden md:table-cell">
                            <span className="text-xs text-gray-500 truncate block max-w-xs">{pair.reason}</span>
                          </td>
                          <td className="px-3 py-2.5 text-right">
                            <span className="text-xs font-mono text-gray-300">${allocation.toLocaleString('es-MX')}</span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {pairs.filter(p => p.score >= minScore).length === 0 && (
                  <div className="px-3 py-4 text-center text-xs text-gray-500">
                    No pairs meet the minimum score. Lower the threshold or try again later.
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-3">
            <button
              onClick={handleAnalyze}
              className="flex items-center gap-1.5 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded font-medium border border-gray-600"
            >
              <BarChart2 className="w-3.5 h-3.5" />
              Analyze Market
            </button>
            {status === 'analyzed' && pairs.filter(p => p.score >= minScore).length > 0 && (
              <button
                onClick={handleDeploy}
                className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded font-medium"
              >
                <ChevronRight className="w-3.5 h-3.5" />
                Deploy {Math.min(maxAgents, pairs.filter(p => p.score >= minScore).length)} Agent{Math.min(maxAgents, pairs.filter(p => p.score >= minScore).length) !== 1 ? 's' : ''}
              </button>
            )}
            {status === 'analyzed' && (
              <button onClick={reset} className="text-xs text-gray-500 hover:text-gray-400 ml-auto">
                Reset
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
