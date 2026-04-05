import { useState, useEffect, useCallback } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  RadialBarChart,
  RadialBar,
} from 'recharts';
import { RefreshCw, TrendingUp, TrendingDown, AlertTriangle, CheckCircle, Clock } from 'lucide-react';
import type { BacktestResult } from '../types';
import {
  getStrategyReasoning,
  getMarketScan,
  runBacktest,
  type BotReasoning,
  type PairScan,
} from '../api/client';

// ── Helpers ─────────────────────────────────────────────────────────────────

function fmt(n: number | null | undefined, prefix = '$'): string {
  if (n == null) return '—';
  return `${prefix}${n.toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function urgencyColor(urgency: string) {
  if (urgency === 'high') return 'text-amber-400';
  if (urgency === 'medium') return 'text-blue-400';
  return 'text-gray-400';
}

function actionIcon(action: string) {
  if (action === 'BUY SIGNAL') return <TrendingUp size={14} className="text-green-400" />;
  if (action === 'SELL SIGNAL') return <TrendingDown size={14} className="text-red-400" />;
  if (action === 'HOLDING') return <CheckCircle size={14} className="text-blue-400" />;
  return <Clock size={14} className="text-gray-400" />;
}

function actionBadge(action: string) {
  const base = 'text-xs font-semibold px-2 py-0.5 rounded-full';
  if (action === 'BUY SIGNAL') return `${base} bg-green-900/50 text-green-300`;
  if (action === 'SELL SIGNAL') return `${base} bg-red-900/50 text-red-300`;
  if (action === 'HOLDING') return `${base} bg-blue-900/50 text-blue-300`;
  return `${base} bg-gray-800 text-gray-400`;
}

// ── RSI Gauge ────────────────────────────────────────────────────────────────

function RSIGauge({ rsi, oversold = 30, overbought = 70 }: { rsi: number; oversold?: number; overbought?: number }) {
  const fill = rsi < oversold ? '#22c55e' : rsi > overbought ? '#ef4444' : '#3b82f6';
  const data = [{ name: 'RSI', value: rsi, fill }];

  return (
    <div className="flex flex-col items-center">
      <div className="relative w-24 h-14 overflow-hidden">
        <RadialBarChart
          width={96}
          height={96}
          cx={48}
          cy={80}
          innerRadius={50}
          outerRadius={80}
          barSize={10}
          data={data}
          startAngle={180}
          endAngle={0}
        >
          <RadialBar dataKey="value" cornerRadius={4} maxBarSize={10} background={{ fill: '#374151' }} />
        </RadialBarChart>
      </div>
      <div className="text-center -mt-1">
        <span className="text-xl font-bold" style={{ color: fill }}>{rsi}</span>
        <span className="text-xs text-gray-400 ml-1">RSI</span>
      </div>
      <div className="text-xs text-gray-500 mt-1">
        {rsi < oversold ? 'Oversold' : rsi > overbought ? 'Overbought' : 'Neutral'}
      </div>
    </div>
  );
}

// ── Bot Reasoning Card ───────────────────────────────────────────────────────

function BotReasoningCard({ bot }: { bot: BotReasoning }) {
  if (bot.error) {
    return (
      <div className="bg-gray-800 border border-red-800 rounded-lg p-4">
        <div className="text-sm font-semibold text-white">{bot.symbol}</div>
        <div className="text-xs text-red-400 mt-1">{bot.error}</div>
      </div>
    );
  }

  const r = bot.reasoning;
  const pnlColor = (bot.unrealized_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400';

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <span className="text-sm font-bold text-white">{bot.symbol}</span>
          <span className="ml-2 text-xs text-gray-400 uppercase">{bot.strategy}</span>
        </div>
        <span className={actionBadge(r.action)}>{r.action}</span>
      </div>

      {/* Indicators */}
      <div className="flex gap-4 items-center">
        {r.rsi != null && (
          <RSIGauge rsi={r.rsi} oversold={r.oversold} overbought={r.overbought} />
        )}
        {r.fast_ma != null && (
          <div className="flex-1 space-y-1">
            <div className="text-xs text-gray-400">Fast MA</div>
            <div className="text-sm font-semibold text-white">{fmt(r.fast_ma)}</div>
            <div className="text-xs text-gray-400 mt-2">Slow MA</div>
            <div className="text-sm font-semibold text-white">{fmt(r.slow_ma)}</div>
            <div className={`text-xs font-medium mt-1 ${r.bullish ? 'text-green-400' : 'text-red-400'}`}>
              {r.bullish ? '▲ Bullish' : '▼ Bearish'} ({r.spread_pct?.toFixed(2)}% spread)
            </div>
          </div>
        )}
        {/* Position info */}
        {bot.has_position && (
          <div className="flex-1 border border-gray-700 rounded p-2 space-y-1">
            <div className="text-xs text-gray-400">Entry</div>
            <div className="text-sm font-semibold text-white">{fmt(bot.entry_price)}</div>
            <div className="text-xs text-gray-400 mt-1">Unrealized P&L</div>
            <div className={`text-sm font-semibold ${pnlColor}`}>{fmt(bot.unrealized_pnl)}</div>
            <div className="text-xs text-gray-400 mt-1">Stop-loss</div>
            <div className="text-sm text-red-400">{fmt(bot.stop_loss_price)}</div>
          </div>
        )}
      </div>

      {/* Trigger reasoning */}
      <div className={`flex items-start gap-2 text-xs ${urgencyColor(r.urgency)}`}>
        {actionIcon(r.action)}
        <span>{r.trigger}</span>
      </div>

      {/* RSI progress bar */}
      {r.rsi != null && (
        <div>
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>{r.oversold} (Buy)</span>
            <span>RSI {r.rsi}</span>
            <span>{r.overbought} (Sell)</span>
          </div>
          <div className="relative h-1.5 bg-gray-700 rounded-full">
            <div
              className="absolute inset-y-0 left-0 rounded-full"
              style={{
                width: `${Math.min(100, r.rsi)}%`,
                backgroundColor: r.rsi < (r.oversold ?? 30) ? '#22c55e' : r.rsi > (r.overbought ?? 70) ? '#ef4444' : '#3b82f6',
              }}
            />
            {/* Oversold/overbought markers */}
            <div className="absolute inset-y-0" style={{ left: `${r.oversold}%`, width: 1, backgroundColor: '#22c55e80' }} />
            <div className="absolute inset-y-0" style={{ left: `${r.overbought}%`, width: 1, backgroundColor: '#ef444480' }} />
          </div>
          {bot.has_position && r.distance_to_sell != null && (
            <div className="text-xs text-gray-500 mt-1">
              Sell trigger in <span className="text-amber-400">+{r.distance_to_sell} RSI points</span>
            </div>
          )}
          {!bot.has_position && r.distance_to_buy != null && r.distance_to_buy > 0 && (
            <div className="text-xs text-gray-500 mt-1">
              Buy trigger in <span className="text-green-400">-{r.distance_to_buy} RSI points</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Market Scanner ───────────────────────────────────────────────────────────

function MarketScanner({ pairs, loading }: { pairs: PairScan[]; loading: boolean }) {
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-white">Market Scanner</h3>
        <span className="text-xs text-gray-400">Opportunity score 0-100</span>
      </div>
      {loading ? (
        <div className="text-xs text-gray-500 py-4 text-center">Scanning pairs…</div>
      ) : (
        <div className="space-y-2">
          {pairs.map((p, i) => (
            <div key={p.symbol} className="flex items-center gap-3">
              <span className="text-xs text-gray-500 w-4">{i + 1}</span>
              <span className="text-xs font-semibold text-white w-20">{p.symbol.replace('/MXN', '')}</span>
              {/* Score bar */}
              <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${p.score}%`,
                    backgroundColor: p.score > 60 ? '#22c55e' : p.score > 30 ? '#f59e0b' : '#6b7280',
                  }}
                />
              </div>
              <span className="text-xs text-gray-400 w-8 text-right">{p.score.toFixed(0)}</span>
              {/* RSI chip */}
              <span
                className={`text-xs px-1.5 py-0.5 rounded font-mono ${
                  p.rsi < 30 ? 'bg-green-900/50 text-green-300' :
                  p.rsi > 70 ? 'bg-red-900/50 text-red-300' : 'bg-gray-700 text-gray-300'
                }`}
              >
                {p.rsi.toFixed(0)}
              </span>
              <span className="text-xs text-gray-500 w-28 text-right">{fmt(p.price)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Backtest Section ─────────────────────────────────────────────────────────

function BacktestSection() {
  const [strategy, setStrategy] = useState('rsi');
  const [symbol, setSymbol] = useState('BTC/MXN');
  const [timeframe, setTimeframe] = useState('1h');
  const [startDate, setStartDate] = useState('2024-01-01');
  const [endDate, setEndDate] = useState('2024-06-01');
  const [capital, setCapital] = useState(10000);
  const [fastPeriod, setFastPeriod] = useState(9);
  const [slowPeriod, setSlowPeriod] = useState(21);
  const [rsiPeriod, setRsiPeriod] = useState(14);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    const params: Record<string, number> =
      strategy === 'ma_crossover'
        ? { fast_period: fastPeriod, slow_period: slowPeriod }
        : { period: rsiPeriod };

    try {
      const data = await runBacktest({ strategy, params, symbol, timeframe, start_date: startDate, end_date: endDate, initial_capital: capital });
      if (data.error) setError(data.error);
      else setResult(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Backtest failed');
    } finally {
      setLoading(false);
    }
  };

  const equityData =
    result?.equity_curve.map(([ts, val]) => ({
      time: new Date(ts).toLocaleDateString('es-MX'),
      equity: parseFloat(val.toFixed(2)),
    })) ?? [];

  return (
    <div className="space-y-4">
      <form onSubmit={handleSubmit} className="bg-gray-800 border border-gray-700 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-white mb-3">Historical Backtest</h3>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Strategy</label>
            <select value={strategy} onChange={e => setStrategy(e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-white text-xs">
              <option value="rsi">RSI</option>
              <option value="ma_crossover">MA Crossover</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Symbol</label>
            <select value={symbol} onChange={e => setSymbol(e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-white text-xs">
              {['BTC/MXN','ETH/MXN','SOL/MXN','XRP/MXN','AVAX/MXN','LTC/MXN'].map(s => <option key={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Timeframe</label>
            <select value={timeframe} onChange={e => setTimeframe(e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-white text-xs">
              <option value="1h">1h</option><option value="4h">4h</option><option value="1d">1d</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Start Date</label>
            <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-white text-xs" />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">End Date</label>
            <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-white text-xs" />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Capital ($MXN)</label>
            <input type="number" value={capital} onChange={e => setCapital(Number(e.target.value))}
              className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-white text-xs" />
          </div>
          {strategy === 'ma_crossover' && <>
            <div><label className="block text-xs text-gray-400 mb-1">Fast Period</label>
              <input type="number" value={fastPeriod} onChange={e => setFastPeriod(Number(e.target.value))}
                className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-white text-xs" /></div>
            <div><label className="block text-xs text-gray-400 mb-1">Slow Period</label>
              <input type="number" value={slowPeriod} onChange={e => setSlowPeriod(Number(e.target.value))}
                className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-white text-xs" /></div>
          </>}
          {strategy === 'rsi' && <div><label className="block text-xs text-gray-400 mb-1">RSI Period</label>
            <input type="number" value={rsiPeriod} onChange={e => setRsiPeriod(Number(e.target.value))}
              className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-white text-xs" /></div>}
        </div>
        <button type="submit" disabled={loading}
          className="mt-3 px-5 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-600 text-white rounded text-xs font-medium">
          {loading ? 'Running…' : 'Run Backtest'}
        </button>
      </form>

      {error && <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 text-red-300 text-xs">{error}</div>}

      {result && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {[
              { label: 'Total Return', value: `${result.total_return_pct > 0 ? '+' : ''}${result.total_return_pct}%`, positive: result.total_return_pct > 0 },
              { label: 'Win Rate', value: `${result.win_rate}%`, positive: result.win_rate > 50 },
              { label: 'Total Trades', value: String(result.total_trades), positive: true },
              { label: 'Max Drawdown', value: `${result.max_drawdown_pct}%`, positive: false },
              { label: 'Sharpe Ratio', value: String(result.sharpe_ratio), positive: result.sharpe_ratio > 1 },
            ].map(stat => (
              <div key={stat.label} className="bg-gray-800 border border-gray-700 rounded p-3">
                <div className="text-xs text-gray-400 mb-1">{stat.label}</div>
                <div className={`text-lg font-bold ${stat.positive ? 'text-green-400' : 'text-red-400'}`}>{stat.value}</div>
              </div>
            ))}
          </div>
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
            <h4 className="text-xs font-medium text-gray-300 mb-3">Equity Curve</h4>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={equityData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="time" tick={{ fill: '#9CA3AF', fontSize: 10 }} />
                <YAxis tick={{ fill: '#9CA3AF', fontSize: 10 }} />
                <Tooltip contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151', borderRadius: '6px' }}
                  labelStyle={{ color: '#9CA3AF' }} />
                <Line type="monotone" dataKey="equity" stroke="#3B82F6" strokeWidth={2} dot={false} name="Equity ($MXN)" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main StrategyPanel ───────────────────────────────────────────────────────

export function BacktestPanel() {
  const [bots, setBots] = useState<BotReasoning[]>([]);
  const [pairs, setPairs] = useState<PairScan[]>([]);
  const [loadingBots, setLoadingBots] = useState(false);
  const [loadingPairs, setLoadingPairs] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [tab, setTab] = useState<'intelligence' | 'backtest'>('intelligence');

  const refresh = useCallback(async () => {
    setLoadingBots(true);
    setLoadingPairs(true);
    try {
      const [botsRes, pairsRes] = await Promise.all([getStrategyReasoning(), getMarketScan()]);
      setBots(botsRes.bots);
      setPairs(pairsRes.pairs);
      setLastUpdated(new Date());
    } catch {
      // silent
    } finally {
      setLoadingBots(false);
      setLoadingPairs(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 30_000);
    return () => clearInterval(interval);
  }, [refresh]);

  return (
    <div className="space-y-4">
      {/* Sub-tab switcher */}
      <div className="flex gap-2 border-b border-gray-700 pb-2">
        <button
          onClick={() => setTab('intelligence')}
          className={`text-sm px-4 py-1.5 rounded-t font-medium transition-colors ${tab === 'intelligence' ? 'bg-gray-700 text-white' : 'text-gray-400 hover:text-white'}`}
        >
          Live Intelligence
        </button>
        <button
          onClick={() => setTab('backtest')}
          className={`text-sm px-4 py-1.5 rounded-t font-medium transition-colors ${tab === 'backtest' ? 'bg-gray-700 text-white' : 'text-gray-400 hover:text-white'}`}
        >
          Historical Backtest
        </button>
        {tab === 'intelligence' && (
          <div className="ml-auto flex items-center gap-2">
            {lastUpdated && (
              <span className="text-xs text-gray-500">
                Updated {lastUpdated.toLocaleTimeString()}
              </span>
            )}
            <button
              onClick={refresh}
              disabled={loadingBots}
              className="p-1.5 rounded text-gray-400 hover:text-white hover:bg-gray-700 transition-colors"
            >
              <RefreshCw size={14} className={loadingBots ? 'animate-spin' : ''} />
            </button>
          </div>
        )}
      </div>

      {tab === 'intelligence' && (
        <div className="space-y-4">
          {/* Active Bot Reasoning */}
          <div>
            <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
              <TrendingUp size={14} className="text-blue-400" />
              Bot Reasoning
            </h3>
            {loadingBots ? (
              <div className="text-xs text-gray-500 py-6 text-center">Loading bot analysis…</div>
            ) : bots.length === 0 ? (
              <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 text-center">
                <AlertTriangle size={20} className="mx-auto text-gray-600 mb-2" />
                <p className="text-sm text-gray-400">No active bots to analyze.</p>
                <p className="text-xs text-gray-500 mt-1">Start an Auto Trade bot to see live reasoning here.</p>
              </div>
            ) : (
              <div className="grid gap-3 md:grid-cols-2">
                {bots.map(bot => <BotReasoningCard key={bot.agent_id} bot={bot} />)}
              </div>
            )}
          </div>

          {/* Market Scanner */}
          <MarketScanner pairs={pairs} loading={loadingPairs} />

          {/* Legend */}
          <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-3">
            <h4 className="text-xs font-semibold text-gray-400 mb-2">How to read this</h4>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs text-gray-500">
              <div><span className="text-green-400 font-medium">RSI &lt; 30</span> — Oversold, bot may buy</div>
              <div><span className="text-red-400 font-medium">RSI &gt; 70</span> — Overbought, bot may sell</div>
              <div><span className="text-blue-400 font-medium">HOLDING</span> — Position open, watching sell target</div>
              <div><span className="text-amber-400 font-medium">WAITING</span> — No position, watching buy signal</div>
              <div><span className="text-gray-300 font-medium">Stop-loss</span> — Auto-sell at loss threshold</div>
              <div><span className="text-gray-300 font-medium">Opportunity score</span> — How favourable the pair looks (0-100)</div>
            </div>
          </div>
        </div>
      )}

      {tab === 'backtest' && <BacktestSection />}
    </div>
  );
}
