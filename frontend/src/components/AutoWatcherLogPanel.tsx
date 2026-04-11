import { useState, useEffect, useCallback } from 'react';
import clsx from 'clsx';
import { RefreshCw, ChevronDown, ChevronRight } from 'lucide-react';
import { getAutoWatcherLogs } from '../api/client';
import type { AutoWatcherLog } from '../types';

const ACTION_LABELS: Record<AutoWatcherLog['action'], string> = {
  deployed: 'Deployed',
  skipped_bots_running: 'Skipped – Bots Running',
  no_eligible_pairs: 'No Eligible Pairs',
  budget_insufficient: 'Budget Insufficient',
  no_symbols: 'No Symbols Available',
  error: 'Error',
};

const ACTION_COLORS: Record<AutoWatcherLog['action'], string> = {
  deployed: 'bg-green-900 text-green-300',
  skipped_bots_running: 'bg-gray-700 text-gray-400',
  no_eligible_pairs: 'bg-yellow-900 text-yellow-300',
  budget_insufficient: 'bg-orange-900 text-orange-300',
  no_symbols: 'bg-gray-700 text-gray-400',
  error: 'bg-red-900 text-red-300',
};

export function AutoWatcherLogPanel() {
  const [logs, setLogs] = useState<AutoWatcherLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const fetchLogs = useCallback(async () => {
    try {
      const data = await getAutoWatcherLogs(0, 50);
      setLogs(data);
      setError(null);
    } catch {
      setError('Failed to load watcher log');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLogs();
    const id = setInterval(fetchLogs, 90_000);
    return () => clearInterval(id);
  }, [fetchLogs]);

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-sm font-semibold text-gray-200">Auto-Watcher Log</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Background scanner checks every 60s — last 50 cycles shown
          </p>
        </div>
        <button
          onClick={fetchLogs}
          className="p-1.5 text-gray-400 hover:text-white hover:bg-gray-700 rounded transition-colors"
          title="Refresh"
        >
          <RefreshCw size={14} />
        </button>
      </div>

      {loading && (
        <div className="text-center text-gray-500 py-8 text-sm">Loading…</div>
      )}

      {error && !loading && (
        <div className="text-center text-red-400 py-8 text-sm">{error}</div>
      )}

      {!loading && !error && logs.length === 0 && (
        <div className="text-center text-gray-500 py-8 text-sm">
          No watcher cycles recorded yet. The first entry appears ~30s after server start.
        </div>
      )}

      {!loading && logs.length > 0 && (
        <div className="space-y-1.5 max-h-[480px] overflow-y-auto pr-1">
          {logs.map(log => {
            const isExpanded = expandedId === log.id;
            const hasDetails = log.details && Object.keys(log.details).length > 0;
            return (
              <div
                key={log.id}
                className="rounded-lg border border-gray-700 bg-gray-900/50 px-3 py-2"
              >
                <div
                  className={clsx(
                    'flex items-center gap-3',
                    hasDetails && 'cursor-pointer'
                  )}
                  onClick={() => hasDetails && setExpandedId(isExpanded ? null : log.id)}
                >
                  {hasDetails ? (
                    isExpanded
                      ? <ChevronDown size={12} className="text-gray-500 shrink-0" />
                      : <ChevronRight size={12} className="text-gray-500 shrink-0" />
                  ) : (
                    <span className="w-3 shrink-0" />
                  )}

                  <span className="font-mono text-xs text-gray-500 whitespace-nowrap shrink-0">
                    {new Date(log.timestamp).toLocaleTimeString()}
                  </span>

                  <span
                    className={clsx(
                      'px-2 py-0.5 rounded text-xs font-semibold shrink-0',
                      ACTION_COLORS[log.action] ?? 'bg-gray-700 text-gray-400'
                    )}
                  >
                    {ACTION_LABELS[log.action] ?? log.action}
                  </span>

                  {log.action === 'deployed' && log.agents_deployed > 0 && (
                    <span className="text-xs text-green-400">
                      {log.agents_deployed} agent{log.agents_deployed !== 1 ? 's' : ''} started
                    </span>
                  )}

                  {log.pairs_evaluated > 0 && (
                    <span className="text-xs text-gray-500 ml-auto shrink-0">
                      {log.pairs_evaluated} pairs scanned
                      {log.eligible_pairs > 0 && `, ${log.eligible_pairs} eligible`}
                    </span>
                  )}
                </div>

                {isExpanded && hasDetails && (
                  <pre className="mt-2 text-[10px] text-gray-400 bg-gray-950/60 rounded p-2 overflow-x-auto whitespace-pre-wrap">
                    {JSON.stringify(log.details, null, 2)}
                  </pre>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
