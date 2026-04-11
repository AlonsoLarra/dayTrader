import { useState } from 'react';
import type { Agent, Trade, TradeSummary } from '../types';
import { AgentCard } from './AgentCard';
import { PnLChart } from './PnLChart';
import { CreateAgentModal } from './CreateAgentModal';
import { PositionsPanel } from './PositionsPanel';

interface Props {
  agents: Agent[];
  trades: Trade[];
  summary: TradeSummary | null;
  onRefresh: () => Promise<void>;
}

function getQuoteCurrency(symbol: string, explicit?: string) {
  return (explicit || (symbol.includes('/') ? symbol.split('/')[1] : 'MXN') || 'MXN').toUpperCase();
}

function formatSummaryAmount(value: number, quoteCurrency?: string) {
  const normalizedQuote = quoteCurrency?.toUpperCase();
  const digits = normalizedQuote === 'BTC' ? 6 : 2;
  const formatted = Number(value || 0).toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });

  if (!normalizedQuote) return formatted;
  return normalizedQuote === 'MXN' ? `$${formatted}` : `${formatted} ${normalizedQuote}`;
}

export function Dashboard({ agents, trades, summary, onRefresh }: Props) {
  const [showCreate, setShowCreate] = useState(false);

  const runningAgents = agents.filter(a => a.status === 'running').length;
  const activeQuotes = Array.from(new Set(
    agents
      .filter(a => a.status !== 'killed')
      .map(a => getQuoteCurrency(a.symbol, a.quote_currency))
  ));
  const summaryQuote = activeQuotes.length <= 1 ? (activeQuotes[0] ?? 'MXN') : undefined;

  const pnl = summary?.total_pnl ?? 0;
  const pnlPct = summary?.total_allocated
    ? (pnl / summary.total_allocated) * 100
    : 0;
  const pnlPositive = pnl >= 0;

  return (
    <div className="space-y-6">
      {/* Portfolio overview */}
      <div className="bg-gray-800 rounded-lg border border-gray-700 p-5">
        <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-4">Portfolio Overview</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-6">
          <div>
            <div className="text-xs text-gray-500 mb-1">Realized P&amp;L</div>
            <div className={`text-2xl font-bold tabular-nums ${pnlPositive ? 'text-green-400' : 'text-red-400'}`}>
              {pnlPositive ? '+' : '-'}{formatSummaryAmount(Math.abs(pnl), summaryQuote)}
            </div>
            <div className={`text-xs mt-0.5 ${pnlPositive ? 'text-green-500' : 'text-red-500'}`}>
              {pnlPositive ? '+' : ''}{pnlPct.toFixed(2)}% on capital
            </div>
            {(summary?.total_fees ?? 0) > 0 && (
              <div className="text-xs text-gray-600 mt-0.5">
                −{formatSummaryAmount(summary?.total_fees ?? 0, summaryQuote)} fees paid
              </div>
            )}
          </div>
          <div>
            <div className="text-xs text-gray-500 mb-1">Capital Deployed</div>
            <div className="text-2xl font-bold text-white tabular-nums">
              {formatSummaryAmount(summary?.total_allocated ?? 0, summaryQuote)}
            </div>
            <div className="text-xs text-gray-500 mt-0.5">
              {summaryQuote ? `${summaryQuote} paper budget` : 'Across paper wallets'}
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-500 mb-1">Win Rate</div>
            <div className="text-2xl font-bold text-white tabular-nums">
              {(summary?.win_rate ?? 0).toFixed(0)}%
            </div>
            <div className="text-xs text-gray-500 mt-0.5">
              {summary?.winning_trades ?? 0} / {summary?.total_trades ?? 0} trades won
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-500 mb-1">Active Bots</div>
            <div className="text-2xl font-bold text-blue-400 tabular-nums">
              {summary?.running_agents ?? runningAgents} / {summary?.total_agents ?? agents.filter(a => a.status !== 'killed').length}
            </div>
            <div className="text-xs text-gray-500 mt-0.5">bots active</div>
          </div>
        </div>
      </div>


      {/* Open positions */}
      <PositionsPanel onSold={onRefresh} refreshTrigger={agents.filter(a => a.status === 'running').length} />
      {/* Bots */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-gray-200 uppercase tracking-wide">Bots</h2>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-1.5 px-4 py-2.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded font-medium min-h-[44px]"
          >
            + New Bot
          </button>
        </div>
        {agents.length === 0 ? (
          <div className="bg-gray-800 rounded-lg p-8 border border-gray-700 text-center text-gray-500 text-sm">
            No bots yet. Use <span className="text-blue-400 font-medium">Auto-Trade</span> in the header or click <span className="text-blue-400 font-medium">+ New Bot</span>.
          </div>
        ) : (
          <div className="grid gap-3 md:gap-4 md:grid-cols-2 xl:grid-cols-3">
            {agents.map(agent => (
              <AgentCard key={agent.agent_id} agent={agent} onUpdate={onRefresh} />
            ))}
          </div>
        )}
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
            await onRefresh();
          }}
        />
      )}
    </div>
  );
}
