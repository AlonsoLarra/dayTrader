import { useState, useEffect, useCallback } from 'react';
import { TrendingUp, Activity, FileText, BarChart2, Zap } from 'lucide-react';
import clsx from 'clsx';
import { Dashboard } from './components/Dashboard';
import { BacktestPanel } from './components/BacktestPanel';
import { TradeLog } from './components/TradeLog';
import { KillSwitch } from './components/KillSwitch';
import { PriceBoard } from './components/PriceBoard';
import { AutoTradeModal } from './components/AutoTradeModal';
import { WalletHeader } from './components/WalletHeader';
import { useWebSocket } from './hooks/useWebSocket';
import { getTrades, getAgents, getPaperWallet } from './api/client';
import type { Trade, Agent } from './types';

type Tab = 'dashboard' | 'backtest' | 'logs';

export default function App() {
  const [tab, setTab] = useState<Tab>('dashboard');
  const [trades, setTrades] = useState<Trade[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [available, setAvailable] = useState<number>(0);
  const [showAutoTrade, setShowAutoTrade] = useState(false);
  const { lastMessage } = useWebSocket();

  const refreshAll = useCallback(async () => {
    const [t, a] = await Promise.all([getTrades({ limit: 500 }), getAgents()]);
    setTrades(t);
    setAgents(a);
  }, []);

  const refreshWallet = useCallback(async () => {
    try {
      const w = await getPaperWallet();
      setAvailable(w.available);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    refreshAll();
    refreshWallet();
  }, [refreshAll, refreshWallet]);

  useEffect(() => {
    if (lastMessage && ['trade', 'state_update'].includes(lastMessage.type)) {
      refreshAll();
      refreshWallet();
    }
  }, [lastMessage, refreshAll, refreshWallet]);

  useEffect(() => {
    const id = setInterval(refreshWallet, 30_000);
    return () => clearInterval(id);
  }, [refreshWallet]);

  const hasRunningAgents = agents.some(a => a.status === 'running');

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'dashboard', label: 'Dashboard', icon: <Activity size={16} /> },
    { id: 'backtest', label: 'Backtest', icon: <BarChart2 size={16} /> },
    { id: 'logs', label: 'Trades', icon: <FileText size={16} /> },
  ];

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      <header className="bg-gray-800 border-b border-gray-700 px-6">
        <div className="flex items-center justify-between h-14">
          <div className="flex items-center gap-0 h-full">
            <div className="flex items-center gap-2 pr-6 border-r border-gray-700 mr-2 h-full">
              <TrendingUp size={18} className="text-blue-400" />
              <span className="text-sm font-bold tracking-tight">dayTrader</span>
            </div>
            {tabs.map(t => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={clsx(
                  'flex items-center gap-2 px-4 h-full text-sm font-medium border-b-2 transition-colors',
                  tab === t.id
                    ? 'border-blue-500 text-blue-400'
                    : 'border-transparent text-gray-400 hover:text-gray-200'
                )}
              >
                {t.icon}
                {t.label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-3">
            <WalletHeader onAvailableChange={setAvailable} />

            <button
              onClick={() => setShowAutoTrade(true)}
              className="flex items-center gap-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded-lg font-medium transition-colors"
            >
              <Zap size={14} />
              Auto-Trade
            </button>

            <div className="w-px h-6 bg-gray-700" />
            <KillSwitch hasRunningAgents={hasRunningAgents} onKilled={() => { refreshAll(); refreshWallet(); }} />
          </div>
        </div>
      </header>

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

      {showAutoTrade && (
        <AutoTradeModal
          available={available}
          onClose={() => setShowAutoTrade(false)}
          onDeployed={() => { setShowAutoTrade(false); refreshAll(); refreshWallet(); }}
        />
      )}
    </div>
  );
}
