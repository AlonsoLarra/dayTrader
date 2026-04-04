import { useState, useEffect, useCallback } from 'react';
import { Bot, Activity, FileText } from 'lucide-react';
import clsx from 'clsx';
import { Dashboard } from './components/Dashboard';
import { BacktestPanel } from './components/BacktestPanel';
import { TradeLog } from './components/TradeLog';
import { KillSwitch } from './components/KillSwitch';
import { PriceBoard } from './components/PriceBoard';
import { useWebSocket } from './hooks/useWebSocket';
import { getTrades, getAgents } from './api/client';
import type { Trade, Agent } from './types';

type Tab = 'dashboard' | 'backtest' | 'logs';

export default function App() {
  const [tab, setTab] = useState<Tab>('dashboard');
  const [trades, setTrades] = useState<Trade[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const { lastMessage } = useWebSocket();

  const refreshAll = useCallback(async () => {
    const [t, a] = await Promise.all([getTrades({ limit: 500 }), getAgents()]);
    setTrades(t);
    setAgents(a);
  }, []);

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  const hasRunningAgents = agents.some(a => a.status === 'running');

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'dashboard', label: 'Dashboard', icon: <Activity size={16} /> },
    { id: 'backtest', label: 'Backtest', icon: <Bot size={16} /> },
    { id: 'logs', label: 'Trades', icon: <FileText size={16} /> },
  ];

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      {/* Top nav */}
      <nav className="bg-gray-800 border-b border-gray-700 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold">🤖 dayTrader</span>
          <span className="text-xs px-2 py-1 rounded font-bold bg-blue-900 text-blue-300">
            PAPER
          </span>
        </div>
        <KillSwitch hasRunningAgents={hasRunningAgents} onKilled={refreshAll} />
      </nav>

      {/* Tabs */}
      <div className="bg-gray-800 border-b border-gray-700 px-6">
        <div className="flex gap-0">
          {tabs.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={clsx(
                'flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors',
                {
                  'border-blue-500 text-blue-400': tab === t.id,
                  'border-transparent text-gray-400 hover:text-gray-200': tab !== t.id,
                }
              )}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <main className="max-w-7xl mx-auto p-6">
        {tab === 'dashboard' && (
          <div className="space-y-6">
            <PriceBoard />
            <Dashboard lastWsMessage={lastMessage} />
          </div>
        )}
        {tab === 'backtest' && <BacktestPanel />}
        {tab === 'logs' && <TradeLog trades={trades} />}
      </main>
    </div>
  );
}
