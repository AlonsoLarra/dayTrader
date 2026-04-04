import { useState, useEffect, useCallback } from 'react';
import { Wallet, RefreshCw, AlertTriangle, ToggleLeft, ToggleRight } from 'lucide-react';
import { getWallet, getMode, setMode } from '../api/client';

interface Balance {
  free: number;
  used: number;
  total: number;
}

export function WalletPanel() {
  const [balances, setBalances] = useState<Record<string, Balance>>({});
  const [paperMode, setPaperMode] = useState(true);
  const [loading, setLoading] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadWallet = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getWallet();
      setBalances(data.balances);
      setPaperMode(data.paper_mode);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Failed to load wallet';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    getMode().then(d => setPaperMode(d.paper_mode)).catch(() => {});
    loadWallet();
  }, [loadWallet]);

  const handleToggleMode = async () => {
    const newMode = !paperMode;
    if (!newMode) {
      const confirmed = window.confirm(
        '⚠️ You are about to enable LIVE TRADING.\n\nThis will place REAL orders on your Bitso account with REAL money.\n\nAre you sure?'
      );
      if (!confirmed) return;
    }
    setToggling(true);
    try {
      await setMode(newMode);
      setPaperMode(newMode);
    } finally {
      setToggling(false);
    }
  };

  const totalMXN = balances['MXN']?.total ?? 0;
  const coins = Object.entries(balances).filter(([c]) => c !== 'MXN');

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Wallet size={18} className="text-blue-400" />
          <h3 className="text-white font-semibold">Bitso Wallet</h3>
          <span className="text-xs text-gray-500">(real balance)</span>
        </div>
        <button
          onClick={loadWallet}
          disabled={loading}
          className="p-1.5 rounded hover:bg-gray-700 text-gray-400 hover:text-white transition-colors disabled:opacity-50"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Live / Paper toggle */}
      <div
        className={`flex items-center justify-between rounded-lg p-3 mb-4 border cursor-pointer ${
          paperMode
            ? 'bg-gray-900 border-gray-600'
            : 'bg-orange-900/30 border-orange-600'
        }`}
        onClick={!toggling ? handleToggleMode : undefined}
      >
        <div>
          <div className="text-sm font-medium text-white">
            {paperMode ? '🧪 Paper Mode (Safe)' : '🔴 Live Trading (Real Money)'}
          </div>
          <div className="text-xs text-gray-400 mt-0.5">
            {paperMode
              ? 'Agents trade with simulated money. Click to enable live mode.'
              : 'Agents will place real orders on Bitso. Click to switch back to paper.'}
          </div>
        </div>
        <div className="ml-3 shrink-0">
          {paperMode ? (
            <ToggleLeft size={28} className="text-gray-400" />
          ) : (
            <ToggleRight size={28} className="text-orange-400" />
          )}
        </div>
      </div>

      {!paperMode && (
        <div className="flex items-start gap-2 text-xs text-orange-300 bg-orange-900/20 border border-orange-800 rounded p-2 mb-4">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" />
          <span>Live mode is active. New agents will place real orders on Bitso.</span>
        </div>
      )}

      {error ? (
        <div className="text-xs text-red-400 bg-red-900/20 border border-red-800 rounded p-2">{error}</div>
      ) : loading && Object.keys(balances).length === 0 ? (
        <div className="text-sm text-gray-500">Loading balances…</div>
      ) : (
        <div className="space-y-2">
          {/* MXN first */}
          {totalMXN > 0 && (
            <div className="flex justify-between items-center py-1.5 border-b border-gray-700">
              <span className="text-sm font-medium text-white">MXN</span>
              <div className="text-right">
                <div className="text-sm text-white">${totalMXN.toLocaleString('es-MX', { minimumFractionDigits: 2 })}</div>
                {balances['MXN']?.used > 0 && (
                  <div className="text-xs text-gray-500">In orders: ${balances['MXN'].used.toFixed(2)}</div>
                )}
              </div>
            </div>
          )}
          {coins.map(([currency, bal]) => (
            <div key={currency} className="flex justify-between items-center py-1">
              <span className="text-sm text-gray-300">{currency}</span>
              <div className="text-right">
                <div className="text-sm text-white">{bal.total.toFixed(8)}</div>
                {bal.used > 0 && (
                  <div className="text-xs text-gray-500">In orders: {bal.used.toFixed(8)}</div>
                )}
              </div>
            </div>
          ))}
          {Object.keys(balances).length === 0 && (
            <div className="text-sm text-gray-500">No balances found. Check your API keys in .env</div>
          )}
        </div>
      )}
    </div>
  );
}
