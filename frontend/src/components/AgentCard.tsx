import { useState, useEffect } from 'react';
import { Play, Square, Skull, ChevronDown, ChevronUp, Trash2, Radar } from 'lucide-react';
import clsx from 'clsx';
import type { Agent, AgentLog } from '../types';
import { BudgetGauge } from './BudgetGauge';
import { startAgent, stopAgent, killAgent, deleteAgent, getAgentLogs } from '../api/client';

interface Props {
  agent: Agent;
  onUpdate: () => void;
}

function formatRelativeTime(value?: string | null, fallback = 'Pending') {
  if (!value) return fallback;
  const ts = value.endsWith('Z') ? value : `${value}Z`;
  const diffSec = Math.max(0, Math.round((Date.now() - new Date(ts).getTime()) / 1000));
  if (diffSec < 5) return 'just now';
  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffSec < 3600) return `${Math.round(diffSec / 60)}m ago`;
  return `${Math.round(diffSec / 3600)}h ago`;
}

function getQuoteCurrency(symbol: string, explicit?: string) {
  return (explicit || (symbol.includes('/') ? symbol.split('/')[1] : 'MXN') || 'MXN').toUpperCase();
}

function formatQuoteAmount(value: number, quoteCurrency = 'MXN') {
  const normalizedQuote = (quoteCurrency || 'MXN').toUpperCase();
  const digits = normalizedQuote === 'BTC' ? 6 : 2;
  const formatted = Number(value || 0).toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  return normalizedQuote === 'MXN' ? `$${formatted} MXN` : `${formatted} ${normalizedQuote}`;
}

function formatSignedQuoteAmount(value: number, quoteCurrency = 'MXN') {
  return `${value >= 0 ? '+' : '-'}${formatQuoteAmount(Math.abs(value), quoteCurrency)}`;
}

