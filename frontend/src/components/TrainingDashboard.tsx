import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  getTrainingRuns,
  getTrainingRun,
  startTrainingRun,
  stopTrainingRun,
  promoteTrainingRun,
} from '../api/client';
import type { GoalCriteria, TrainingRunDetail, TrainingRunSummary, TrainingStartRequest, WsMessage } from '../types';

interface Props {
  lastMessage: WsMessage | null;
  onPromoted?: () => Promise<void>;
}

const DEFAULT_FORM: TrainingStartRequest = {
  symbol: 'BTC/MXN',
  timeframe: '1h',
  start_date: '2024-01-01',
  end_date: '2024-06-01',
  initial_capital: 10000,
  max_trials: 24,
  strategy_candidates: ['rsi', 'ma_crossover', 'trend_rsi', 'adaptive'],
  goal: {
    target_return_pct: 0.1,
    min_win_rate: 45,
    max_drawdown_pct: 18,
    min_trades: 5,
  },
};

function formatPct(value: unknown) {
  const num = Number(value ?? 0);
  if (Number.isNaN(num)) return '0.00%';
  return `${num.toFixed(2)}%`;
}

function GoalCriteriaBreakdown({
  criteria,
  goal,
}: {
  criteria: GoalCriteria | undefined;
  goal: TrainingRunDetail['goal'];
}) {
  if (!criteria) return null;

  const items: { label: string; met: boolean; detail: string }[] = [
    {
      label: 'Return',
      met: criteria.return_met,
      detail: `≥ ${goal.target_return_pct}%`,
    },
    {
      label: 'Win Rate',
      met: criteria.win_rate_met,
      detail: `≥ ${goal.min_win_rate}%`,
    },
    {
      label: 'Drawdown',
      met: criteria.drawdown_met,
      detail: `≤ ${goal.max_drawdown_pct}%`,
    },
    {
      label: 'Trades',
      met: criteria.trades_met,
      detail: `≥ ${goal.min_trades}`,
    },
  ];

  return (
    <div className="flex flex-wrap gap-2 mt-1">
      {items.map(({ label, met, detail }) => (
        <span
          key={label}
          className={`text-[10px] px-2 py-0.5 rounded border ${
            met
              ? 'border-green-700 text-green-400 bg-green-950/40'
              : 'border-red-800 text-red-400 bg-red-950/40'
          }`}
        >
          {met ? '✓' : '✗'} {label} {detail}
        </span>
      ))}
    </div>
  );
}

