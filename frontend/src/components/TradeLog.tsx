import { useState } from 'react';
import clsx from 'clsx';
import type { Trade } from '../types';

interface Props {
  trades: Trade[];
}

export function TradeLog({ trades }: Props) {
  const [filterSide, setFilterSide] = useState<'all' | 'buy' | 'sell'>('all');
  const [filterStrategy, setFilterStrategy] = useState('all');

  const strategies = ['all', ...Array.from(new Set(trades.map(t => t.strategy)))];
  const filtered = trades.filter(t => {
    if (filterSide !== 'all' && t.side !== filterSide) return false;
    if (filterStrategy !== 'all' && t.strategy !== filterStrategy) return false;
    return true;
  });

  return (
    <div>
      <div className="flex gap-4 mb-4 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-gray-400 text-sm">Side:</span>
          {(['all', 'buy', 'sell'] as const).map(s => (
            <button
              key={s}
              onClick={() => setFilterSide(s)}
              className={clsx('px-3 py-1 rounded text-sm', {
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
              className={clsx('px-3 py-1 rounded text-sm', {
                'bg-blue-600 text-white': filterStrategy === s,
                'bg-gray-700 text-gray-300 hover:bg-gray-600': filterStrategy !== s,
              })}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 text-left border-b border-gray-700">
              <th className="pb-2 pr-4">Time</th>
              <th className="pb-2 pr-4">Agent</th>
              <th className="pb-2 pr-4">Symbol</th>
              <th className="pb-2 pr-4">Side</th>
              <th className="pb-2 pr-4">Amount</th>
              <th className="pb-2 pr-4">Price</th>
              <th className="pb-2 pr-4">P&amp;L</th>
              <th className="pb-2 pr-4">Mode</th>
              <th className="pb-2">Strategy</th>
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
                  <td className="py-2 pr-4 font-mono text-xs text-gray-300">
                    {new Date(trade.timestamp).toLocaleString()}
                  </td>
                  <td className="py-2 pr-4 font-mono text-xs text-gray-300">{trade.agent_id}</td>
                  <td className="py-2 pr-4 text-gray-200">{trade.symbol}</td>
                  <td className="py-2 pr-4">
                    <span
                      className={clsx('px-2 py-0.5 rounded text-xs font-bold', {
                        'bg-green-800 text-green-300': trade.side === 'buy',
                        'bg-red-800 text-red-300': trade.side === 'sell',
                      })}
                    >
                      {trade.side.toUpperCase()}
                    </span>
                  </td>
                  <td className="py-2 pr-4 font-mono text-gray-300">{trade.amount.toFixed(8)}</td>
                  <td className="py-2 pr-4 font-mono text-gray-300">${trade.price.toFixed(2)}</td>
                  <td
                    className={clsx('py-2 pr-4 font-mono', {
                      'text-green-400': trade.pnl !== null && trade.pnl > 0,
                      'text-red-400': trade.pnl !== null && trade.pnl < 0,
                      'text-gray-500': trade.pnl === null,
                    })}
                  >
                    {trade.pnl !== null ? `$${trade.pnl.toFixed(2)}` : '—'}
                  </td>
                  <td className="py-2 pr-4">
                    <span
                      className={clsx('text-xs px-2 py-0.5 rounded', {
                        'bg-blue-900 text-blue-300': trade.mode === 'paper',
                        'bg-orange-900 text-orange-300': trade.mode === 'live',
                      })}
                    >
                      {trade.mode}
                    </span>
                  </td>
                  <td className="py-2 text-xs text-gray-400">{trade.strategy}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
