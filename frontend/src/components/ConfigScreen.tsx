import { useState, useEffect, useCallback } from 'react';
import { Save, Check, AlertCircle, Settings, Wallet } from 'lucide-react';
import { getPaperWallet, setPaperWallet, getRiskConfig, updateRiskConfig, type PaperWalletData, type RiskConfig } from '../api/client';

const CURRENCIES = ['MXN', 'BTC', 'USD', 'USDT'] as const;
type Currency = typeof CURRENCIES[number];

function Field({
  label,
  description,
  value,
  onChange,
  type = 'number',
  min,
  step,
}: {
  label: string;
  description: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  min?: number;
  step?: number;
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-200 mb-0.5">{label}</label>
      <p className="text-xs text-gray-500 mb-1.5">{description}</p>
      <input
        type={type}
        min={min}
        step={step}
        value={value}
        onChange={e => onChange(e.target.value)}
        className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
      />
    </div>
  );
}

export function ConfigScreen() {
  // --- Wallet state ---
  const [walletCurrency, setWalletCurrency] = useState<Currency>('USD');
  const [walletData, setWalletData] = useState<PaperWalletData | null>(null);
  const [walletValue, setWalletValue] = useState('');
  const [walletSaving, setWalletSaving] = useState(false);
  const [walletMsg, setWalletMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  // --- Risk config state ---
  const [riskValues, setRiskValues] = useState({ max_losses: '3', max_loss_pct: '5', max_trades: '10' });
  const [riskSaving, setRiskSaving] = useState(false);
  const [riskLoading, setRiskLoading] = useState(true);
  const [riskMsg, setRiskMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  // Load wallet for selected currency
  const loadWallet = useCallback(async (currency: Currency) => {
    try {
      const data = await getPaperWallet(currency);
      setWalletData(data);
      setWalletValue(String(data.starting_balance));
    } catch {
      // ignore
    }
  }, []);

  // Load risk config
  const loadRiskConfig = useCallback(async () => {
    setRiskLoading(true);
    try {
      const cfg = await getRiskConfig();
      setRiskValues({
        max_losses: String(cfg.max_losses_per_day),
        max_loss_pct: String(Math.round(cfg.max_daily_loss_pct * 100 * 100) / 100),
        max_trades: String(cfg.max_trades_per_day),
      });
    } catch {
      // keep defaults
    } finally {
      setRiskLoading(false);
    }
  }, []);

  useEffect(() => { loadWallet(walletCurrency); }, [walletCurrency, loadWallet]);
  useEffect(() => { loadRiskConfig(); }, [loadRiskConfig]);

  const handleWalletSave = async () => {
    const amount = parseFloat(walletValue);
    if (isNaN(amount) || amount <= 0) {
      setWalletMsg({ type: 'err', text: 'Enter a valid positive amount.' });
      return;
    }
    setWalletSaving(true);
    setWalletMsg(null);
    try {
      await setPaperWallet(amount, walletCurrency);
      await loadWallet(walletCurrency);
      setWalletMsg({ type: 'ok', text: 'Balance updated.' });
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setWalletMsg({ type: 'err', text: detail || 'Failed to save.' });
    } finally {
      setWalletSaving(false);
      setTimeout(() => setWalletMsg(null), 3000);
    }
  };

  const handleRiskSave = async () => {
    const losses = parseInt(riskValues.max_losses, 10);
    const pct = parseFloat(riskValues.max_loss_pct);
    const trades = parseInt(riskValues.max_trades, 10);
    if (isNaN(losses) || losses < 1 || isNaN(pct) || pct < 0.1 || pct > 100 || isNaN(trades) || trades < 1) {
      setRiskMsg({ type: 'err', text: 'Check your values — all fields must be valid.' });
      return;
    }
    const payload: RiskConfig = {
      max_losses_per_day: losses,
      max_daily_loss_pct: pct / 100,
      max_trades_per_day: trades,
    };
    setRiskSaving(true);
    setRiskMsg(null);
    try {
      await updateRiskConfig(payload);
      setRiskMsg({ type: 'ok', text: 'Risk limits saved.' });
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setRiskMsg({ type: 'err', text: detail || 'Failed to save.' });
    } finally {
      setRiskSaving(false);
      setTimeout(() => setRiskMsg(null), 3000);
    }
  };

  const selectedBalance = walletData?.balances?.[walletCurrency] ?? walletData;

  return (
    <div className="p-4 space-y-4 max-w-lg mx-auto">
      {/* ── Paper Wallet Section ── */}
      <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
        <div className="flex items-center gap-2 mb-4">
          <Wallet size={16} className="text-blue-400" />
          <h2 className="text-sm font-semibold text-white">Paper Wallet Capital</h2>
        </div>

        {/* Currency tabs */}
        <div className="flex gap-1 mb-4">
          {CURRENCIES.map(c => (
            <button
              key={c}
              onClick={() => setWalletCurrency(c)}
              className={`flex-1 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                walletCurrency === c
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-700 text-gray-400 hover:text-white'
              }`}
            >
              {c}
            </button>
          ))}
        </div>

        {/* Balance overview */}
        {selectedBalance && (
          <div className="grid grid-cols-3 gap-2 mb-4">
            {[
              { label: 'Starting', value: selectedBalance.starting_balance },
              { label: 'Deployed', value: selectedBalance.deployed },
              { label: 'Available', value: selectedBalance.available },
            ].map(({ label, value }) => (
              <div key={label} className="bg-gray-900 rounded-lg p-2.5 text-center">
                <p className="text-xs text-gray-500 mb-0.5">{label}</p>
                <p className="text-sm font-semibold text-white">
                  {walletCurrency === 'BTC' ? value.toFixed(6) : value.toFixed(2)}
                </p>
              </div>
            ))}
          </div>
        )}

        {/* Edit starting balance */}
        <div className="space-y-3">
          <Field
            label={`Starting Balance (${walletCurrency})`}
            description="Sets the total paper capital for this currency. Running bots keep their allocated budgets."
            value={walletValue}
            onChange={setWalletValue}
            min={0.000001}
            step={walletCurrency === 'BTC' ? 0.001 : 1}
          />

          <div className="flex items-center gap-2">
            <button
              onClick={handleWalletSave}
              disabled={walletSaving}
              className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors"
            >
              <Save size={13} />
              {walletSaving ? 'Saving…' : 'Save Balance'}
            </button>
            {walletMsg && (
              <span className={`flex items-center gap-1 text-xs ${walletMsg.type === 'ok' ? 'text-green-400' : 'text-red-400'}`}>
                {walletMsg.type === 'ok' ? <Check size={12} /> : <AlertCircle size={12} />}
                {walletMsg.text}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* ── Risk Limits Section ── */}
      <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <Settings size={16} className="text-amber-400" />
            <h2 className="text-sm font-semibold text-white">Risk Limits</h2>
          </div>
        </div>
        <p className="text-xs text-gray-500 mb-4">Applied to newly created bots. Existing running bots keep their current limits.</p>

        {riskLoading ? (
          <p className="text-xs text-gray-500 py-4 text-center">Loading…</p>
        ) : (
          <div className="space-y-4">
            <Field
              label="Max Losses Per Day"
              description="Stop opening new positions after this many losing trades in a day."
              value={riskValues.max_losses}
              onChange={v => setRiskValues(r => ({ ...r, max_losses: v }))}
              min={1}
              step={1}
            />
            <Field
              label="Max Daily Loss %"
              description="Stop trading if total loss exceeds this % of the bot's allocated budget."
              value={riskValues.max_loss_pct}
              onChange={v => setRiskValues(r => ({ ...r, max_loss_pct: v }))}
              min={0.1}
              step={0.5}
            />
            <Field
              label="Max Trades Per Day"
              description="Hard cap on the total number of trades a bot can make per day."
              value={riskValues.max_trades}
              onChange={v => setRiskValues(r => ({ ...r, max_trades: v }))}
              min={1}
              step={1}
            />

            <div className="flex items-center gap-2">
              <button
                onClick={handleRiskSave}
                disabled={riskSaving}
                className="flex items-center gap-1.5 px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors"
              >
                <Save size={13} />
                {riskSaving ? 'Saving…' : 'Save Limits'}
              </button>
              {riskMsg && (
                <span className={`flex items-center gap-1 text-xs ${riskMsg.type === 'ok' ? 'text-green-400' : 'text-red-400'}`}>
                  {riskMsg.type === 'ok' ? <Check size={12} /> : <AlertCircle size={12} />}
                  {riskMsg.text}
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
