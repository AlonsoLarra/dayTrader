import { useState } from 'react';
import { Download } from 'lucide-react';
import clsx from 'clsx';
import type { Trade } from '../types';
import { exportTrades } from '../api/client';

interface Props {
  trades: Trade[];
}

export function TradeLog({ trades }: Props) {
  const [filterSide, setFilterSide] = useState<'all' | 'buy' | 'sell'>('all');
  const [filterStrategy, setFilterStrategy] = useState('all');
  const [exporting, setExporting] = useState(false);

  const strategies = ['all', ...Array.from(new Set(trades.map(t => t.strategy)))];
  const filtered = trades.filter(t => {
    if (filterSide !== 'all' && t.side !== filterSide) return false;
    if (filterStrategy !== 'all' && t.strategy !== filterStrategy) return false;
    return true;
  });

  async function handleExport() {
    setExporting(true);
    try {
      const blob = await exportTrades(30);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `daytrader_export_${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 100);
    } catch {
      /* ignore */
    } finally {
      setExporting(false);
    }
  }

  return (
    <div>
      <div className="flex gap-4 mb-4 flex-wrap items-center">
        <div className="flex items-center gap-2">
          <span className="text-gray-400 text-sm">Side:</span>
          {(['all', 'buy', 'sell'] as const).map(s => (
            <button
              key={s}
              onClick={() => setFilterSide(s)}
              className={clsx('px-3 py-2 min-h-[40px] rounded text-sm', {
                'bg-blue-600 text-white': filterSide === s,
                'bg-gray-700 text-gray-300 hover:bg-gray-600': filterSide !== s,
              })}
            >
              {s}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-gray-400 text-sm">Strategy:</span>
          {strategies.map(s => (
            <button
              key={s}
              onClick={() => setFilterStrategy(s)}
              className={clsx('px-3 py-2 min-h-[40px] rounded text-sm', {
                'bg-blue-600 text-white': filterStrategy === s,
                'bg-gray-700 text-gray-300 hover:bg-gray-600': filterStrategy !== s,
              })}
            >
              {s}
            </button>
          ))}
        </div>
        <button
          onClick={handleExport}
          disabled={exporting || trades.length === 0}
          className="ml-auto flex items-center gap-1.5 px-3 py-2 min-h-[40px] bg-gray-700 hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed text-gray-300 text-sm rounded transition-colors"
          title="Export trades as JSON for LLM analysis"
        >
          <Download size={13} />
          {exporting ? 'Exporting…' : 'Export Log'}
        </button>
      </div>

      <div className="overflow-x-auto -mx-4 px-4 md:mx-0 md:px-0">
        <table className="text-sm min-w-[600px] w-full">
          <thead>
            <tr className="text-gray-400 text-left border-b border-gray-700">
              <th className="pb-2 pr-4">Time</th>
              <th className="pb-2 pr-4 hidden sm:table-cell">Agent</th>
              <th className="pb-2 pr-4">Symbol</th>
              <th className="pb-2 pr-4">Side</th>
              <th className="pb-2 pr-4 hidden sm:table-cell">Amount</th>
              <th className="pb-2 pr-4">Price</th>
              <th className="pb-2 pr-4">P&amp;L</th>
              <th className="pb-2 pr-4 hidden md:table-cell">Mode</th>
              <th className="pb-2 hidden md:table-cell">Strategy</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={9} className="text-center text-gray-500 py-8">
                  No trades found
                </td>
              </tr>
            ) : (
              filtered.map(trade => (
                <tr
                  key={trade.id}
                  className={clsx('border-b border-gray-800 hover:bg-gray-800/50', {
                    'bg-green-900/10': trade.pnl !== null && trade.pnl > 0,
                    'bg-red-900/10': trade.pnl !== null && trade.pnl < 0,
                  })}
                >
                  <td className="py-2.5 pr-4 font-mono text-xs text-gray-300 whitespace-nowrap">
                    {new Date(trade.timestamp).toLocaleString()}
                  </td>
                  <td className="py-2.5 pr-4 font-mono text-xs text-gray-300 hidden sm:table-cell">{trade.agent_id}</td>
                  <td className="py-2.5 pr-4 text-gray-200 whitespace-nowrap">{trade.symbol}</td>
                  <td className="py-2.5 pr-4">
                    <span
                      className={clsx('px-2 py-0.5 rounded text-xs font-bold', {
                        'bg-green-800 text-green-300': trade.side === 'buy',
                        'bg-red-800 text-red-300': trade.side === 'sell',
                      })}
                    >
                      {trade.side.toUpperCase()}
                    </span>
                  </td>
                  <td className="py-2.5 pr-4 font-mono text-gray-300 hidden sm:table-cell">{trade.amount.toFixed(8)}</td>
                  <td className="py-2.5 pr-4 font-mono text-gray-300 whitespace-nowrap">${trade.price.toFixed(2)}</td>
                  <td
                    className={clsx('py-2.5 pr-4 font-mono whitespace-nowrap', {
                      'text-green-400': trade.pnl !== null && trade.pnl > 0,
                      'text-red-400': trade.pnl !== null && trade.pnl < 0,
                      'text-gray-500': trade.pnl === null,
                    })}
                  >
                    {trade.pnl !== null ? `$${trade.pnl.toFixed(2)}` : '—'}
                  </td>
                  <td className="py-2.5 pr-4 hidden md:table-cell">
                    <span
                      className={clsx('text-xs px-2 py-0.5 rounded', {
                        'bg-blue-900 text-blue-300': trade.mode === 'paper',
                        'bg-orange-900 text-orange-300': trade.mode === 'live',
                      })}
                    >
                      {trade.mode}
                    </span>
                  </td>
                  <td className="py-2.5 text-xs text-gray-400 hidden md:table-cell">{trade.strategy}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
