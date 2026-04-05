import { useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { killAllAgents } from '../api/client';

interface Props {
  hasRunningAgents: boolean;
  onKilled: () => void;
}

export function KillSwitch({ hasRunningAgents, onKilled }: Props) {
  const [confirming, setConfirming] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleClick = () => {
    if (!confirming) {
      setConfirming(true);
      return;
    }
    setLoading(true);
    killAllAgents()
      .then(() => {
        onKilled();
        setConfirming(false);
      })
      .finally(() => setLoading(false));
  };

  return (
    <div className="flex items-center gap-2">
      {confirming && (
        <span className="text-yellow-400 text-sm">Are you sure?</span>
      )}
      <button
        onClick={handleClick}
        disabled={!hasRunningAgents || loading}
        className={`flex items-center gap-2 text-sm px-3 py-1.5 rounded border transition-colors ${
          hasRunningAgents
            ? confirming
              ? 'border-red-600 text-red-300 bg-red-900/40 hover:bg-red-900/60'
              : 'border-red-700 text-red-400 hover:bg-red-900/40'
            : 'border-gray-700 text-gray-600 cursor-not-allowed'
        }`}
      >
        <AlertTriangle size={16} />
        {loading ? 'Killing...' : confirming ? 'CONFIRM KILL ALL' : 'KILL ALL AGENTS'}
      </button>
      {confirming && (
        <button
          onClick={() => setConfirming(false)}
          className="text-gray-400 text-sm hover:text-white"
        >
          Cancel
        </button>
      )}
    </div>
  );
}
