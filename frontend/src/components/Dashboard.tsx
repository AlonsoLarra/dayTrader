import { useState, useEffect, useCallback } from 'react';
import type { Agent, Trade, TradeSummary, WsMessage } from '../types';
import { getAgents, getTrades, getTradeSummary } from '../api/client';
import { AgentCard } from './AgentCard';
import { PnLChart } from './PnLChart';
import { CreateAgentModal } from './CreateAgentModal';
import { WalletPanel } from './WalletPanel';

interface Props {
  lastWsMessage: WsMessage | null;
}

export function Dashboard({ lastWsMessage }: Props) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [summary, setSummary] = useState<TradeSummary | null>(null);
  const [showCreate, setShowCreate] = useState(false);

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
      {/* Stats row */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="text-xs text-gray-400 font-medium uppercase tracking-wide mb-1">Total P&amp;L</div>
          <div
            className={`text-2xl font-bold ${
              (summary?.total_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'
            }`}
          >
            ${(summary?.total_pnl ?? 0).toFixed(2)}
          </div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="text-xs text-gray-400 font-medium uppercase tracking-wide mb-1">Active Agents</div>
          <div className="text-2xl font-bold text-blue-400">
            {runningAgents} / {agents.length}
          </div>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="text-xs text-gray-400 font-medium uppercase tracking-wide mb-1">Total Trades</div>
          <div className="text-2xl font-bold text-white">{summary?.total_trades ?? 0}</div>
        </div>
      </div>

      {/* Two-column: Agents (main) + Wallet (sidebar) */}
      <div className="flex gap-6">
        {/* Agents — main content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-gray-200 uppercase tracking-wide">Agents</h2>
            <button
              onClick={() => setShowCreate(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded font-medium"
            >
              + New Agent
            </button>
          </div>
          {agents.length === 0 ? (
            <div className="bg-gray-800 rounded-lg p-8 border border-gray-700 text-center text-gray-500 text-sm">
              No agents yet. Click <span className="text-blue-400 font-medium">+ New Agent</span> to get started.
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {agents.map(agent => (
                <AgentCard key={agent.agent_id} agent={agent} onUpdate={refresh} />
              ))}
            </div>
          )}
        </div>

        {/* Wallet — right sidebar */}
        <div className="w-72 shrink-0">
          <WalletPanel />
        </div>
      </div>

      {/* P&L chart — full width */}
      <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">Cumulative P&amp;L</h2>
        <PnLChart trades={trades} />
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
