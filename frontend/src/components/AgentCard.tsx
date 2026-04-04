import { useState, useEffect } from 'react';
import { Play, Square, Skull, ChevronDown, ChevronUp, Trash2 } from 'lucide-react';
import clsx from 'clsx';
import type { Agent, AgentLog } from '../types';
import { BudgetGauge } from './BudgetGauge';
import { startAgent, stopAgent, killAgent, deleteAgent, getAgentLogs } from '../api/client';

interface Props {
  agent: Agent;
  onUpdate: () => void;
}

export function AgentCard({ agent, onUpdate }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [logs, setLogs] = useState<AgentLog[]>([]);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const statusColors: Record<string, string> = {
    running: 'bg-green-500',
    stopped: 'bg-yellow-500',
    killed: 'bg-red-500',
  };

  const handleAction = async (fn: () => Promise<unknown>, label: string) => {
    setError(null);
    setLoading(true);
    try {
      await fn();
      onUpdate();
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (e instanceof Error ? e.message : String(e));
      setError(`${label} failed: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  const handleStart = () => handleAction(() => startAgent(agent.agent_id), 'Start');
  const handleStop = () => handleAction(() => stopAgent(agent.agent_id), 'Stop');
  const handleKill = () => handleAction(() => killAgent(agent.agent_id), 'Kill');
  const handleDelete = () => handleAction(() => deleteAgent(agent.agent_id), 'Delete');

  const toggleExpand = async () => {
    const opening = !expanded;
    if (opening && logs.length === 0) {
      setLoadingLogs(true);
      try {
        const data = await getAgentLogs(agent.agent_id);
        setLogs(data);
      } catch {
        // ignore log fetch errors
      } finally {
        setLoadingLogs(false);
      }
    }
    setExpanded(opening);
  };

  // Auto-refresh logs every 15s when expanded and running
  useEffect(() => {
    if (!expanded || agent.status !== 'running') return;
    const id = setInterval(async () => {
      try {
        const data = await getAgentLogs(agent.agent_id);
        setLogs(data);
      } catch { /* ignore */ }
    }, 15000);
    return () => clearInterval(id);
  }, [expanded, agent.status, agent.agent_id]);

  const remainingBudget = agent.budget_allocated - agent.budget_used;

  return (
    <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={clsx('w-2 h-2 rounded-full', statusColors[agent.status])} />
          <span className="font-mono text-sm text-gray-300">{agent.agent_id}</span>
          <span className="text-xs bg-gray-700 px-2 py-0.5 rounded text-gray-300">
            {agent.strategy}
          </span>
          <span className="text-xs bg-blue-900 text-blue-300 px-2 py-0.5 rounded font-mono">
            {agent.symbol}
          </span>
          <span className={clsx('text-xs px-2 py-0.5 rounded font-medium', {
            'bg-green-900 text-green-300': agent.status === 'running',
            'bg-yellow-900 text-yellow-300': agent.status === 'stopped',
            'bg-red-900 text-red-300': agent.status === 'killed',
          })}>
            {agent.status}
          </span>
        </div>
        <div className="flex items-center gap-1">
          {agent.status !== 'killed' && agent.status !== 'running' && (
            <button
              onClick={handleStart}
              disabled={loading}
              className="p-1.5 rounded bg-green-700 hover:bg-green-600 text-white disabled:opacity-50"
              title="Start agent"
            >
              <Play size={14} />
            </button>
          )}
          {agent.status === 'running' && (
            <button
              onClick={handleStop}
              disabled={loading}
              className="p-1.5 rounded bg-yellow-700 hover:bg-yellow-600 text-white disabled:opacity-50"
              title="Stop agent"
            >
              <Square size={14} />
            </button>
          )}
          {agent.status !== 'killed' && (
            <button
              onClick={handleKill}
              disabled={loading}
              className="p-1.5 rounded bg-red-700 hover:bg-red-600 text-white disabled:opacity-50"
              title="Kill agent permanently"
            >
              <Skull size={14} />
            </button>
          )}
          {(agent.status === 'killed' || agent.status === 'stopped') && (
            <button
              onClick={handleDelete}
              disabled={loading}
              className="p-1.5 rounded bg-gray-600 hover:bg-red-700 text-gray-400 hover:text-white disabled:opacity-50"
              title="Delete agent"
            >
              <Trash2 size={14} />
            </button>
          )}
          <button
            onClick={toggleExpand}
            className="p-1.5 rounded bg-gray-700 hover:bg-gray-600 text-gray-300"
          >
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-2 text-xs text-red-400 bg-red-900/30 border border-red-800 rounded px-2 py-1">
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 text-sm mb-2">
        <div>
          <div className="text-gray-400 text-xs">Trades Today</div>
          <div className="text-white font-mono">{agent.trades_today}</div>
        </div>
        <div>
          <div className="text-gray-400 text-xs">Remaining Budget</div>
          <div className="text-white font-mono">${remainingBudget.toFixed(2)}</div>
        </div>
      </div>

      {agent.status === 'running' && (
        <div className="flex items-center justify-between text-xs mb-2 bg-gray-900 rounded px-2 py-1.5">
          <div className="flex items-center gap-2">
            <span className="text-gray-400">Last signal:</span>
            {agent.last_signal ? (
              <span className={clsx('font-bold uppercase', {
                'text-green-400': agent.last_signal === 'buy',
                'text-red-400': agent.last_signal === 'sell',
                'text-gray-400': agent.last_signal === 'hold',
              })}>
                {agent.last_signal}
              </span>
            ) : (
              <span className="text-gray-500 animate-pulse">analyzing…</span>
            )}
          </div>
          <div className="text-gray-500">
            {agent.last_tick_at
              ? `${Math.round((Date.now() - new Date(agent.last_tick_at).getTime()) / 1000)}s ago`
              : 'first tick pending…'}
          </div>
        </div>
      )}

      <BudgetGauge allocated={agent.budget_allocated} used={agent.budget_used} />

      {expanded && (
        <div className="mt-4 border-t border-gray-700 pt-3">
          <div className="text-xs text-gray-400 mb-2">Recent Logs</div>
          {loadingLogs ? (
            <div className="text-gray-500 text-xs">Loading...</div>
          ) : logs.length === 0 ? (
            <div className="text-gray-500 text-xs">No logs yet. Start the agent to see activity.</div>
          ) : (
            <div className="space-y-1 max-h-40 overflow-y-auto">
              {logs.map(log => (
                <div key={log.id} className="text-xs font-mono">
                  <span
                    className={clsx('mr-2', {
                      'text-blue-400': log.level === 'info',
                      'text-yellow-400': log.level === 'warning',
                      'text-red-400': log.level === 'error',
                      'text-green-400': log.level === 'trade',
                    })}
                  >
                    [{log.level.toUpperCase()}]
                  </span>
                  <span className="text-gray-300">{log.message}</span>
                  {log.reasoning && (
                    <span className="text-gray-500 ml-1">— {log.reasoning}</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
