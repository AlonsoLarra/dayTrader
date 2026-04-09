import { useEffect, useState } from 'react';
import { X, Zap, CheckCircle, BarChart2 } from 'lucide-react';
import { analyzeMarket, deployPortfolio, getMarkets, getPaperWallet } from '../api/client';
import type { PairAnalysis, DeployResult } from '../types';

interface Props {
  available: number;
  onClose: () => void;
  onDeployed: () => void;
}

type Status = 'idle' | 'working' | 'done';
type BudgetMode = 'fixed' | 'percent';
type QuoteCurrency = 'MXN' | 'BTC' | 'USD' | 'USDT';

function getActionBadgeClass(action?: string) {
  if (action === 'BUY SIGNAL') return 'bg-green-500/15 text-green-300 border-green-500/30';
  if (action === 'SELL SIGNAL') return 'bg-red-500/15 text-red-300 border-red-500/30';
  return 'bg-gray-700/70 text-gray-300 border-gray-600';
}

function getQuoteDecimals(quoteCurrency: QuoteCurrency) {
  return quoteCurrency === 'BTC' ? 8 : 2;
}

function formatAmount(value: number, quoteCurrency: QuoteCurrency) {
  const digits = quoteCurrency === 'BTC' ? 6 : 2;
  return Number(value || 0).toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatBudgetInput(value: number, quoteCurrency: QuoteCurrency) {
  if (quoteCurrency === 'BTC') {
    const safeValue = value > 0 ? value : 0.001;
    return safeValue.toFixed(4);
  }
  return value > 0 ? String(Math.floor(value)) : '100';
}

export function AutoTradeModal({ available, onClose, onDeployed }: Props) {
  const [quoteCurrency, setQuoteCurrency] = useState<QuoteCurrency>('MXN');
  const [quoteAvailable, setQuoteAvailable] = useState<number>(available);
  const [walletBalances, setWalletBalances] = useState<Record<string, { available: number }> | null>(null);
  const [budgetMode, setBudgetMode] = useState<BudgetMode>('fixed');
  const [fixedAmount, setFixedAmount] = useState<string>(formatBudgetInput(available, 'MXN'));
  const [pct, setPct] = useState<number>(100);
  const [status, setStatus] = useState<Status>('idle');
  const [pairs, setPairs] = useState<PairAnalysis[]>([]);
  const [scanSymbols, setScanSymbols] = useState<string[]>([]);
  const [totalMarkets, setTotalMarkets] = useState<number>(0);
  const [result, setResult] = useState<DeployResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    Promise.resolve(getPaperWallet())
      .then(data => {
        if (!active || !data) return;
        setWalletBalances(data.balances ?? null);
        const selected = data.balances?.[quoteCurrency] ?? data;
        const nextAvailable = Number(selected?.available ?? (quoteCurrency === 'MXN' ? available : 0));
        setQuoteAvailable(nextAvailable);
        setFixedAmount(formatBudgetInput(nextAvailable, quoteCurrency));
      })
      .catch(() => {
        if (!active) return;
        const fallback = quoteCurrency === 'MXN' ? available : 0;
        setQuoteAvailable(fallback);
        setFixedAmount(formatBudgetInput(fallback, quoteCurrency));
      });

    return () => {
      active = false;
    };
  }, [available, quoteCurrency]);

  const budget =
    budgetMode === 'fixed'
      ? parseFloat(fixedAmount) || 0
      : Number(((quoteAvailable || 0) * (pct / 100)).toFixed(getQuoteDecimals(quoteCurrency)));

  const overBudget = quoteAvailable > 0 && budget > quoteAvailable + 1e-9;

  async function handleStart() {
    if (budget <= 0) {
      setError('Enter a valid amount');
      return;
    }
    if (overBudget) {
      setError(`Only ${formatAmount(quoteAvailable, quoteCurrency)} ${quoteCurrency} available`);
      return;
    }

    setError(null);
    setStatus('working');
    setPairs([]);
    setScanSymbols([]);
    setTotalMarkets(0);
    setResult(null);

    try {
      const marketsPromise = Promise.resolve(getMarkets(quoteCurrency))
        .then(d => {
          setScanSymbols(Array.isArray(d?.symbols) ? d.symbols : []);
        })
        .catch(() => {
          setScanSymbols([]);
        });

      const analysis = await analyzeMarket(10, quoteCurrency);
      await marketsPromise;
      setPairs(analysis.pairs);
      setTotalMarkets(Number(analysis.total_markets ?? analysis.pairs.length ?? 0));

      const r = await deployPortfolio({
        budget,
        max_agents: 3,
        min_score: 20,
        quote_currency: quoteCurrency,
        rotation_enabled: true,
        rotation_interval_minutes: 1,
        aggressive_rotation: true,
        min_rotation_score_delta: 1,
      });
      setResult(r);
      setStatus('done');
    } catch (e: unknown) {
      const msg =
        typeof e === 'object' && e !== null && 'response' in e
          ? String((e as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Failed')
          : e instanceof Error ? e.message : 'Failed';
      setError(msg);
      setStatus('idle');
    }
  }

  const resultQuote = ((result?.quote_currency as QuoteCurrency | undefined) ?? quoteCurrency);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-gray-800 border border-gray-700 rounded-xl shadow-2xl w-full max-w-lg mx-4 p-6">
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-blue-400" />
            <span className="font-semibold text-gray-100">Auto-Trade</span>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 transition-colors">
            <X size={18} />
          </button>
        </div>

        {status === 'done' && result && (
          <div className="flex flex-col items-center gap-4 py-4 text-center">
            <CheckCircle className="w-12 h-12 text-green-400" />
            <div className="text-green-400 font-semibold">Agents started</div>
            <p className="text-sm text-gray-400">
              {formatAmount(result.total_budget, resultQuote)} {resultQuote} spread across{' '}
              {result.agent_ids.length} pair{result.agent_ids.length !== 1 ? 's' : ''}.
              They will begin trading within 30 seconds and re-check the full market every minute.
            </p>
            <div className="flex flex-wrap justify-center gap-2 mt-1">
              {result.pairs.map(p => (
                <span
                  key={p.symbol}
                  className="text-xs bg-blue-900/40 text-blue-300 border border-blue-800/40 rounded-full px-3 py-1 font-mono"
                >
                  {p.symbol.split('/')[0]} · {formatAmount(p.budget_allocated, resultQuote)} {resultQuote}
                </span>
              ))}
            </div>
            <button
              onClick={onDeployed}
              className="mt-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-sm text-gray-200 rounded-lg transition-colors"
            >
              Close
            </button>
          </div>
        )}

        {status === 'working' && (
          <div className="flex flex-col items-center gap-4 py-4 text-center">
            <svg className="animate-spin w-8 h-8 text-blue-400" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8v8z" />
            </svg>
            <p className="text-sm text-gray-300">
              {pairs.length === 0
                ? `Scanning all available Bitso ${quoteCurrency} markets…`
                : `Reviewed ${totalMarkets || pairs.length} markets — showing the best long setups…`}
            </p>

            {pairs.length === 0 ? (
              <div className="w-full bg-gray-900/50 border border-gray-700 rounded-lg p-4 text-left space-y-4">
                <div>
                  <div className="text-xs font-semibold text-gray-300 mb-2">Checking each market for</div>
                  <div className="grid gap-2 sm:grid-cols-2 text-xs text-gray-500">
                    <div>• Trend and EMA direction</div>
                    <div>• RSI pullback entry</div>
                    <div>• Volume confirmation</div>
                    <div>• Confidence and upside quality</div>
                  </div>
                </div>

                {scanSymbols.length > 0 && (
                  <div>
                    <div className="text-xs font-semibold text-gray-300 mb-2">
                      Markets in this scan ({scanSymbols.length})
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {scanSymbols.slice(0, 12).map(symbol => (
                        <span
                          key={symbol}
                          className="text-[11px] px-2.5 py-1 rounded-full bg-gray-800/80 text-blue-200 border border-gray-600 font-mono"
                        >
                          {symbol}
                        </span>
                      ))}
                      {scanSymbols.length > 12 && (
                        <span className="text-[11px] px-2.5 py-1 rounded-full bg-gray-800/80 text-gray-300 border border-gray-600">
                          +{scanSymbols.length - 12} more
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="w-full bg-gray-900/50 border border-gray-700 rounded-lg p-3 text-left max-h-72 overflow-y-auto">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-gray-300">Markets reviewed</span>
                  <span className="text-[11px] text-gray-500">
                    {totalMarkets > pairs.length ? `Top ${pairs.length} of ${totalMarkets}` : 'Top candidates first'}
                  </span>
                </div>
                <div className="space-y-2">
                  {pairs.slice(0, 5).map(pair => (
                    <div key={pair.symbol} className="rounded-lg border border-gray-700 bg-gray-800/70 p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="text-sm font-semibold text-white">{pair.symbol}</div>
                          <div className="text-[11px] text-gray-500 uppercase tracking-wide">
                            {(pair.strategy ?? 'market scan').replace('_', ' ')}
                          </div>
                        </div>
                        <div className="flex flex-wrap justify-end gap-1.5">
                          <span className={`text-[10px] px-2 py-0.5 rounded-full border ${getActionBadgeClass(pair.action)}`}>
                            {pair.action ?? 'WAITING'}
                          </span>
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-500/15 text-blue-300 border border-blue-500/30">
                            Score {pair.score.toFixed(0)}
                          </span>
                          {typeof pair.expected_roi_pct === 'number' && pair.expected_roi_pct > 0 && (
                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                              ROI ~{pair.expected_roi_pct.toFixed(1)}%
                            </span>
                          )}
                          {typeof pair.confidence === 'number' && (
                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-700/80 text-gray-300 border border-gray-600">
                              {Math.round(pair.confidence * 100)}% conf
                            </span>
                          )}
                        </div>
                      </div>
                      <p className="text-xs text-gray-400 mt-2 leading-relaxed">{pair.reason}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {status === 'idle' && (
          <div className="space-y-5">
            <p className="text-sm text-gray-400">
              Set a budget and the system will automatically find the best crypto positions now, then keep re-evaluating the market every minute.
            </p>

            <div>
              <label htmlFor="auto-trade-quote" className="block text-xs text-gray-500 mb-2">
                Quote currency
              </label>
              <select
                id="auto-trade-quote"
                value={quoteCurrency}
                onChange={e => {
                  const nextQuote = e.target.value as QuoteCurrency;
                  const nextAvailable = Number(walletBalances?.[nextQuote]?.available ?? (nextQuote === 'MXN' ? available : 0));
                  setQuoteCurrency(nextQuote);
                  setQuoteAvailable(nextAvailable);
                  setFixedAmount(formatBudgetInput(nextAvailable, nextQuote));
                }}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
              >
                <option value="MXN">MXN markets</option>
                <option value="BTC">BTC markets</option>
                <option value="USD">USD markets</option>
                <option value="USDT">USDT markets</option>
              </select>
            </div>

            <div>
              <label className="block text-xs text-gray-500 mb-2">How much to trade with?</label>
              <div className="flex gap-2">
                <div className="flex rounded-lg overflow-hidden border border-gray-600 text-xs font-medium shrink-0">
                  <button
                    onClick={() => setBudgetMode('fixed')}
                    className={`px-3 py-2 transition-colors ${budgetMode === 'fixed' ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'}`}
                  >
                    Fixed
                  </button>
                  <button
                    onClick={() => setBudgetMode('percent')}
                    className={`px-3 py-2 transition-colors ${budgetMode === 'percent' ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'}`}
                  >
                    % of wallet
                  </button>
                </div>

                {budgetMode === 'fixed' ? (
                  <input
                    type="number"
                    min={quoteCurrency === 'BTC' ? 0.0001 : 1}
                    step={quoteCurrency === 'BTC' ? 0.0001 : 10}
                    value={fixedAmount}
                    onChange={e => setFixedAmount(e.target.value)}
                    className={`flex-1 bg-gray-700 border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500 ${overBudget ? 'border-red-500' : 'border-gray-600'}`}
                    placeholder={quoteCurrency}
                  />
                ) : (
                  <div className="flex-1 flex items-center gap-3">
                    <input
                      type="range"
                      min={10}
                      max={100}
                      step={5}
                      value={pct}
                      onChange={e => setPct(Number(e.target.value))}
                      className="flex-1 accent-blue-500"
                    />
                    <span className="text-sm text-white font-medium w-8 text-right">{pct}%</span>
                  </div>
                )}
              </div>

              <div className="flex justify-between mt-1.5 text-xs">
                <span className="text-gray-600">Split across up to 3 pairs automatically</span>
                <span className={overBudget ? 'text-red-400' : 'text-gray-500'}>
                  {formatAmount(budget, quoteCurrency)} / {formatAmount(quoteAvailable, quoteCurrency)} {quoteCurrency} available
                </span>
              </div>
            </div>

            <div className="bg-gray-900/50 rounded-lg p-3 text-xs text-gray-500 space-y-1.5">
              <div className="flex items-start gap-2">
                <BarChart2 className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                <span>Scans all available Bitso {quoteCurrency} markets using RSI and trend signals to find the best opportunities now</span>
              </div>
              <div className="flex items-start gap-2">
                <Zap className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                <span>Automatically opens positions across 1-3 top-ranked pairs, then rechecks every minute and can rotate into stronger setups</span>
              </div>
            </div>

            {error && (
              <div className="text-xs text-red-400 bg-red-950/40 border border-red-800 rounded-lg px-3 py-2">{error}</div>
            )}

            <div className="flex gap-3">
              <button
                onClick={onClose}
                className="flex-1 py-2.5 bg-gray-700 hover:bg-gray-600 text-sm text-gray-300 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleStart}
                disabled={budget <= 0 || overBudget}
                className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
              >
                <Zap size={14} />
                Start Trading
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
