import { useEffect, useRef, useState } from 'react';
import { Zap, CheckCircle, BarChart2, RotateCcw } from 'lucide-react';
import { analyzeMarket, deployPortfolio, getMarkets, getPaperWallet } from '../api/client';
import type { PairAnalysis, DeployResult } from '../types';
import { RiskSlider, RISK_LEVELS } from './RiskSlider';

interface Props {
  available: number;
  onDeployed: () => void;
}

type Status = 'idle' | 'working' | 'done';

function getActionBadgeClass(action?: string) {
  if (action === 'BUY SIGNAL') return 'bg-green-500/15 text-green-300 border-green-500/30';
  if (action === 'SELL SIGNAL') return 'bg-red-500/15 text-red-300 border-red-500/30';
  return 'bg-gray-700/70 text-gray-300 border-gray-600';
}

function formatUSD(value: number) {
  return Number(value || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function DeployPanel({ available, onDeployed }: Props) {
  const [riskLevel, setRiskLevel] = useState(3);
  const [usdAvailable, setUsdAvailable] = useState<number>(available);
  const [fixedAmount, setFixedAmount] = useState<string>('100');
  const [status, setStatus] = useState<Status>('idle');
  const [pairs, setPairs] = useState<PairAnalysis[]>([]);
  const [scanSymbols, setScanSymbols] = useState<string[]>([]);
  const [totalMarkets, setTotalMarkets] = useState<number>(0);
  const [result, setResult] = useState<DeployResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorIsNetwork, setErrorIsNetwork] = useState(false);
  const workingRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getPaperWallet('USD')
      .then(data => {
        const bal = data.balances?.['USD'] ?? data;
        const next = Number(bal?.available ?? available);
        setUsdAvailable(next);
        setFixedAmount(String(Math.floor(next) || 100));
      })
      .catch(() => {
        setUsdAvailable(available);
        setFixedAmount(String(Math.floor(available) || 100));
      });
  }, [available]);

  useEffect(() => {
    if (status === 'working' && workingRef.current) {
      if (typeof workingRef.current.scrollIntoView === 'function') {
        workingRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }
  }, [status]);

  const budget = parseFloat(fixedAmount) || 0;
  const overBudget = usdAvailable > 0 && budget > usdAvailable + 1e-9;
  const levelInfo = RISK_LEVELS[riskLevel] ?? RISK_LEVELS[3];

  async function handleStart(retryCount = 0) {
    if (budget <= 0) { setError('Enter a valid amount'); setErrorIsNetwork(false); return; }
    if (overBudget) { setError(`Only $${formatUSD(usdAvailable)} USD available`); setErrorIsNetwork(false); return; }

    setError(null);
    setErrorIsNetwork(false);
    setStatus('working');
    setPairs([]);
    setScanSymbols([]);
    setTotalMarkets(0);
    setResult(null);

    try {
      const marketsPromise = getMarkets('USD')
        .then(data => {
          const symbols = Array.isArray(data?.symbols) ? data.symbols : [];
          setScanSymbols(symbols);
          return symbols;
        })
        .catch(() => { setScanSymbols([]); return [] as string[]; });

      const analysisPromise = analyzeMarket(0, 'USD');
      const [, analysis] = await Promise.all([marketsPromise, analysisPromise]);
      setPairs(analysis.pairs);
      setTotalMarkets(Number(analysis.total_markets ?? analysis.pairs.length ?? 0));

      const r = await deployPortfolio({
        budget,
        max_agents: levelInfo.maxBots,
        min_score: levelInfo.minScore,
        quote_currency: 'USD',
        rotation_enabled: true,
        rotation_interval_minutes: 1,
        aggressive_rotation: riskLevel >= 4,
        min_rotation_score_delta: 1,
        risk_level: riskLevel,
      });
      setResult(r);
      setStatus('done');
      onDeployed();
    } catch (e: unknown) {
      const isNetworkError = e instanceof Error &&
        (e.message === 'Network Error' || e.message.toLowerCase().includes('network'));
      const isTimeout = typeof e === 'object' && e !== null && 'code' in e &&
        (e as { code?: string }).code === 'ECONNABORTED';

      if ((isNetworkError || isTimeout) && retryCount < 1) {
        await new Promise(r => setTimeout(r, 250));
        return handleStart(retryCount + 1);
      }

      const msg = isNetworkError
        ? 'Network error. Check your signal and try again.'
        : isTimeout
          ? 'Request timed out. The market scan is taking too long — try again.'
          : typeof e === 'object' && e !== null && 'response' in e
            ? String((e as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Failed')
            : e instanceof Error ? e.message : 'Failed';
      setError(msg);
      setErrorIsNetwork(isNetworkError || isTimeout);
      setStatus('idle');
    }
  }

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-5">
      <div className="flex items-center gap-2 mb-5">
        <Zap className="w-4 h-4 text-blue-400" />
        <span className="text-sm font-semibold text-gray-100">Auto-Trade</span>
      </div>

      {/* ── Done state ── */}
      {status === 'done' && result && (
        <div className="flex flex-col items-center gap-4 py-2 text-center">
          <CheckCircle className="w-10 h-10 text-green-400" />
          <div className="text-green-400 font-semibold">Agents started</div>
          <p className="text-sm text-gray-400">
            ${formatUSD(result.total_budget)} USD spread across{' '}
            {result.agent_ids.length} pair{result.agent_ids.length !== 1 ? 's' : ''}.
            They will begin trading within 30 seconds and re-check the market every minute.
          </p>
          <div className="flex flex-wrap justify-center gap-2 mt-1">
            {result.pairs.map(p => (
              <span
                key={p.symbol}
                className="text-xs bg-blue-900/40 text-blue-300 border border-blue-800/40 rounded-full px-3 py-1 font-mono"
              >
                {p.symbol.split('/')[0]} · ${formatUSD(p.budget_allocated)}
              </span>
            ))}
          </div>
          <button
            onClick={() => setStatus('idle')}
            className="mt-1 flex items-center gap-1.5 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-sm text-gray-200 rounded-lg transition-colors"
          >
            <RotateCcw size={13} />
            Deploy Again
          </button>
        </div>
      )}

      {/* ── Working state ── */}
      {status === 'working' && (
        <div ref={workingRef} className="flex flex-col items-center gap-4 py-2 text-center">
          <svg className="animate-spin w-7 h-7 text-blue-400" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8v8z" />
          </svg>
          <p className="text-sm text-gray-300">
            {pairs.length === 0
              ? 'Scanning all available USD markets…'
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
                  <div className="max-h-40 overflow-y-auto pr-1">
                    <div className="flex flex-wrap gap-2">
                      {scanSymbols.map(symbol => (
                        <span
                          key={symbol}
                          className="text-[11px] px-2.5 py-1 rounded-full bg-gray-800/80 text-blue-200 border border-gray-600 font-mono"
                        >
                          {symbol}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="w-full bg-gray-900/50 border border-gray-700 rounded-lg p-3 text-left max-h-80 overflow-y-auto">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold text-gray-300">Markets reviewed</span>
                <span className="text-[11px] text-gray-500">
                  {totalMarkets > pairs.length ? `Showing ${pairs.length} of ${totalMarkets}` : `All ${pairs.length}`}
                </span>
              </div>
              <div className="space-y-2">
                {pairs.map(pair => (
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

      {/* ── Idle state ── */}
      {status === 'idle' && (
        <div className="space-y-5">
          <p className="text-sm text-gray-400">
            Set your risk tolerance and budget, then the system will find the best USD positions and re-evaluate every minute.
          </p>

          {/* Risk slider */}
          <RiskSlider value={riskLevel} onChange={setRiskLevel} />

          {/* Budget input */}
          <div>
            <label className="block text-xs text-gray-500 mb-2">Budget (USD)</label>
            <input
              type="number"
              min={5}
              step={5}
              value={fixedAmount}
              onChange={e => setFixedAmount(e.target.value)}
              className={`w-full bg-gray-700 border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500 ${overBudget ? 'border-red-500' : 'border-gray-600'}`}
              placeholder="100"
            />
            <div className="flex justify-between mt-1.5 text-xs">
              <span className="text-gray-600">Split across up to {levelInfo.maxBots} pair{levelInfo.maxBots !== 1 ? 's' : ''} automatically</span>
              <span className={overBudget ? 'text-red-400' : 'text-gray-500'}>
                ${formatUSD(budget)} / ${formatUSD(usdAvailable)} available
              </span>
            </div>
          </div>

          {/* Info pills */}
          <div className="bg-gray-900/50 rounded-lg p-3 text-xs text-gray-500 space-y-1.5">
            <div className="flex items-start gap-2">
              <BarChart2 className="w-3.5 h-3.5 mt-0.5 shrink-0" />
              <span>Scans all available Bitso USD markets using RSI and trend signals</span>
            </div>
            <div className="flex items-start gap-2">
              <Zap className="w-3.5 h-3.5 mt-0.5 shrink-0" />
              <span>Opens up to {levelInfo.maxBots} position{levelInfo.maxBots !== 1 ? 's' : ''} with {levelInfo.stopLoss} stop-loss, then rechecks every minute</span>
            </div>
          </div>

          {error && (
            <div className="text-xs text-red-400 bg-red-950/40 border border-red-800 rounded-lg px-3 py-2">
              {error}
              {errorIsNetwork && (
                <button
                  onClick={() => handleStart()}
                  className="mt-1.5 flex items-center gap-1 text-red-300 hover:text-red-100 underline underline-offset-2 transition-colors"
                >
                  Try again
                </button>
              )}
            </div>
          )}

          <button
            onClick={() => handleStart()}
            disabled={budget <= 0 || overBudget}
            className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
          >
            <Zap size={14} />
            Start Trading
          </button>
        </div>
      )}
    </div>
  );
}
