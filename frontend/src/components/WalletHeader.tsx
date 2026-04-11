import { useState, useEffect, useCallback, useRef } from 'react';
import { Shield, AlertTriangle, Edit2, Check, X, ChevronDown, RefreshCw } from 'lucide-react';
import { getWallet, getMode, setMode, getPaperWallet, setPaperWallet, type PaperWalletData } from '../api/client';

interface Props {
  onAvailableChange: (amount: number) => void;
}

interface Balance {
  free: number; used: number; total: number;
}

export function WalletHeader({ onAvailableChange }: Props) {
  const [open, setOpen] = useState(false);
  const [paperMode, setPaperMode] = useState(true);
  const [paperWallet, setPaperWalletData] = useState<PaperWalletData | null>(null);
  const [balances, setBalances] = useState<Record<string, Balance>>({});
  const [loading, setLoading] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState('');
  const [saving, setSaving] = useState(false);
  const [selectedQuote, setSelectedQuote] = useState<'MXN' | 'BTC' | 'USD' | 'USDT'>('MXN');
  const ref = useRef<HTMLDivElement>(null);

  const loadPaperWallet = useCallback(async () => {
    try {
      const data = await getPaperWallet(selectedQuote);
      setPaperWalletData(data);
      const selectedBalance = data.balances?.[selectedQuote] ?? data;
      onAvailableChange(Number(selectedBalance?.available ?? 0));
    } catch {
      /* ignore */
    }
  }, [onAvailableChange, selectedQuote]);

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

  useEffect(() => {
    const id = setInterval(loadPaperWallet, 30_000);
    return () => clearInterval(id);
  }, [loadPaperWallet]);

  // Close on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

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
      if (newMode) loadPaperWallet(); else loadWallet();
    } finally {
      setToggling(false);
    }
  };

  const handleSaveBalance = async () => {
    const val = parseFloat(editValue);
    if (!val || val <= 0) return;
    setSaving(true);
    try {
      await setPaperWallet(val, selectedQuote);
      await loadPaperWallet();
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  const pw = paperWallet;
  const selectedPaperWallet = pw?.balances?.[selectedQuote] ?? pw;
  const pct = selectedPaperWallet ? Math.min(100, (selectedPaperWallet.deployed / Math.max(selectedPaperWallet.starting_balance, 1e-9)) * 100) : 0;
  const available = selectedPaperWallet?.available ?? 0;
  const totalMXN = balances["MXN"]?.total ?? 0;
  const coins = Object.entries(balances).filter(([c]) => c !== "MXN");

  return (
    <div className="relative" ref={ref}>
      {/* Pill trigger */}
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 bg-gray-700/60 border border-gray-600 rounded-lg px-3 py-1.5 hover:bg-gray-700 transition-colors"
      >
        {paperMode
          ? <Shield size={13} className="text-blue-400 shrink-0" />
          : <AlertTriangle size={13} className="text-orange-400 shrink-0" />
        }
        <span className={`text-xs font-medium ${paperMode ? "text-amber-400" : "text-orange-400"}`}>
          {paperMode ? "PAPER" : "LIVE"}
        </span>
        <div className="hidden sm:block w-px h-3.5 bg-gray-600 mx-0.5" />
        <span className="hidden sm:inline text-xs text-gray-400">Available</span>
        <span className="text-sm font-bold text-white tabular-nums">
          {available.toLocaleString("en-US", {
            minimumFractionDigits: selectedQuote === 'BTC' ? 6 : 2,
            maximumFractionDigits: selectedQuote === 'BTC' ? 6 : 2,
          })}
          <span className="text-xs font-normal text-gray-500 ml-1">{selectedQuote}</span>
        </span>
        <ChevronDown size={12} className={`text-gray-500 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute right-0 top-full mt-2 w-72 bg-gray-800 border border-gray-700 rounded-xl shadow-2xl z-50 p-4">
          {/* Header row */}
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
              {paperMode ? "Paper Wallet" : "Bitso Account"}
            </span>
            <button
              onClick={paperMode ? loadPaperWallet : loadWallet}
              disabled={loading}
              className="p-1 rounded hover:bg-gray-700 text-gray-500 hover:text-gray-300 transition-colors"
            >
              <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
            </button>
          </div>

          {/* Mode toggle row */}
          <div className="flex items-center justify-between py-2.5 border-b border-gray-700 mb-3">
            <div className="flex items-center gap-2">
              {paperMode
                ? <Shield size={13} className="text-blue-400" />
                : <AlertTriangle size={13} className="text-orange-400" />
              }
              <span className="text-sm text-white">{paperMode ? "Paper Mode" : "Live Trading"}</span>
            </div>
            <button
              onClick={!toggling ? handleToggleMode : undefined}
              disabled={toggling}
              title={paperMode ? "Switch to live trading" : "Switch to paper mode"}
              className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors disabled:opacity-50 ${
                paperMode ? "bg-gray-600" : "bg-orange-500"
              }`}
            >
              <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                paperMode ? "translate-x-1" : "translate-x-4"
              }`} />
            </button>
          </div>

          {!paperMode && (
            <div className="flex items-start gap-2 text-xs text-orange-300 bg-orange-900/20 border border-orange-800 rounded p-2 mb-3">
              <AlertTriangle size={12} className="shrink-0 mt-0.5" />
              <span>Live mode — agents place real orders on Bitso.</span>
            </div>
          )}

          {/* Paper wallet details */}
          {paperMode && pw && (
            <div className="space-y-2.5">
              <div className="flex items-center gap-2">
                {(['MXN', 'BTC', 'USD', 'USDT'] as const).map(quote => (
                  <button
                    key={quote}
                    onClick={() => {
                      setSelectedQuote(quote);
                      const nextBalance = pw.balances?.[quote] ?? pw;
                      onAvailableChange(Number(nextBalance?.available ?? 0));
                    }}
                    className={`px-2.5 py-1 rounded-full text-[11px] border transition-colors ${
                      selectedQuote === quote
                        ? 'bg-blue-600/20 text-blue-200 border-blue-500/40'
                        : 'bg-gray-700/70 text-gray-400 border-gray-600 hover:text-gray-200'
                    }`}
                  >
                    {quote}
                  </button>
                ))}
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">Capital</span>
                {editing ? (
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-gray-400">$</span>
                    <input
                      type="number"
                      value={editValue}
                      onChange={e => setEditValue(e.target.value)}
                      className="w-20 bg-gray-700 border border-gray-600 rounded px-2 py-0.5 text-sm text-white text-right focus:outline-none focus:border-blue-500"
                      autoFocus
                      onKeyDown={e => { if (e.key === "Enter") handleSaveBalance(); if (e.key === "Escape") setEditing(false); }}
                    />
                    <button onClick={handleSaveBalance} disabled={saving} className="p-0.5 text-green-400 hover:text-green-300"><Check size={13} /></button>
                    <button onClick={() => setEditing(false)} className="p-0.5 text-gray-500 hover:text-gray-300"><X size={13} /></button>
                  </div>
                ) : (
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm font-bold text-white">
                      {selectedPaperWallet?.starting_balance.toLocaleString("en-US", {
                        minimumFractionDigits: selectedQuote === 'BTC' ? 6 : 2,
                        maximumFractionDigits: selectedQuote === 'BTC' ? 6 : 2,
                      })} {selectedQuote}
                    </span>
                    <button onClick={() => { setEditValue(String(selectedPaperWallet?.starting_balance ?? 0)); setEditing(true); }}
                      className="p-0.5 text-gray-600 hover:text-gray-300">
                      <Edit2 size={11} />
                    </button>
                  </div>
                )}
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">Available</span>
                <span className={`text-sm font-semibold ${pw.available > 0 ? "text-green-400" : "text-red-400"}`}>
                  {selectedPaperWallet?.available.toLocaleString("en-US", {
                    minimumFractionDigits: selectedQuote === 'BTC' ? 6 : 2,
                    maximumFractionDigits: selectedQuote === 'BTC' ? 6 : 2,
                  })} {selectedQuote}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">In Agents</span>
                <span className="text-sm text-gray-300">
                  {selectedPaperWallet?.deployed.toLocaleString("en-US", {
                    minimumFractionDigits: selectedQuote === 'BTC' ? 6 : 2,
                    maximumFractionDigits: selectedQuote === 'BTC' ? 6 : 2,
                  })} {selectedQuote}
                </span>
              </div>
              {(selectedPaperWallet?.in_market ?? 0) > 0 && (
                <div className="flex items-center justify-between">
                  <span className="text-xs text-gray-500">In Positions</span>
                  <span className="text-sm text-blue-300">
                    {selectedPaperWallet?.in_market.toLocaleString("en-US", {
                      minimumFractionDigits: selectedQuote === 'BTC' ? 6 : 2,
                      maximumFractionDigits: selectedQuote === 'BTC' ? 6 : 2,
                    })} {selectedQuote}
                  </span>
                </div>
              )}
              <div>
                <div className="flex justify-between text-xs text-gray-600 mb-1">
                  <span>Deployed</span><span>{pct.toFixed(0)}%</span>
                </div>
                <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
                  <div className={`h-full rounded-full transition-all ${pct > 80 ? "bg-orange-500" : "bg-blue-500"}`}
                    style={{ width: `${pct}%` }} />
                </div>
              </div>
            </div>
          )}

          {/* Live balances */}
          {!paperMode && (
            error ? (
              <div className="text-xs text-red-400 bg-red-900/20 border border-red-800 rounded p-2">{error}</div>
            ) : loading && Object.keys(balances).length === 0 ? (
              <div className="text-sm text-gray-500">Loading balances…</div>
            ) : (
              <div className="space-y-1.5">
                {totalMXN > 0 && (
                  <div className="flex justify-between items-center py-1 border-b border-gray-700">
                    <span className="text-sm font-medium text-white">MXN</span>
                    <span className="text-sm text-white">${totalMXN.toLocaleString("es-MX", { minimumFractionDigits: 2 })}</span>
                  </div>
                )}
                {coins.map(([currency, bal]) => (
                  <div key={currency} className="flex justify-between items-center py-0.5">
                    <span className="text-sm text-gray-300">{currency}</span>
                    <span className="text-sm text-white font-mono">{bal.total.toFixed(6)}</span>
                  </div>
                ))}
                {Object.keys(balances).length === 0 && (
                  <div className="text-xs text-gray-500">No balances. Check API keys in .env</div>
                )}
              </div>
            )
          )}
        </div>
      )}
    </div>
  );
}
