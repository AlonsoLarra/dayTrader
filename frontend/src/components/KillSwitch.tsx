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
        className={`flex items-center gap-2 px-4 py-2 rounded font-bold text-sm transition-colors ${
          hasRunningAgents
            ? confirming
              ? 'bg-red-700 hover:bg-red-600 text-white'
              : 'bg-red-600 hover:bg-red-500 text-white'
            : 'bg-gray-700 text-gray-500 cursor-not-allowed'
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
