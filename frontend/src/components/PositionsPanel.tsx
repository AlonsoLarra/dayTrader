import { useState, useEffect, useCallback, useRef } from 'react';
import { RefreshCw, TrendingUp, TrendingDown, X } from 'lucide-react';
import clsx from 'clsx';
import type { Position } from '../types';
import { getPositions, forceSell } from '../api/client';

interface Props {
  onSold?: () => void;
  refreshTrigger?: number;
}

function getQuoteCurrency(symbol: string) {
  return (symbol.includes('/') ? symbol.split('/')[1] : 'MXN').toUpperCase();
}

function getBaseAsset(symbol: string) {
  return (symbol.includes('/') ? symbol.split('/')[0] : symbol).toUpperCase();
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

function formatAssetAmount(value: number, asset = '') {
  const formatted = Number(value || 0).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 6,
  });
  return `${formatted} ${asset}`.trim();
}

export function PositionsPanel({ onSold, refreshTrigger }: Props) {
  const [positions, setPositions] = useState<Position[]>([]);
  const [spinning, setSpinning] = useState(false);
  const [selling, setSelling] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const initialLoad = useRef(false);

  const load = useCallback(async (showSpinner = false) => {
    if (showSpinner) setSpinning(true);
    try {
      const data = await getPositions();
      setPositions(data.positions);
    } catch {
      // ignore silently
    } finally {
      if (showSpinner) setSpinning(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    if (!initialLoad.current) {
      initialLoad.current = true;
      load(true);
    }
  }, [load]);

  // Refresh when running agents change — background, no spinner
  useEffect(() => {
    if (initialLoad.current) load(false);
  }, [load, refreshTrigger]);

  // Auto-refresh every 15s — background, no spinner, no flicker
  useEffect(() => {
    const id = setInterval(() => load(false), 15_000);
    return () => clearInterval(id);
  }, [load]);

  const handleForceSell = async (agentId: string) => {
    setSelling(agentId);
    setError(null);
    setConfirm(null);
    try {
      await forceSell(agentId);
      await load(false);
      onSold?.();
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Sell failed';
      setError(msg);
    } finally {
      setSelling(null);
    }
  };

  if (positions.length === 0) return null;

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold text-gray-200 uppercase tracking-wide">Open Positions</h3>
          <p className="text-xs text-gray-500 mt-0.5">Live unrealized P&amp;L — auto-refreshes every 15s</p>
        </div>
        <button
          onClick={() => load(true)}
          disabled={spinning}
          className="p-1.5 rounded hover:bg-gray-700 text-gray-400 hover:text-white disabled:opacity-50"
        >
          <RefreshCw size={14} className={spinning ? 'animate-spin' : ''} />
        </button>
      </div>

      {error && (
        <div className="mb-3 text-xs text-red-400 bg-red-900/20 border border-red-800 rounded px-3 py-2">{error}</div>
      )}

      <div className="space-y-3">
        {positions.map(pos => {
          const pnlPositive = (pos.unrealized_pnl ?? 0) >= 0;
          const isConfirming = confirm === pos.agent_id;
          const isSelling = selling === pos.agent_id;
          const quoteCurrency = getQuoteCurrency(pos.symbol);
          const baseAsset = getBaseAsset(pos.symbol);
          const entryValue = pos.cost_basis ?? (pos.entry_price * pos.amount);
          const currentValue = pos.proceeds_if_sold ?? (pos.current_price != null ? pos.current_price * pos.amount : null);

          return (
            <div key={pos.agent_id} className="rounded-lg border border-gray-700 p-3 bg-gray-900">
              {/* Header row */}
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-gray-400">{pos.agent_id}</span>
                  <span className="text-xs bg-blue-900/60 text-blue-300 px-2 py-0.5 rounded font-mono">{pos.symbol}</span>
                  <span className="text-xs text-gray-500">{pos.strategy}</span>
                </div>
                {pnlPositive ? (
                  <TrendingUp size={14} className="text-green-400" />
                ) : (
                  <TrendingDown size={14} className="text-red-400" />
                )}
              </div>

              {/* Position info grid */}
              <div className="grid grid-cols-3 gap-3 mb-3">
                <div>
                  <div className="text-xs text-gray-500 mb-0.5">Entry Value</div>
                  <div className="text-sm text-white font-mono">{formatQuoteAmount(entryValue, quoteCurrency)}</div>
                  <div className="text-[11px] text-gray-500 mt-0.5">@ {formatQuoteAmount(pos.entry_price, quoteCurrency)} each</div>
                </div>
                <div>
                  <div className="text-xs text-gray-500 mb-0.5">Current Value</div>
                  <div className="text-sm text-white font-mono">
                    {currentValue != null
                      ? formatQuoteAmount(currentValue, quoteCurrency)
                      : '—'}
                  </div>
                  <div className="text-[11px] text-gray-500 mt-0.5">
                    {pos.current_price != null ? `@ ${formatQuoteAmount(pos.current_price, quoteCurrency)} each` : 'Live price unavailable'}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-500 mb-0.5">Unrealized P&amp;L</div>
                  <div className={clsx('text-sm font-bold font-mono', pnlPositive ? 'text-green-400' : 'text-red-400')}>
                    {pos.unrealized_pnl != null
                      ? `${pnlPositive ? '+' : '-'}${formatQuoteAmount(Math.abs(pos.unrealized_pnl), quoteCurrency)}`
                      : '—'}
                    {pos.pnl_pct != null && (
                      <span className="text-xs font-normal ml-1 opacity-70">
                        ({pnlPositive ? '+' : ''}{pos.pnl_pct.toFixed(2)}%)
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Position size info */}
              <div className="flex items-center justify-between bg-gray-800 rounded px-3 py-2 mb-3">
                <div className="text-xs text-gray-400">
                  Position size
                </div>
                <div className="text-sm font-bold text-white">
                  {formatAssetAmount(pos.amount, baseAsset)}
                </div>
              </div>

              {/* Sell button */}
              {!isConfirming ? (
                <button
                  onClick={() => setConfirm(pos.agent_id)}
                  className="w-full py-1.5 text-sm rounded border border-gray-600 text-gray-300 hover:border-red-600 hover:text-red-400 transition-colors"
                >
                  Close Position
                </button>
              ) : (
                <div className="flex gap-2">
                  <button
                    onClick={() => handleForceSell(pos.agent_id)}
                    disabled={isSelling}
                    className="flex-1 py-1.5 text-sm rounded bg-red-700 hover:bg-red-600 text-white font-medium disabled:opacity-50"
                  >
                    {isSelling ? 'Selling…' : `Confirm Sell at ${pos.current_price != null ? formatQuoteAmount(pos.current_price, quoteCurrency) : '?'}`}
                  </button>
                  <button
                    onClick={() => setConfirm(null)}
                    className="p-1.5 rounded border border-gray-600 text-gray-400 hover:text-white"
                  >
                    <X size={14} />
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
