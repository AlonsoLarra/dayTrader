import { useState, useEffect, useCallback } from 'react';
import { Wallet, RefreshCw, AlertTriangle, Shield, Edit2, Check, X } from 'lucide-react';
import { getWallet, getMode, setMode, getPaperWallet, setPaperWallet, type PaperWalletData } from '../api/client';

interface Balance {
  free: number;
  used: number;
  total: number;
}

export function WalletPanel() {
  const [balances, setBalances] = useState<Record<string, Balance>>({});
  const [paperMode, setPaperMode] = useState(true);
  const [paperWallet, setPaperWalletData] = useState<PaperWalletData | null>(null);
  const [loading, setLoading] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState('');
  const [saving, setSaving] = useState(false);

  const loadPaperWallet = useCallback(async () => {
    try {
      const data = await getPaperWallet();
      setPaperWalletData(data);
    } catch {
      // ignore
    }
  }, []);

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
    loadPaperWallet();
    loadWallet();
  }, [loadWallet, loadPaperWallet]);

  // Refresh paper wallet every 30s
  useEffect(() => {
    const id = setInterval(loadPaperWallet, 30_000);
    return () => clearInterval(id);
  }, [loadPaperWallet]);

  const handleToggleMode = async () => {
    const newMode = !paperMode;
    if (!newMode) {
      const confirmed = window.confirm(
        'You are about to enable LIVE TRADING.\n\nThis will place REAL orders on your Bitso account with REAL money.\n\nAre you sure?'
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

  const handleEditBalance = () => {
    setEditValue(paperWallet?.starting_balance.toString() ?? '100');
    setEditing(true);
  };

  const handleSaveBalance = async () => {
    const val = parseFloat(editValue);
    if (!val || val <= 0) return;
    setSaving(true);
    try {
      await setPaperWallet(val);
      await loadPaperWallet();
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  const totalMXN = balances['MXN']?.total ?? 0;
  const coins = Object.entries(balances).filter(([c]) => c !== 'MXN');

  const pw = paperWallet;
  const pct = pw ? Math.min(100, (pw.deployed / pw.starting_balance) * 100) : 0;

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Wallet size={18} className="text-blue-400" />
          <h3 className="text-sm font-semibold text-gray-200 uppercase tracking-wide">
            {paperMode ? 'Paper Wallet' : 'Bitso Account'}
          </h3>
        </div>
        <button
          onClick={paperMode ? loadPaperWallet : loadWallet}
          disabled={loading}
          className="p-1.5 rounded hover:bg-gray-700 text-gray-400 hover:text-white transition-colors disabled:opacity-50"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Mode toggle */}
      <div className="flex items-center justify-between py-2 border-b border-gray-700 mb-4">
        <div className="flex items-center gap-2">
          {paperMode ? (
            <Shield size={14} className="text-blue-400" />
          ) : (
            <AlertTriangle size={14} className="text-orange-400" />
          )}
          <span className="text-sm font-medium text-white">{paperMode ? 'Paper Mode' : 'Live Trading'}</span>
        </div>
        <button
          onClick={!toggling ? handleToggleMode : undefined}
          disabled={toggling}
          className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors disabled:opacity-50 ${
            paperMode ? 'bg-gray-600' : 'bg-orange-500'
          }`}
        >
          <span
            className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
              paperMode ? 'translate-x-1' : 'translate-x-4'
            }`}
          />
        </button>
      </div>

      {!paperMode && (
        <div className="flex items-start gap-2 text-xs text-orange-300 bg-orange-900/20 border border-orange-800 rounded p-2 mb-4">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" />
          <span>Live mode active. New agents will place real orders on Bitso.</span>
        </div>
      )}

      {/* Paper wallet breakdown */}
      {paperMode && pw && (
        <div className="space-y-3">
          {/* Starting balance — editable */}
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500 uppercase tracking-wide">Capital</span>
            {editing ? (
              <div className="flex items-center gap-1">
                <span className="text-xs text-gray-400">$</span>
                <input
                  type="number"
                  value={editValue}
                  onChange={e => setEditValue(e.target.value)}
                  className="w-24 bg-gray-700 border border-gray-600 rounded px-2 py-0.5 text-sm text-white text-right focus:outline-none focus:border-blue-500"
                  autoFocus
                  onKeyDown={e => { if (e.key === 'Enter') handleSaveBalance(); if (e.key === 'Escape') setEditing(false); }}
                />
                <button onClick={handleSaveBalance} disabled={saving} className="p-0.5 text-green-400 hover:text-green-300">
                  <Check size={14} />
                </button>
                <button onClick={() => setEditing(false)} className="p-0.5 text-gray-500 hover:text-gray-300">
                  <X size={14} />
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-white">
                  ${pw.starting_balance.toLocaleString('es-MX', { minimumFractionDigits: 2 })} MXN
                </span>
                <button onClick={handleEditBalance} className="p-0.5 text-gray-500 hover:text-gray-300">
                  <Edit2 size={12} />
                </button>
              </div>
            )}
          </div>

          {/* Available */}
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500">Available</span>
            <span className={`text-sm font-semibold ${pw.available > 0 ? 'text-green-400' : 'text-red-400'}`}>
              ${pw.available.toLocaleString('es-MX', { minimumFractionDigits: 2 })} MXN
            </span>
          </div>

          {/* Deployed */}
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500">In Agents</span>
            <span className="text-sm text-gray-300">
              ${pw.deployed.toLocaleString('es-MX', { minimumFractionDigits: 2 })} MXN
            </span>
          </div>

          {/* In-market */}
          {pw.in_market > 0 && (
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-500">In Positions</span>
              <span className="text-sm text-blue-300">
                ${pw.in_market.toLocaleString('es-MX', { minimumFractionDigits: 2 })} MXN
              </span>
            </div>
          )}

          {/* Progress bar */}
          <div>
            <div className="flex justify-between text-xs text-gray-500 mb-1">
              <span>Deployed</span>
              <span>{pct.toFixed(0)}%</span>
            </div>
            <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${pct > 80 ? 'bg-orange-500' : 'bg-blue-500'}`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Live mode — real Bitso balances */}
      {!paperMode && (
        error ? (
          <div className="text-xs text-red-400 bg-red-900/20 border border-red-800 rounded p-2">{error}</div>
        ) : loading && Object.keys(balances).length === 0 ? (
          <div className="text-sm text-gray-500">Loading balances…</div>
        ) : (
          <div className="space-y-2">
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
        )
      )}
    </div>
  );
}

