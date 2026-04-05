import { useState, useEffect, useCallback } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import axios from 'axios';

interface PriceTick {
  last: number;
  change_pct: number;
  high: number;
  low: number;
}

interface OhlcvCandle {
  time: string;
  close: number;
}

const COINS = ['BTC', 'ETH', 'SOL', 'XRP', 'AVAX', 'LTC'];
const SYMBOLS = COINS.map(c => `${c}/MXN`);

function fmt(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `$${n.toLocaleString('es-MX', { maximumFractionDigits: 0 })}`;
  return `$${n.toFixed(4)}`;
}

export function PriceBoard() {
  const [prices, setPrices] = useState<Record<string, PriceTick>>({});
  const [selected, setSelected] = useState('BTC/MXN');
  const [ohlcv, setOhlcv] = useState<OhlcvCandle[]>([]);
  const [loadingChart, setLoadingChart] = useState(false);

  const fetchPrices = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/prices');
      setPrices(data.prices ?? {});
    } catch {
      // keep stale data
    }
  }, []);

  const fetchOhlcv = useCallback(async (symbol: string) => {
    setLoadingChart(true);
    try {
      const slug = symbol.replace('/', '-');
      const { data } = await axios.get(`/api/prices/${slug}/ohlcv`, {
        params: { timeframe: '1h', limit: 50 },
      });
      const candles: OhlcvCandle[] = (data.data ?? []).map(
        ([ts, , , , close]: [number, number, number, number, number]) => ({
          time: new Date(ts).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' }),
          close,
        })
      );
      setOhlcv(candles);
    } catch {
      setOhlcv([]);
    } finally {
      setLoadingChart(false);
    }
  }, []);

  useEffect(() => {
    fetchPrices();
    const id = setInterval(fetchPrices, 30_000);
    return () => clearInterval(id);
  }, [fetchPrices]);

  useEffect(() => {
    fetchOhlcv(selected);
  }, [selected, fetchOhlcv]);

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-4 space-y-3">
      {/* Compact horizontal ticker strip */}
      <div className="flex gap-2 overflow-x-auto pb-1">
        {SYMBOLS.map(sym => {
          const tick = prices[sym];
          const up = (tick?.change_pct ?? 0) >= 0;
          const active = sym === selected;
          return (
            <button
              key={sym}
              onClick={() => setSelected(sym)}
              className={`flex items-center gap-3 px-3 py-2 rounded border shrink-0 transition-colors ${
                active
                  ? 'border-blue-500 bg-gray-700'
                  : 'border-gray-700 hover:border-gray-600 hover:bg-gray-750'
              }`}
            >
              <span className="text-xs font-semibold text-gray-300 w-8">{sym.split('/')[0]}</span>
              <span className="text-sm font-medium text-white">{tick ? fmt(tick.last) : '—'}</span>
              <span className={`text-xs font-medium ${up ? 'text-green-400' : 'text-red-400'}`}>
                {tick ? `${up ? '+' : ''}${tick.change_pct.toFixed(2)}%` : '—'}
              </span>
            </button>
          );
        })}
      </div>

      {/* OHLCV chart */}
      <div>
        <div className="text-xs text-gray-400 font-medium uppercase tracking-wide mb-2">
          {selected} · 1h candles (close)
        </div>
        {loadingChart ? (
          <div className="h-36 flex items-center justify-center text-gray-500 text-sm">
            Loading…
          </div>
        ) : ohlcv.length === 0 ? (
          <div className="h-36 flex items-center justify-center text-gray-500 text-sm">
            No data
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={140}>
            <LineChart data={ohlcv} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
              <XAxis
                dataKey="time"
                tick={{ fontSize: 10, fill: '#9ca3af' }}
                interval="preserveStartEnd"
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                domain={['auto', 'auto']}
                tick={{ fontSize: 10, fill: '#9ca3af' }}
                tickLine={false}
                axisLine={false}
                width={60}
                tickFormatter={v => fmt(v)}
              />
              <Tooltip
                contentStyle={{ background: '#1f2937', border: '1px solid #374151', fontSize: 12 }}
                formatter={(v: number) => [fmt(v), 'Close']}
              />
              <Line
                type="monotone"
                dataKey="close"
                stroke="#3b82f6"
                dot={false}
                strokeWidth={1.5}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
