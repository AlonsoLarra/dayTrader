/**
 * Frontend component tests.
 * API calls are mocked — no real backend needed.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { DeployPanel } from '../components/DeployPanel';
import { WalletHeader } from '../components/WalletHeader';
import { AgentCard } from '../components/AgentCard';
import { BacktestPanel } from '../components/BacktestPanel';
import { PositionsPanel } from '../components/PositionsPanel';

// vi.mock is hoisted — use vi.fn() inside the factory, not external variables
vi.mock('../api/client', () => ({
  analyzeMarket: vi.fn(),
  deployPortfolio: vi.fn(),
  getMarkets: vi.fn(),
  getWallet: vi.fn(),
  getMode: vi.fn(),
  setMode: vi.fn(),
  getPaperWallet: vi.fn(),
  setPaperWallet: vi.fn(),
  getTrades: vi.fn(),
  getAgents: vi.fn(),
  getPrices: vi.fn(),
  getPriceOhlcv: vi.fn(),
  getAgentLogs: vi.fn(),
  startAgent: vi.fn(),
  stopAgent: vi.fn(),
  killAgent: vi.fn(),
  deleteAgent: vi.fn(),
  getStrategyReasoning: vi.fn(),
  getMarketScan: vi.fn(),
  getPositions: vi.fn(),
  forceSell: vi.fn(),
  runBacktest: vi.fn(),
}));

vi.mock('../hooks/useWebSocket', () => ({
  useWebSocket: () => ({
    lastMessage: null,
    messages: [],
    readyState: WebSocket.CLOSED,
    sendMessage: vi.fn(),
  }),
}));

// Import after mock is set up so we get the mocked versions
import * as apiMock from '../api/client';
import App from '../App';

// ── DeployPanel tests ─────────────────────────────────────────────────────────

describe('DeployPanel', () => {
  const defaultProps = {
    available: 100,
    onDeployed: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    (apiMock.getPaperWallet as ReturnType<typeof vi.fn>).mockResolvedValue({
      starting_balance: 100,
      available: 100,
      deployed: 0,
      in_market: 0,
      balances: {
        USD: { starting_balance: 100, deployed: 0, in_market: 0, available: 100 },
      },
    });
  });

  it('renders budget input and Start Trading button', async () => {
    render(<DeployPanel {...defaultProps} />);
    await waitFor(() => expect(screen.getByText(/Start Trading/i)).toBeInTheDocument());
    expect(screen.getByPlaceholderText(/100/i)).toBeInTheDocument();
  });

  it('calls analyzeMarket then deployPortfolio on submit with USD', async () => {
    const analyze = apiMock.analyzeMarket as ReturnType<typeof vi.fn>;
    const deploy = apiMock.deployPortfolio as ReturnType<typeof vi.fn>;
    const markets = apiMock.getMarkets as ReturnType<typeof vi.fn>;
    markets.mockResolvedValue({ symbols: ['BTC/USD'] });
    analyze.mockResolvedValue({ pairs: [{ symbol: 'BTC/USD', score: 75 }] });
    deploy.mockResolvedValue({
      agent_ids: ['a1'],
      total_budget: 100,
      pairs: [{ symbol: 'BTC/USD', budget_allocated: 100 }],
    });

    render(<DeployPanel {...defaultProps} />);
    await waitFor(() => screen.getByText(/Start Trading/i));
    fireEvent.click(screen.getByText(/Start Trading/i));

    await waitFor(() => expect(analyze).toHaveBeenCalledWith(0, 'USD'));
    await waitFor(() => expect(deploy).toHaveBeenCalledWith(expect.objectContaining({
      quote_currency: 'USD',
    })));
  });

  it('shows error message when deploy fails', async () => {
    const analyze = apiMock.analyzeMarket as ReturnType<typeof vi.fn>;
    analyze.mockRejectedValue(new Error('Network error'));
    render(<DeployPanel {...defaultProps} />);
    await waitFor(() => screen.getByText(/Start Trading/i));
    fireEvent.click(screen.getByText(/Start Trading/i));
    await waitFor(() => expect(screen.getByText(/Network error/i)).toBeInTheDocument());
  });

  it('shows success state after deploy', async () => {
    const analyze = apiMock.analyzeMarket as ReturnType<typeof vi.fn>;
    const deploy = apiMock.deployPortfolio as ReturnType<typeof vi.fn>;
    const markets = apiMock.getMarkets as ReturnType<typeof vi.fn>;
    markets.mockResolvedValue({ symbols: ['BTC/USD', 'ETH/USD'] });
    analyze.mockResolvedValue({ pairs: [] });
    deploy.mockResolvedValue({
      agent_ids: ['a1', 'a2'],
      total_budget: 100,
      pairs: [
        { symbol: 'BTC/USD', budget_allocated: 50 },
        { symbol: 'ETH/USD', budget_allocated: 50 },
      ],
    });

    render(<DeployPanel {...defaultProps} />);
    await waitFor(() => screen.getByText(/Start Trading/i));
    fireEvent.click(screen.getByText(/Start Trading/i));
    await waitFor(() => expect(screen.getByText(/Agents started/i)).toBeInTheDocument());
    expect(screen.getByText(/2 pairs/i)).toBeInTheDocument();
  });
});

// ── WalletHeader tests ────────────────────────────────────────────────────────

describe('PositionsPanel', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows current position value separately from the unit price', async () => {
    (apiMock.getPositions as ReturnType<typeof vi.fn>).mockResolvedValue({
      positions: [
        {
          agent_id: 'a1',
          symbol: 'FET/USD',
          strategy: 'trend_rsi',
          side: 'buy',
          amount: 100,
          entry_price: 0.25,
          current_price: 0.252,
          unrealized_pnl: 0.2,
          pnl_pct: 0.8,
          proceeds_if_sold: 25.2,
          cost_basis: 25.0,
        },
      ],
    });

    render(<PositionsPanel />);

    await waitFor(() => expect(screen.getByText(/Current Value/i)).toBeInTheDocument());
    expect(screen.getByText('25.20 USD')).toBeInTheDocument();
    expect(screen.getByText(/@ 0\.2500 USD each/i)).toBeInTheDocument();
    expect(screen.getByText(/@ 0\.2520 USD each/i)).toBeInTheDocument();
    expect(screen.getByText('100.00 FET')).toBeInTheDocument();
  });
});

describe('App auth gate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    (apiMock.getTrades as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (apiMock.getAgents as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (apiMock.getPaperWallet as ReturnType<typeof vi.fn>).mockResolvedValue({
      starting_balance: 100,
      available: 100,
      deployed: 0,
      in_market: 0,
    });
    (apiMock.getPrices as ReturnType<typeof vi.fn>).mockResolvedValue({ prices: {}, timestamp: new Date().toISOString() });
    (apiMock.getPriceOhlcv as ReturnType<typeof vi.fn>).mockResolvedValue({ symbol: 'BTC/MXN', timeframe: '1h', data: [] });
  });

  it('shows the login screen without calling protected endpoints first', async () => {
    render(<App />);

    await waitFor(() => expect(screen.getByText(/Welcome back/i)).toBeInTheDocument());
    expect(apiMock.getTrades).not.toHaveBeenCalled();
    expect(apiMock.getAgents).not.toHaveBeenCalled();
    expect(apiMock.getPaperWallet).not.toHaveBeenCalled();
  });
});

describe('AgentCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (apiMock.getAgentLogs as ReturnType<typeof vi.fn>).mockResolvedValue([]);
  });

  it('shows active review cadence and rotation status', () => {
    render(
      <AgentCard
        agent={{
          agent_id: 'bot-1',
          strategy: 'adaptive',
          status: 'running',
          symbol: 'SOL/MXN',
          budget_allocated: 100,
          budget_used: 25,
          trades_today: 2,
          losses_today: 0,
          realized_pnl_today: 5,
          realized_pnl_total: 8,
          rotation_enabled: true,
          aggressive_rotation: true,
          rotation_interval_minutes: 1,
          last_signal: 'hold',
          last_tick_at: null,
          last_market_review_at: null,
          last_rotation_at: null,
        }}
        onUpdate={vi.fn()}
      />
    );

    expect(screen.getByText(/Adaptive review · 1m/i)).toBeInTheDocument();
    expect(screen.getByText(/Market review active/i)).toBeInTheDocument();
    expect(screen.getByText(/Every 1 min/i)).toBeInTheDocument();
    expect(screen.getByText('Pending')).toBeInTheDocument();
    expect(screen.getByText(/No switch yet/i)).toBeInTheDocument();
  });

  it('formats BTC bot budgets with BTC units', () => {
    render(
      <AgentCard
        agent={{
          agent_id: 'bot-btc',
          strategy: 'adaptive',
          status: 'stopped',
          symbol: 'ETH/BTC',
          quote_currency: 'BTC',
          budget_allocated: 0.01,
          budget_used: 0,
          trades_today: 0,
          losses_today: 0,
          realized_pnl_today: 0,
          realized_pnl_total: 0,
          rotation_enabled: true,
          aggressive_rotation: true,
          rotation_interval_minutes: 1,
          last_signal: 'hold',
          last_tick_at: null,
          last_market_review_at: null,
          last_rotation_at: null,
        }}
        onUpdate={vi.fn()}
      />
    );

    expect(screen.getAllByText(/0\.010000 BTC/i).length).toBeGreaterThan(0);
  });
});

describe('BacktestPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (apiMock.getStrategyReasoning as ReturnType<typeof vi.fn>).mockResolvedValue({
      bots: [
        {
          agent_id: 'bot-1',
          symbol: 'XRP/MXN',
          strategy: 'adaptive',
          current_price: 23,
          has_position: false,
          entry_price: null,
          unrealized_pnl: null,
          stop_loss_price: null,
          stop_loss_pct: 3,
          reasoning: {
            action: 'WAITING',
            trigger: 'No buy: downtrend (price $23 < EMA50 $24)',
            urgency: 'low',
            rsi: 40,
            oversold: 35,
            overbought: 65,
          },
        },
      ],
    });
    (apiMock.getMarketScan as ReturnType<typeof vi.fn>).mockResolvedValue({
      pairs: [
        {
          symbol: 'AVAX/MXN',
          score: 64,
          rsi: 36,
          price: 620,
          strategy: 'adaptive',
          action: 'BUY SIGNAL',
          reason: 'Buy signal: uptrend + RSI pullback + volume confirmation',
          confidence: 0.74,
          tracked_count: 1,
        },
      ],
    });
  });

  it('shows evaluated pairs and their current decision reasoning', async () => {
    render(<BacktestPanel />);

    await waitFor(() => expect(screen.getByText(/Pairs evaluated this cycle/i)).toBeInTheDocument());
    expect(screen.getByText('AVAX/MXN')).toBeInTheDocument();
    expect(screen.getAllByText(/BUY SIGNAL/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Buy signal: uptrend \+ RSI pullback \+ volume confirmation/i)).toBeInTheDocument();
    expect(screen.getByText(/Being watched by 1 bot/i)).toBeInTheDocument();
  });

  it('stops showing the loading state when the market scan request fails', async () => {
    (apiMock.getMarketScan as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('scan temporarily unavailable'));

    render(<BacktestPanel />);

    await waitFor(() => expect(screen.queryByText(/Loading bot analysis/i)).not.toBeInTheDocument());
    expect(screen.getByText('XRP/MXN')).toBeInTheDocument();
    expect(screen.getByText(/No market scan available right now/i)).toBeInTheDocument();
  });
});

describe('WalletHeader', () => {
  const mockWallet = {
    starting_balance: 100,
    available: 75,
    deployed: 25,
    in_market: 10,
    balances: {
      MXN: { starting_balance: 100, available: 75, deployed: 25, in_market: 10 },
      BTC: { starting_balance: 0.01, available: 0.01, deployed: 0, in_market: 0 },
      USD: { starting_balance: 250, available: 250, deployed: 0, in_market: 0 },
      USDT: { starting_balance: 250, available: 250, deployed: 0, in_market: 0 },
    },
  };

  beforeEach(() => {
    vi.clearAllMocks();
    (apiMock.getPaperWallet as ReturnType<typeof vi.fn>).mockResolvedValue(mockWallet);
    (apiMock.getMode as ReturnType<typeof vi.fn>).mockResolvedValue({ paper_mode: true });
    (apiMock.getWallet as ReturnType<typeof vi.fn>).mockResolvedValue({ balances: {}, paper_mode: true });
  });

  it('renders the PAPER badge', async () => {
    render(<WalletHeader onAvailableChange={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('PAPER')).toBeInTheDocument());
  });

  it('calls onAvailableChange with USD wallet available amount', async () => {
    const onAvailableChange = vi.fn();
    render(<WalletHeader onAvailableChange={onAvailableChange} />);
    await waitFor(() => expect(onAvailableChange).toHaveBeenCalledWith(250));
  });

  it('opens dropdown when pill is clicked', async () => {
    render(<WalletHeader onAvailableChange={vi.fn()} />);
    await waitFor(() => screen.getByText('PAPER'));
    fireEvent.click(screen.getByText('PAPER').closest('button')!);
    await waitFor(() => expect(screen.getByText('Paper Wallet')).toBeInTheDocument());
    expect(screen.getByText('USD')).toBeInTheDocument();
    expect(screen.getByText('USDT')).toBeInTheDocument();
  });

  it('shows live trading warning when not in paper mode', async () => {
    (apiMock.getMode as ReturnType<typeof vi.fn>).mockResolvedValue({ paper_mode: false });
    (apiMock.getWallet as ReturnType<typeof vi.fn>).mockResolvedValue({
      balances: { MXN: { free: 500, used: 0, total: 500 } },
      paper_mode: false,
    });

    render(<WalletHeader onAvailableChange={vi.fn()} />);
    await waitFor(() => screen.getByText('LIVE'));
    fireEvent.click(screen.getByText('LIVE').closest('button')!);
    await waitFor(() =>
      expect(screen.getByText(/Live mode — agents place real orders/i)).toBeInTheDocument()
    );
  });
});