export function TrainingDashboard({ lastMessage, onPromoted }: Props) {
  const [runs, setRuns] = useState<TrainingRunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [detail, setDetail] = useState<TrainingRunDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState<TrainingStartRequest>(DEFAULT_FORM);
  const [promoteBudget, setPromoteBudget] = useState(100);
  const [promoteAutoStart, setPromoteAutoStart] = useState(true);

  const refreshRuns = useCallback(async () => {
    const data = await getTrainingRuns(30);
    setRuns(data);
    return data;
  }, []);

  const refreshDetail = useCallback(async (runId: string | null) => {
    if (!runId) {
      setDetail(null);
      return;
    }
    const data = await getTrainingRun(runId);
    setDetail(data);
  }, []);

  const refreshAll = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await refreshRuns();
      const targetId = selectedRunId ?? (data.length > 0 ? data[0].run_id : null);
      if (!selectedRunId && targetId) setSelectedRunId(targetId);
      await refreshDetail(targetId);
    } catch (exc) {
      setError((exc as Error)?.message || 'Failed to load training data');
    } finally {
      setLoading(false);
    }
  }, [refreshRuns, refreshDetail, selectedRunId]);

  useEffect(() => {
    refreshAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Refresh detail whenever the selected run changes.
  useEffect(() => {
    refreshDetail(selectedRunId);
  }, [selectedRunId, refreshDetail]);

  // On WS update: patch run list in-place (no extra fetch) and refresh detail
  // only for the selected run. This prevents the count divergence race.
  useEffect(() => {
    if (!lastMessage) return;
    const { type, payload } = lastMessage as { type: string; payload: Record<string, unknown> };
    if (!['training_update', 'training_run_completed', 'training_run_failed'].includes(type)) return;
    if (!payload) return;

    const wsRunId = payload.run_id as string | undefined;

    // Patch the matching card in the run list directly from the WS payload.
    setRuns(prev =>
      prev.map(r => {
        if (r.run_id !== wsRunId) return r;
        return {
          ...r,
          status: (payload.status as string) ?? r.status,
          completed_trials:
            payload.completed_trials != null
              ? (payload.completed_trials as number)
              : r.completed_trials,
          max_trials: payload.max_trials != null ? (payload.max_trials as number) : r.max_trials,
          best_score: payload.best_score != null ? (payload.best_score as number) : r.best_score,
          best_strategy:
            payload.best_strategy != null
              ? (payload.best_strategy as string)
              : r.best_strategy,
          best_goal_met:
            payload.best_goal_met != null
              ? Boolean(payload.best_goal_met)
              : r.best_goal_met,
        };
      })
    );

    // Full detail refresh only for the selected run.
    if (wsRunId === selectedRunId) {
      refreshDetail(wsRunId);
    }
  }, [lastMessage, selectedRunId, refreshDetail]);

  const progressPct = useMemo(() => {
    if (!detail || detail.max_trials <= 0) return 0;
    return Math.min(100, (detail.completed_trials / detail.max_trials) * 100);
  }, [detail]);

  const runBestReturn = Number(detail?.best?.metrics?.total_return_pct ?? 0);
  const runBestWinRate = Number(detail?.best?.metrics?.win_rate ?? 0);
  const runBestDrawdown = Number(detail?.best?.metrics?.max_drawdown_pct ?? 0);
  const runGoalMet = Boolean(detail?.best?.goal_met);
  const bestCriteria = detail?.best?.metrics?.goal_criteria as GoalCriteria | undefined;

  const onStartRun = async () => {
    try {
      setSubmitting(true);
      setError(null);
      const started = await startTrainingRun(form);
      setSelectedRunId(started.run_id);
      await refreshAll();
    } catch (exc) {
      setError((exc as Error)?.message || 'Failed to start training run');
    } finally {
      setSubmitting(false);
    }
  };

  const onStopRun = async () => {
    if (!detail) return;
    try {
      await stopTrainingRun(detail.run_id);
      await refreshAll();
    } catch (exc) {
      setError((exc as Error)?.message || 'Failed to stop run');
    }
  };

  const onPromoteRun = async () => {
    if (!detail) return;
    try {
      await promoteTrainingRun(detail.run_id, {
        budget: promoteBudget,
        auto_start: promoteAutoStart,
      });
      if (onPromoted) {
        await onPromoted();
      }
      await refreshAll();
    } catch (exc) {
      setError((exc as Error)?.message || 'Failed to promote trained strategy');
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-gray-800 rounded-lg border border-gray-700 p-5 space-y-4">
        <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Start Auto-Explore Training</div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <label className="text-xs text-gray-300 space-y-1">
            <span>Symbol</span>
            <input
              value={form.symbol}
              onChange={e => setForm(prev => ({ ...prev, symbol: e.target.value }))}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
              placeholder="BTC/MXN"
            />
          </label>
          <label className="text-xs text-gray-300 space-y-1">
            <span>Timeframe</span>
            <select
              value={form.timeframe}
              onChange={e => setForm(prev => ({ ...prev, timeframe: e.target.value }))}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
            >
              <option value="15m">15m</option>
              <option value="1h">1h</option>
              <option value="4h">4h</option>
            </select>
          </label>
          <label className="text-xs text-gray-300 space-y-1">
            <span>Max Trials</span>
            <input
              type="number"
              min={1}
              max={500}
              value={form.max_trials}
              onChange={e => setForm(prev => ({ ...prev, max_trials: Number(e.target.value || 1) }))}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
            />
          </label>
          <label className="text-xs text-gray-300 space-y-1">
            <span>Start Date</span>
            <input
              value={form.start_date}
              onChange={e => setForm(prev => ({ ...prev, start_date: e.target.value }))}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
              placeholder="YYYY-MM-DD"
            />
          </label>
          <label className="text-xs text-gray-300 space-y-1">
            <span>End Date</span>
            <input
              value={form.end_date}
              onChange={e => setForm(prev => ({ ...prev, end_date: e.target.value }))}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
              placeholder="YYYY-MM-DD"
            />
          </label>
          <label className="text-xs text-gray-300 space-y-1">
            <span>Initial Capital</span>
            <input
              type="number"
              min={1}
              value={form.initial_capital}
              onChange={e => setForm(prev => ({ ...prev, initial_capital: Number(e.target.value || 1) }))}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
            />
          </label>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <label className="text-xs text-gray-300 space-y-1">
            <span>Target Return %</span>
            <input
              type="number"
              step="0.1"
              value={form.goal.target_return_pct}
              onChange={e => setForm(prev => ({ ...prev, goal: { ...prev.goal, target_return_pct: Number(e.target.value || 0) } }))}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
            />
          </label>
          <label className="text-xs text-gray-300 space-y-1">
            <span>Min Win Rate %</span>
            <input
              type="number"
              step="1"
              value={form.goal.min_win_rate}
              onChange={e => setForm(prev => ({ ...prev, goal: { ...prev.goal, min_win_rate: Number(e.target.value || 0) } }))}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
            />
          </label>
          <label className="text-xs text-gray-300 space-y-1">
            <span>Max Drawdown %</span>
            <input
              type="number"
              step="0.5"
              value={form.goal.max_drawdown_pct}
              onChange={e => setForm(prev => ({ ...prev, goal: { ...prev.goal, max_drawdown_pct: Number(e.target.value || 0) } }))}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
            />
          </label>
          <label className="text-xs text-gray-300 space-y-1">
            <span>Min Trades</span>
            <input
              type="number"
              min={1}
              step="1"
              value={form.goal.min_trades}
              onChange={e => setForm(prev => ({ ...prev, goal: { ...prev.goal, min_trades: Number(e.target.value || 1) } }))}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
            />
          </label>
        </div>

        <button
          onClick={onStartRun}
          disabled={submitting}
          className="px-4 py-2 rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-60 text-sm font-medium"
        >
          {submitting ? 'Starting...' : 'Start Training Run'}
        </button>
      </div>

      {error && (
        <div className="bg-red-950 border border-red-700 text-red-200 text-sm rounded p-3">{error}</div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-4 xl:col-span-1">
          <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">Recent Training Runs</div>
          <div className="space-y-2 max-h-[520px] overflow-y-auto pr-1">
            {runs.length === 0 && (
              <div className="text-sm text-gray-500">No runs yet.</div>
            )}
            {runs.map(run => (
              <button
                key={run.run_id}
                onClick={() => setSelectedRunId(run.run_id)}
                className={`w-full text-left p-3 rounded border transition-colors ${
                  selectedRunId === run.run_id
                    ? 'border-blue-500 bg-gray-900'
                    : 'border-gray-700 hover:border-gray-500 bg-gray-900/40'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium text-white">{run.symbol}</div>
                  <div className="text-[10px] uppercase tracking-wide text-gray-400">{run.status}</div>
                </div>
                <div className="text-xs text-gray-500 mt-1">{run.run_id} • {run.timeframe}</div>
                <div className="text-xs text-gray-400 mt-1">{run.completed_trials}/{run.max_trials} trials</div>
                <div className="text-xs text-gray-400">Best: {run.best_strategy ?? '—'} / {run.best_score?.toFixed(2) ?? '—'}</div>
                <div className={`text-[10px] uppercase tracking-wide mt-1 ${run.best_goal_met ? 'text-green-400' : 'text-amber-400'}`}>
                  {run.best_goal_met ? 'Goal met' : 'Goal not met'}
                </div>
              </button>
            ))}
          </div>
        </div>

        <div className="bg-gray-800 rounded-lg border border-gray-700 p-4 xl:col-span-2 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Run Detail</div>
              <div className="text-sm text-gray-300 mt-1">{detail ? `${detail.symbol} • ${detail.timeframe}` : 'Select a run'}</div>
            </div>
            {detail && (
              <div className="flex items-center gap-2">
                <button
                  onClick={onStopRun}
                  disabled={detail.status !== 'running'}
                  className="px-3 py-1.5 rounded border border-gray-600 text-xs hover:border-gray-400 disabled:opacity-50"
                >
                  Stop
                </button>
              </div>
            )}
          </div>

          {loading && !detail && <div className="text-sm text-gray-500">Loading training runs...</div>}

          {detail && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="bg-gray-900 border border-gray-700 rounded p-3">
                  <div className="text-[10px] uppercase text-gray-500">Progress</div>
                  <div className="text-lg font-semibold text-white">{detail.completed_trials}/{detail.max_trials}</div>
                </div>
                <div className="bg-gray-900 border border-gray-700 rounded p-3">
                  <div className="text-[10px] uppercase text-gray-500">Best Score</div>
                  <div className="text-lg font-semibold text-blue-300">{detail.best.score?.toFixed(2) ?? '—'}</div>
                </div>
                <div className="bg-gray-900 border border-gray-700 rounded p-3">
                  <div className="text-[10px] uppercase text-gray-500">Best Return</div>
                  <div className={`text-lg font-semibold ${runBestReturn >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {formatPct(runBestReturn)}
                  </div>
                  <div className="text-xs text-gray-500 mt-0.5">Holdout period</div>
                </div>
                <div className="bg-gray-900 border border-gray-700 rounded p-3">
                  <div className="text-[10px] uppercase text-gray-500">Goal Status</div>
                  <div className={`text-lg font-semibold ${runGoalMet ? 'text-green-400' : 'text-amber-400'}`}>
                    {runGoalMet ? 'Met' : 'Not Met'}
                  </div>
                  <div className="text-xs text-gray-500 mt-0.5">Win {formatPct(runBestWinRate)}</div>
                </div>
              </div>

              <div>
                <div className="h-2 bg-gray-700 rounded overflow-hidden">
                  <div className="h-full bg-blue-500 transition-all" style={{ width: `${progressPct}%` }} />
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  Scored on holdout (last 20% of date range). Current best drawdown: {formatPct(runBestDrawdown)}
                </div>
              </div>

              {/* Per-criterion goal breakdown */}
              {!runGoalMet && bestCriteria && (
                <div className="bg-gray-900 border border-amber-800/40 rounded p-3 space-y-1">
                  <div className="text-xs text-amber-400 font-medium">Failing criteria on best trial:</div>
                  <GoalCriteriaBreakdown criteria={bestCriteria} goal={detail.goal} />
                </div>
              )}

              <div className="bg-gray-900 border border-gray-700 rounded p-3 space-y-2">
                <div className="text-xs text-gray-400">Promote best configuration to live paper agent</div>
                <div className="flex flex-wrap items-center gap-2">
                  <input
                    type="number"
                    min={1}
                    value={promoteBudget}
                    onChange={e => setPromoteBudget(Number(e.target.value || 1))}
                    className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm w-28"
                  />
                  <label className="text-xs text-gray-300 flex items-center gap-1">
                    <input
                      type="checkbox"
                      checked={promoteAutoStart}
                      onChange={e => setPromoteAutoStart(e.target.checked)}
                    />
                    Auto-start agent
                  </label>
                  <button
                    onClick={onPromoteRun}
                    disabled={!detail.best.strategy || !runGoalMet}
                    className="px-3 py-1.5 rounded bg-green-600 hover:bg-green-500 disabled:opacity-50 text-xs font-medium"
                  >
                    Promote Best
                  </button>
                </div>
                {!runGoalMet && (
                  <div className="text-xs text-amber-300">
                    Promotion is blocked until the best trial meets all configured goal criteria.
                  </div>
                )}
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-gray-400 border-b border-gray-700">
                      <th className="py-2 pr-3">#</th>
                      <th className="py-2 pr-3">Strategy</th>
                      <th className="py-2 pr-3">Score</th>
                      <th className="py-2 pr-3">Return</th>
                      <th className="py-2 pr-3">Win</th>
                      <th className="py-2 pr-3">DD</th>
                      <th className="py-2 pr-3">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.trials.slice(0, 30).map(t => {
                      const ret = Number(t.metrics?.total_return_pct ?? 0);
                      const win = Number(t.metrics?.win_rate ?? 0);
                      const dd = Number(t.metrics?.max_drawdown_pct ?? 0);
                      const trialGoalMet = Boolean((t.metrics as Record<string, unknown>)?.goal_met);
                      return (
                        <tr key={t.id} className="border-b border-gray-800 text-gray-200">
                          <td className="py-2 pr-3">{t.trial_index}</td>
                          <td className="py-2 pr-3">{t.strategy}</td>
                          <td className="py-2 pr-3">{t.objective_score?.toFixed(2) ?? '—'}</td>
                          <td className={`py-2 pr-3 ${ret >= 0 ? 'text-green-400' : 'text-red-400'}`}>{formatPct(ret)}</td>
                          <td className="py-2 pr-3">{formatPct(win)}</td>
                          <td className="py-2 pr-3">{formatPct(dd)}</td>
                          <td className="py-2 pr-3">
                            <span className="uppercase text-[11px] tracking-wide text-gray-400">{t.status}</span>
                            {t.status === 'completed' && (
                              <span className={`ml-1.5 text-[10px] ${trialGoalMet ? 'text-green-400' : 'text-gray-600'}`}>
                                {trialGoalMet ? '✓goal' : ''}
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