export function AgentCard({ agent, onUpdate }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [logs, setLogs] = useState<AgentLog[]>([]);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const statusLabel: Record<string, string> = {
    running: 'Active',
    stopped: 'Paused',
    killed: 'Closed',
  };

  const handleAction = async (fn: () => Promise<unknown>, label: string) => {
    setError(null);
    setLoading(true);
    try {
      await fn();
      onUpdate();
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (e instanceof Error ? e.message : String(e));
      setError(`${label} failed: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  const handleStart = () => handleAction(() => startAgent(agent.agent_id), 'Start');
  const handleStop = () => handleAction(() => stopAgent(agent.agent_id), 'Stop');
  const handleKill = () => handleAction(() => killAgent(agent.agent_id), 'Kill');
  const handleDelete = () => handleAction(() => deleteAgent(agent.agent_id), 'Delete');

  const toggleExpand = async () => {
    const opening = !expanded;
    if (opening && logs.length === 0) {
      setLoadingLogs(true);
      try {
        const data = await getAgentLogs(agent.agent_id);
        setLogs(data);
      } catch {
        // ignore log fetch errors
      } finally {
        setLoadingLogs(false);
      }
    }
    setExpanded(opening);
  };

  // Auto-refresh logs every 15s when expanded and running
  useEffect(() => {
    if (!expanded || agent.status !== 'running') return;
    const id = setInterval(async () => {
      try {
        const data = await getAgentLogs(agent.agent_id);
        setLogs(data);
      } catch { /* ignore */ }
    }, 15000);
    return () => clearInterval(id);
  }, [expanded, agent.status, agent.agent_id]);

  const realizedPnlTotal = agent.realized_pnl_total ?? agent.realized_pnl_today ?? 0;
  const remainingBudget = Math.max(0, agent.budget_allocated + realizedPnlTotal - agent.budget_used);
  const quoteCurrency = getQuoteCurrency(agent.symbol, agent.quote_currency);
  const rotationEnabled = agent.rotation_enabled ?? false;
  const reviewInterval = agent.rotation_interval_minutes ?? 1;
  const strategyLabel = {
    trend_rsi: 'Trend RSI',
    adaptive: 'Adaptive',
    rsi: 'RSI',
    ma_crossover: 'MA Crossover',
  }[agent.strategy] ?? agent.strategy;

  return (
    <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
      {/* Row 1: identity badges */}
      <div className="flex items-center gap-2 mb-2 flex-wrap">
        <span className={clsx('w-2 h-2 rounded-full shrink-0', {
          'bg-green-500': agent.status === 'running',
          'bg-yellow-500': agent.status === 'stopped',
          'bg-red-500': agent.status === 'killed',
        })} />
        <span className="font-mono text-sm text-gray-200 font-medium">{agent.agent_id}</span>
        <span className="text-xs bg-gray-700 px-2 py-0.5 rounded text-gray-400">
          {agent.strategy}
        </span>
        <span className="text-xs bg-blue-900/60 text-blue-300 px-2 py-0.5 rounded font-mono">
          {agent.symbol}
        </span>
        <span className={clsx('text-xs px-2 py-0.5 rounded font-medium', {
          'bg-green-900/60 text-green-300': agent.status === 'running',
          'bg-amber-900/60 text-amber-300': agent.status === 'stopped',
          'bg-red-900/60 text-red-400': agent.status === 'killed',
        })}>
          {statusLabel[agent.status] ?? agent.status}
        </span>
        <span className={clsx('text-xs px-2 py-0.5 rounded font-medium', {
          'bg-indigo-900/60 text-indigo-300': rotationEnabled,
          'bg-gray-700 text-gray-400': !rotationEnabled,
        })}>
          {rotationEnabled ? `${strategyLabel} review · ${reviewInterval}m` : 'Pair locked'}
        </span>
      </div>

      {/* Row 2: action buttons right-aligned */}
      <div className="flex items-center justify-end gap-1 mb-3">
        {agent.status !== 'killed' && agent.status !== 'running' && (
          <button
            onClick={handleStart}
            disabled={loading}
            className="p-1.5 rounded bg-green-700 hover:bg-green-600 text-white disabled:opacity-50"
            title="Activate bot"
          >
            <Play size={13} />
          </button>
        )}
        {agent.status === 'running' && (
          <button
            onClick={handleStop}
            disabled={loading}
            className="p-1.5 rounded bg-amber-700 hover:bg-amber-600 text-white disabled:opacity-50"
            title="Pause bot"
          >
            <Square size={13} />
          </button>
        )}
        {agent.status !== 'killed' && (
          <button
            onClick={handleKill}
            disabled={loading}
            className="p-1.5 rounded bg-red-800 hover:bg-red-700 text-white disabled:opacity-50"
            title="Close bot"
          >
            <Skull size={13} />
          </button>
        )}
        {(agent.status === 'killed' || agent.status === 'stopped') && (
          <button
            onClick={handleDelete}
            disabled={loading}
            className="p-1.5 rounded bg-gray-700 hover:bg-red-800 text-gray-400 hover:text-white disabled:opacity-50"
            title="Remove bot"
          >
            <Trash2 size={13} />
          </button>
        )}
        <button
          onClick={toggleExpand}
          className="p-1.5 rounded bg-gray-700 hover:bg-gray-600 text-gray-400"
        >
          {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        </button>
      </div>

      {error && (
        <div className="mb-2 text-xs text-red-400 bg-red-900/30 border border-red-800 rounded px-2 py-1">
          {error}
        </div>
      )}

      <div className="grid grid-cols-4 gap-2 text-sm mb-2">
        <div>
          <div className="text-gray-500 text-xs">Budget</div>
          <div className="text-white font-mono text-sm">{formatQuoteAmount(agent.budget_allocated, quoteCurrency)}</div>
        </div>
        <div>
          <div className="text-gray-500 text-xs">Remaining</div>
          <div className={clsx('font-mono text-sm', remainingBudget < agent.budget_allocated * 0.5 ? 'text-amber-400' : 'text-white')}>
            {formatQuoteAmount(remainingBudget, quoteCurrency)}
          </div>
        </div>
        <div>
          <div className="text-gray-500 text-xs">Trades</div>
          <div className="text-white font-mono text-sm">{agent.trades_today}</div>
        </div>
        <div>
          <div className="text-gray-500 text-xs">P&amp;L Today</div>
          <div className={clsx('font-mono text-sm', {
            'text-green-400': agent.realized_pnl_today > 0,
            'text-red-400': agent.realized_pnl_today < 0,
            'text-gray-400': agent.realized_pnl_today === 0,
          })}>
            {formatSignedQuoteAmount(agent.realized_pnl_today, quoteCurrency)}
          </div>
        </div>
      </div>

      {/* Exit criteria warning */}
      {agent.losses_today >= 2 && (
        <div className={clsx('text-xs px-2 py-1 rounded mb-2', {
          'bg-red-900/40 text-red-300 border border-red-800': agent.losses_today >= 3,
          'bg-amber-900/30 text-amber-400 border border-amber-800': agent.losses_today === 2,
        })}>
          {agent.losses_today >= 3
            ? `⛔ Daily loss limit reached — ${agent.losses_today} losses today, no new positions`
            : `⚠ ${agent.losses_today} losses today — 1 more will pause new positions`
          }
        </div>
      )}

      {agent.status === 'running' && (
        <div className="flex items-center justify-between text-xs mb-2 bg-gray-900 rounded px-2 py-1.5">
          <div className="flex items-center gap-2">
            <span className="text-gray-400">Last signal:</span>
            {agent.last_signal ? (
              <span className={clsx('font-bold uppercase', {
                'text-green-400': agent.last_signal === 'buy',
                'text-red-400': agent.last_signal === 'sell',
                'text-gray-400': agent.last_signal === 'hold',
              })}>
                {agent.last_signal}
              </span>
            ) : (
              <span className="text-gray-500 animate-pulse">analyzing…</span>
            )}
          </div>
          <div className="text-gray-500">{formatRelativeTime(agent.last_tick_at, 'first tick pending…')}</div>
        </div>
      )}

      <div className="mb-2 rounded bg-gray-900 px-2 py-2 text-xs">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-gray-300">
            <Radar size={12} className="text-indigo-300" />
            <span>{rotationEnabled ? 'Market review active' : 'Market review off'}</span>
          </div>
          <span className={clsx('font-medium', rotationEnabled ? 'text-indigo-300' : 'text-gray-500')}>
            {rotationEnabled ? `Every ${reviewInterval} min` : 'Current pair only'}
          </span>
        </div>
        <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] text-gray-400">
          <div>
            <div className="uppercase tracking-wide text-gray-500">Last review</div>
            <div className="text-gray-200">{formatRelativeTime(agent.last_market_review_at, 'Pending')}</div>
          </div>
          <div>
            <div className="uppercase tracking-wide text-gray-500">Last rotation</div>
            <div className="text-gray-200">{formatRelativeTime(agent.last_rotation_at, 'No switch yet')}</div>
          </div>
        </div>
      </div>

      <BudgetGauge allocated={agent.budget_allocated} used={agent.budget_used} quoteCurrency={quoteCurrency} />

      {expanded && (
        <div className="mt-4 border-t border-gray-700 pt-3">
          <div className="text-xs text-gray-400 mb-2">Recent Logs</div>
          {loadingLogs ? (
            <div className="text-gray-500 text-xs">Loading...</div>
          ) : logs.length === 0 ? (
            <div className="text-gray-500 text-xs">No logs yet. Activate the bot to see activity.</div>
          ) : (
            <div className="space-y-1 max-h-40 overflow-y-auto">
              {logs.map(log => (
                <div key={log.id} className="text-xs font-mono">
                  <span
                    className={clsx('mr-2', {
                      'text-blue-400': log.level === 'info',
                      'text-yellow-400': log.level === 'warning',
                      'text-red-400': log.level === 'error',
                      'text-green-400': log.level === 'trade',
                    })}
                  >
                    [{log.level.toUpperCase()}]
                  </span>
                  <span className="text-gray-300">{log.message}</span>
                  {log.reasoning && (
                    <span className="text-gray-500 ml-1">— {log.reasoning}</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
