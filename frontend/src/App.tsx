import { useState, useEffect, useCallback } from 'react';
import { TrendingUp, Activity, FileText, BarChart2, LogOut, Menu, X, Zap } from 'lucide-react';
import clsx from 'clsx';
import { Dashboard } from './components/Dashboard';
import { BacktestPanel } from './components/BacktestPanel';
import { TradeLog } from './components/TradeLog';
import { AutoWatcherLogPanel } from './components/AutoWatcherLogPanel';
import { KillSwitch } from './components/KillSwitch';
import { PriceBoard } from './components/PriceBoard';
import { AutoTradeModal } from './components/AutoTradeModal';
import { WalletHeader } from './components/WalletHeader';
import { LoginScreen } from './components/LoginScreen';
import { useWebSocket } from './hooks/useWebSocket';
import { getTrades, getAgents, getPaperWallet, getTradeSummary } from './api/client';
import type { Trade, Agent, TradeSummary } from './types';

type Tab = 'dashboard' | 'backtest' | 'logs';

export default function App() {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('daytrader_token'));
  const [tab, setTab] = useState<Tab>('dashboard');
  const [trades, setTrades] = useState<Trade[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [summary, setSummary] = useState<TradeSummary | null>(null);
  const [available, setAvailable] = useState<number>(0);
  const [showAutoTrade, setShowAutoTrade] = useState(false);
  const [showDrawer, setShowDrawer] = useState(false);
  const { lastMessage } = useWebSocket(Boolean(token));

  // Listen for 401 logout signal from axios interceptor
  useEffect(() => {
    const onLogout = () => setToken(null);
    window.addEventListener('daytrader:logout', onLogout);
    return () => window.removeEventListener('daytrader:logout', onLogout);
  }, []);

  const refreshAll = useCallback(async () => {
    try {
      const [t, a, s] = await Promise.all([
        getTrades({ limit: 500 }),
        getAgents(),
        getTradeSummary(),
      ]);
      setTrades(t);
      setAgents(a);
      setSummary(s);
    } catch {
      // Ignore transient auth/network failures; the login screen handles auth state.
    }
  }, []);

  const refreshWallet = useCallback(async () => {
    try {
      const w = await getPaperWallet();
      setAvailable(w.available);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (!token) return;
    refreshAll();
    refreshWallet();
  }, [token, refreshAll, refreshWallet]);

  useEffect(() => {
    if (!token) return;
    if (lastMessage && ['trade', 'state_update'].includes(lastMessage.type)) {
      refreshAll();
      refreshWallet();
    }
  }, [token, lastMessage, refreshAll, refreshWallet]);

  useEffect(() => {
    if (!token) return;
    const id = setInterval(refreshWallet, 30_000);
    return () => clearInterval(id);
  }, [token, refreshWallet]);

  const hasRunningAgents = agents.some(a => a.status === 'running');

  const handleLogout = () => {
    localStorage.removeItem('daytrader_token');
    setToken(null);
  };

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'dashboard', label: 'Dashboard', icon: <Activity size={16} /> },
    { id: 'backtest', label: 'Strategy', icon: <BarChart2 size={16} /> },
    { id: 'logs', label: 'Trades', icon: <FileText size={16} /> },
  ];

  if (!token) {
    return <LoginScreen onAuthenticated={t => setToken(t)} />;
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      {/* ── Header ── */}
      <header className="bg-gray-800 border-b border-gray-700 sticky top-0 z-30">
        {/* Mobile header */}
        <div className="flex lg:hidden items-center justify-between h-14 px-4">
          <div className="flex items-center gap-2">
            <TrendingUp size={18} className="text-blue-400" />
            <span className="text-sm font-bold tracking-tight">dayTrader</span>
          </div>
          <div className="flex items-center gap-2">
            <WalletHeader onAvailableChange={setAvailable} />
            <button
              onClick={() => setShowDrawer(true)}
              className="p-2 text-gray-400 hover:text-white hover:bg-gray-700 rounded-lg transition-colors"
              aria-label="Open menu"
            >
              <Menu size={20} />
            </button>
          </div>
        </div>

        {/* Desktop header */}
        <div className="hidden lg:flex items-center justify-between h-14 px-6">
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
              <Zap size={15} />
              <span>Auto-Trade</span>
            </button>
            <div className="w-px h-6 bg-gray-700" />
            <KillSwitch hasRunningAgents={hasRunningAgents} onKilled={() => { refreshAll(); refreshWallet(); }} />
            <div className="w-px h-6 bg-gray-700" />
            <button
              onClick={handleLogout}
              title="Sign out"
              className="p-1.5 text-gray-400 hover:text-white hover:bg-gray-700 rounded transition-colors"
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </header>

      {/* ── Main content ── */}
      <main className="max-w-7xl mx-auto p-4 lg:p-6 pb-24 lg:pb-6">
        {tab === 'dashboard' && (
          <div className="space-y-4 md:space-y-6">
            <PriceBoard />
            <Dashboard
              agents={agents}
              trades={trades}
              summary={summary}
              onRefresh={refreshAll}
            />
          </div>
        )}
        {tab === 'backtest' && <BacktestPanel />}
        {tab === 'logs' && (
          <div className="space-y-6">
            <AutoWatcherLogPanel />
            <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
              <h2 className="text-sm font-semibold text-gray-200 mb-4">Trade History</h2>
              <TradeLog trades={trades} />
            </div>
          </div>
        )}
      </main>

      {/* ── Mobile bottom nav ── */}
      <nav
        className="fixed bottom-0 inset-x-0 z-30 lg:hidden bg-gray-800 border-t border-gray-700 flex"
        style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
      >
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={clsx(
              'flex-1 flex flex-col items-center justify-center gap-1 py-2 min-h-[56px] transition-colors',
              tab === t.id ? 'text-blue-400' : 'text-gray-500'
            )}
          >
            {t.icon}
            <span className="text-[10px] font-medium">{t.label}</span>
          </button>
        ))}
      </nav>

      {/* ── Mobile drawer ── */}
      {showDrawer && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setShowDrawer(false)}
          />
          <div className="absolute right-0 top-0 bottom-0 w-72 bg-gray-800 border-l border-gray-700 flex flex-col shadow-2xl">
            <div className="flex items-center justify-between p-4 border-b border-gray-700">
              <span className="text-sm font-semibold text-white">Menu</span>
              <button
                onClick={() => setShowDrawer(false)}
                className="p-1.5 text-gray-400 hover:text-white hover:bg-gray-700 rounded transition-colors"
              >
                <X size={18} />
              </button>
            </div>
            <div className="flex flex-col gap-3 p-4">
              <button
                onClick={() => { setShowAutoTrade(true); setShowDrawer(false); }}
                className="flex items-center gap-3 px-4 py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-medium transition-colors"
              >
                <Zap size={16} />
                <span>Auto-Trade</span>
              </button>
              <KillSwitch
                hasRunningAgents={hasRunningAgents}
                onKilled={() => { refreshAll(); refreshWallet(); setShowDrawer(false); }}
              />
            </div>
            <div className="mt-auto p-4 border-t border-gray-700">
              <button
                onClick={handleLogout}
                className="flex items-center gap-3 px-4 py-3 w-full text-gray-400 hover:text-white hover:bg-gray-700 rounded-lg transition-colors"
              >
                <LogOut size={16} />
                <span className="text-sm">Sign Out</span>
              </button>
            </div>
          </div>
        </div>
      )}

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
