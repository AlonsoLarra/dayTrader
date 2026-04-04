import { useState, useEffect, useCallback } from 'react';
import type { Agent, Trade, TradeSummary, WsMessage } from '../types';
import { getAgents, getTrades, getTradeSummary, createAgent, startAgent, getMarkets } from '../api/client';
import { AgentCard } from './AgentCard';
import { PnLChart } from './PnLChart';
import { CreateAgentModal } from './CreateAgentModal';

interface Props {
  lastWsMessage: WsMessage | null;
}

export function Dashboard({ lastWsMessage }: Props) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [summary, setSummary] = useState<TradeSummary | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  // Quick Start state
  const [qsBudget, setQsBudget] = useState(1000);
  const [qsStrategy, setQsStrategy] = useState<'rsi' | 'ma_crossover'>('rsi');
  const [qsSymbol, setQsSymbol] = useState('BTC/MXN');
  const [qsMarkets, setQsMarkets] = useState<string[]>(['BTC/MXN', 'ETH/MXN', 'SOL/MXN', 'XRP/MXN', 'AVAX/MXN', 'LTC/MXN']);
  const [qsLoading, setQsLoading] = useState(false);
  const [qsError, setQsError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [a, t, s] = await Promise.all([
      getAgents(),
      getTrades({ limit: 200 }),
      getTradeSummary(),
    ]);
    setAgents(a);
    setTrades(t);
    setSummary(s);
  }, []);

  useEffect(() => {
    getMarkets().then(d => setQsMarkets(d.symbols)).catch(() => {});
  }, []);

  const handleQuickStart = useCallback(async () => {
    setQsLoading(true);
    setQsError(null);
    try {
      const params: Record<string, number> =
        qsStrategy === 'rsi' ? { period: 14 } : { fast_period: 9, slow_period: 21 };
      const { agent_id } = await createAgent({ strategy: qsStrategy, params, budget: qsBudget, symbol: qsSymbol });
      await startAgent(agent_id);
      await refresh();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to start agent';
      setQsError(msg);
    } finally {
      setQsLoading(false);
    }
  }, [qsStrategy, qsBudget, qsSymbol, refresh]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (lastWsMessage && ['trade', 'state_update'].includes(lastWsMessage.type)) {
      refresh();
    }
  }, [lastWsMessage, refresh]);

  const runningAgents = agents.filter(a => a.status === 'running').length;

  return (
    <div className="space-y-6">
      {/* Quick Start — shown when no agents are running */}
      {runningAgents === 0 && (
        <div className="bg-gray-800 rounded-lg border border-blue-600 p-5">
          <h2 className="text-white font-bold text-base mb-4">🚀 Start Trading</h2>
          <div className="space-y-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Budget (MXN)</label>
              <input
                type="number"
                value={qsBudget}
                onChange={e => setQsBudget(Number(e.target.value))}
                className="w-48 bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm"
              />
            </div>
            <div className="flex gap-6 items-center flex-wrap">
              <div>
                <label className="block text-xs text-gray-400 mb-1">Strategy</label>
                <div className="flex gap-4">
                  {(['rsi', 'ma_crossover'] as const).map(s => (
                    <label key={s} className="flex items-center gap-1.5 cursor-pointer text-sm text-gray-200">
                      <input
                        type="radio"
                        name="qs-strategy"
                        value={s}
                        checked={qsStrategy === s}
                        onChange={() => setQsStrategy(s)}
                        className="accent-blue-500"
                      />
                      {s === 'rsi' ? 'RSI (recommended)' : 'MA Cross'}
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Pair</label>
                <select
                  value={qsSymbol}
                  onChange={e => setQsSymbol(e.target.value)}
                  className="bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm"
                >
                  {qsMarkets.map(m => <option key={m} value={m}>{m}</option>)}
                </select>
              </div>
            </div>
            <div className="text-xs text-gray-500 space-y-0.5">
              <div>Auto-guardrails: Stop-loss 3% · Max 10 trades/day · Mode: PAPER (safe)</div>
            </div>
            {qsError && <div className="text-xs text-red-400">{qsError}</div>}
            <button
              onClick={handleQuickStart}
              disabled={qsLoading}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-600 text-white rounded font-medium text-sm"
            >
              {qsLoading ? 'Starting…' : '▶ Start Agent'}
            </button>
          </div>
        </div>
      )}
      {/* Summary stats */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="text-xs text-gray-400 mb-1">Total P&amp;L</div>
          <div
            className={`text-2xl font-bold ${
              (summary?.total_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'
            }`}
          >
            ${(summary?.total_pnl ?? 0).toFixed(2)}
          </div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="text-xs text-gray-400 mb-1">Active Agents</div>
          <div className="text-2xl font-bold text-blue-400">
            {runningAgents} / {agents.length}
          </div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="text-xs text-gray-400 mb-1">Total Trades</div>
          <div className="text-2xl font-bold text-white">{summary?.total_trades ?? 0}</div>
        </div>
      </div>

      {/* P&L Chart */}
      <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <h2 className="text-sm font-medium text-gray-300 mb-3">Cumulative P&amp;L</h2>
        <PnLChart trades={trades} />
      </div>

      {/* Agents */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-medium text-gray-300">Agents</h2>
          <button
            onClick={() => setShowCreate(true)}
            className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded"
          >
            + New Agent
          </button>
        </div>
        {agents.length === 0 ? (
          <div className="bg-gray-800 rounded-lg p-8 border border-gray-700 text-center text-gray-500">
            No agents yet. Create one to get started.
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {agents.map(agent => (
              <AgentCard key={agent.agent_id} agent={agent} onUpdate={refresh} />
            ))}
          </div>
        )}
      </div>

      {showCreate && (
        <CreateAgentModal
          onClose={() => setShowCreate(false)}
          onCreate={async () => {
            setShowCreate(false);
            await refresh();
          }}
        />
      )}
    </div>
  );
}
