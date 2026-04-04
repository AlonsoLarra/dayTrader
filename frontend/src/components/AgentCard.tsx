import { useState } from 'react';
import { Play, Square, Skull, ChevronDown, ChevronUp } from 'lucide-react';
import clsx from 'clsx';
import type { Agent, AgentLog } from '../types';
import { BudgetGauge } from './BudgetGauge';
import { startAgent, stopAgent, killAgent, getAgentLogs } from '../api/client';

interface Props {
  agent: Agent;
  onUpdate: () => void;
}

export function AgentCard({ agent, onUpdate }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [logs, setLogs] = useState<AgentLog[]>([]);
  const [loadingLogs, setLoadingLogs] = useState(false);

  const statusColors: Record<string, string> = {
    running: 'bg-green-500',
    stopped: 'bg-yellow-500',
    killed: 'bg-red-500',
  };

  const handleStart = async () => {
    await startAgent(agent.agent_id);
    onUpdate();
  };

  const handleStop = async () => {
    await stopAgent(agent.agent_id);
    onUpdate();
  };

  const handleKill = async () => {
    await killAgent(agent.agent_id);
    onUpdate();
  };

  const toggleExpand = async () => {
    if (!expanded && logs.length === 0) {
      setLoadingLogs(true);
      const data = await getAgentLogs(agent.agent_id);
      setLogs(data);
      setLoadingLogs(false);
    }
    setExpanded(!expanded);
  };

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
        </div>
        <div className="flex items-center gap-1">
          {agent.status !== 'killed' && agent.status !== 'running' && (
            <button
              onClick={handleStart}
              className="p-1.5 rounded bg-green-700 hover:bg-green-600 text-white"
              title="Start"
            >
              <Play size={14} />
            </button>
          )}
          {agent.status === 'running' && (
            <button
              onClick={handleStop}
              className="p-1.5 rounded bg-yellow-700 hover:bg-yellow-600 text-white"
              title="Stop"
            >
              <Square size={14} />
            </button>
          )}
          {agent.status !== 'killed' && (
            <button
              onClick={handleKill}
              className="p-1.5 rounded bg-red-700 hover:bg-red-600 text-white"
              title="Kill"
            >
              <Skull size={14} />
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

      <BudgetGauge allocated={agent.budget_allocated} used={agent.budget_used} />

      {expanded && (
        <div className="mt-4 border-t border-gray-700 pt-3">
          <div className="text-xs text-gray-400 mb-2">Recent Logs</div>
          {loadingLogs ? (
            <div className="text-gray-500 text-xs">Loading...</div>
          ) : logs.length === 0 ? (
            <div className="text-gray-500 text-xs">No logs yet</div>
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
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
