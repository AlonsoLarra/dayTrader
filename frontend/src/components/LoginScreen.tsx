import { useState } from 'react';
import { TrendingUp } from 'lucide-react';

interface Props {
  onAuthenticated: (token: string) => void;
}

type Step = 'email' | 'set-password' | 'enter-password';

export function LoginScreen({ onAuthenticated }: Props) {
  const [step, setStep] = useState<Step>('email');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const API = import.meta.env.VITE_API_BASE_URL ?? '/api';

  const handleEmailSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    const trimmed = email.trim().toLowerCase();
    setLoading(true);
    try {
      const res = await fetch(`${API}/auth/check-email`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: trimmed }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail ?? 'Error checking email');
      } else {
        setStep(data.has_password ? 'enter-password' : 'set-password');
      }
    } catch {
      setError('Cannot reach the server. Is the backend running?');
    } finally {
      setLoading(false);
    }
  };

  const handleSetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${API}/auth/set-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail ?? 'Error setting password');
      } else {
        localStorage.setItem('daytrader_token', data.token);
        onAuthenticated(data.token);
      }
    } catch {
      setError('Cannot reach the server.');
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await fetch(`${API}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail ?? 'Invalid credentials');
      } else {
        localStorage.setItem('daytrader_token', data.token);
        onAuthenticated(data.token);
      }
    } catch {
      setError('Cannot reach the server.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="p-2 bg-blue-600 rounded-xl">
            <TrendingUp size={24} className="text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white">dayTrader</h1>
            <p className="text-xs text-gray-400">AI Crypto Trading Platform</p>
          </div>
        </div>

        <div className="bg-gray-800 border border-gray-700 rounded-xl p-6 shadow-2xl">
          {step === 'email' && (
            <form onSubmit={handleEmailSubmit} className="space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-white mb-1">Welcome back</h2>
                <p className="text-xs text-gray-400">Enter your email to continue</p>
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="your@email.com"
                  autoFocus
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2.5 text-white text-sm placeholder-gray-500 focus:outline-none focus:border-blue-500"
                />
              </div>
              {error && <p className="text-xs text-red-400">{error}</p>}
              <button type="submit" disabled={loading || !email}
                className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-600 text-white rounded-lg font-medium text-sm transition-colors">
                {loading ? 'Checking…' : 'Continue'}
              </button>
            </form>
          )}

          {step === 'set-password' && (
            <form onSubmit={handleSetPassword} className="space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-white mb-1">Create your password</h2>
                <p className="text-xs text-gray-400">First time setup — choose a strong password</p>
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="At least 8 characters"
                  autoFocus
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2.5 text-white text-sm placeholder-gray-500 focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Confirm password</label>
                <input
                  type="password"
                  value={confirm}
                  onChange={e => setConfirm(e.target.value)}
                  placeholder="Repeat password"
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2.5 text-white text-sm placeholder-gray-500 focus:outline-none focus:border-blue-500"
                />
              </div>
              {error && <p className="text-xs text-red-400">{error}</p>}
              <button type="submit" disabled={loading || !password || !confirm}
                className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-600 text-white rounded-lg font-medium text-sm transition-colors">
                {loading ? 'Setting up…' : 'Set Password & Enter'}
              </button>
              <button type="button" onClick={() => { setStep('email'); setError(''); }}
                className="w-full text-xs text-gray-500 hover:text-gray-300 transition-colors">
                ← Use a different email
              </button>
            </form>
          )}

          {step === 'enter-password' && (
            <form onSubmit={handleLogin} className="space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-white mb-1">Enter your password</h2>
                <p className="text-xs text-gray-400">{email}</p>
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="Your password"
                  autoFocus
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2.5 text-white text-sm placeholder-gray-500 focus:outline-none focus:border-blue-500"
                />
              </div>
              {error && <p className="text-xs text-red-400">{error}</p>}
              <button type="submit" disabled={loading || !password}
                className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-600 text-white rounded-lg font-medium text-sm transition-colors">
                {loading ? 'Signing in…' : 'Sign In'}
              </button>
              <button type="button" onClick={() => { setStep('email'); setError(''); setPassword(''); }}
                className="w-full text-xs text-gray-500 hover:text-gray-300 transition-colors">
                ← Back
              </button>
            </form>
          )}
        </div>

        <p className="text-center text-xs text-gray-600 mt-6">
          Access restricted to authorised users only.
        </p>
      </div>
    </div>
  );
}
