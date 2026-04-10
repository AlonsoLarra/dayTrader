/**
 * Frontend component tests.
 * API calls are mocked — no real backend needed.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AutoTradeModal } from '../components/AutoTradeModal';
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

// ── AutoTradeModal tests ──────────────────────────────────────────────────────

describe('AutoTradeModal', () => {
  const defaultProps = {
    available: 100,
    onClose: vi.fn(),
    onDeployed: vi.fn(),
  };

  beforeEach(() => vi.clearAllMocks());

  it('renders budget input and Start Trading button', () => {
    render(<AutoTradeModal {...defaultProps} />);
    expect(screen.getByText(/Start Trading/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/MXN/i)).toBeInTheDocument();
  });

  it('shows Cancel button that calls onClose', () => {
    render(<AutoTradeModal {...defaultProps} />);
    fireEvent.click(screen.getByText('Cancel'));
    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  it('disables Start Trading when budget exceeds available', () => {
    render(<AutoTradeModal {...defaultProps} available={50} />);
    const input = screen.getByPlaceholderText(/MXN/i);
    fireEvent.change(input, { target: { value: '200' } });
    const btn = screen.getByText(/Start Trading/i).closest('button');
    expect(btn).toBeDisabled();
  });

  it('calls analyzeMarket then deployPortfolio on submit', async () => {
    const analyze = apiMock.analyzeMarket as ReturnType<typeof vi.fn>;
    const deploy = apiMock.deployPortfolio as ReturnType<typeof vi.fn>;
    const markets = apiMock.getMarkets as ReturnType<typeof vi.fn>;
    markets.mockResolvedValue({ symbols: ['XRP/MXN'] });
    analyze.mockResolvedValue({ pairs: [{ symbol: 'XRP/MXN', score: 75 }] });
    deploy.mockResolvedValue({
      agent_ids: ['a1'],
      total_budget: 100,
      pairs: [{ symbol: 'XRP/MXN', budget_allocated: 100 }],
    });

    render(<AutoTradeModal {...defaultProps} />);
    fireEvent.click(screen.getByText(/Start Trading/i));

    await waitFor(() => expect(analyze).toHaveBeenCalledWith(0, 'MXN'));
    await waitFor(() => expect(deploy).toHaveBeenCalledWith({
      budget: 100,
      max_agents: 3,
      min_score: 20,
      quote_currency: 'MXN',
      rotation_enabled: true,
      rotation_interval_minutes: 1,
      aggressive_rotation: true,
      min_rotation_score_delta: 1,
    }));
  });

  it('can switch to BTC quote mode for auto-trade', async () => {
    const analyze = apiMock.analyzeMarket as ReturnType<typeof vi.fn>;
    const deploy = apiMock.deployPortfolio as ReturnType<typeof vi.fn>;
    const markets = apiMock.getMarkets as ReturnType<typeof vi.fn>;
    const paperWallet = apiMock.getPaperWallet as ReturnType<typeof vi.fn>;

    markets.mockImplementation((quote?: string) => Promise.resolve({
      symbols: quote === 'BTC' ? ['ETH/BTC', 'SOL/BTC'] : quote === 'USD' ? ['BTC/USD', 'ETH/USD', 'SOL/USD'] : ['BTC/MXN'],
    }));
    paperWallet.mockResolvedValue({
      starting_balance: 100,
      deployed: 0,
      in_market: 0,
      available: 75,
      balances: {
        MXN: { starting_balance: 100, deployed: 0, in_market: 0, available: 75 },
        BTC: { starting_balance: 0.01, deployed: 0, in_market: 0, available: 0.01 },
        USD: { starting_balance: 250, deployed: 0, in_market: 0, available: 250 },
        USDT: { starting_balance: 250, deployed: 0, in_market: 0, available: 250 },
      },
    });
    analyze.mockResolvedValue({ pairs: [{ symbol: 'ETH/BTC', score: 75, strategy: 'trend_rsi', reason: 'Buy signal active' }] });
    deploy.mockResolvedValue({
      agent_ids: ['a1'],
      total_budget: 0.01,
      pairs: [{ symbol: 'ETH/BTC', budget_allocated: 0.01 }],
    });

    render(<AutoTradeModal {...defaultProps} />);
    fireEvent.change(screen.getByLabelText(/Quote currency/i), { target: { value: 'BTC' } });
    fireEvent.click(screen.getByText(/Start Trading/i));

    await waitFor(() => expect(analyze).toHaveBeenCalledWith(0, 'BTC'));
    await waitFor(() => expect(deploy).toHaveBeenCalledWith(expect.objectContaining({
      quote_currency: 'BTC',
    })));
  });

  it('can switch to USD quote mode to scan a much larger market set', async () => {
    const analyze = apiMock.analyzeMarket as ReturnType<typeof vi.fn>;
    const deploy = apiMock.deployPortfolio as ReturnType<typeof vi.fn>;
    const markets = apiMock.getMarkets as ReturnType<typeof vi.fn>;
    const paperWallet = apiMock.getPaperWallet as ReturnType<typeof vi.fn>;

    markets.mockImplementation((quote?: string) => Promise.resolve({
      symbols: quote === 'USD' ? ['BTC/USD', 'ETH/USD', 'SOL/USD', 'ADA/USD'] : ['BTC/MXN'],
    }));
    paperWallet.mockResolvedValue({
      starting_balance: 100,
      deployed: 0,
      in_market: 0,
      available: 75,
      balances: {
        MXN: { starting_balance: 100, deployed: 0, in_market: 0, available: 75 },
        BTC: { starting_balance: 0.01, deployed: 0, in_market: 0, available: 0.01 },
        USD: { starting_balance: 250, deployed: 0, in_market: 0, available: 250 },
        USDT: { starting_balance: 250, deployed: 0, in_market: 0, available: 250 },
      },
    });
    analyze.mockResolvedValue({ pairs: [{ symbol: 'BTC/USD', score: 81, strategy: 'adaptive', reason: 'Strong buy setup' }] });
    deploy.mockResolvedValue({
      agent_ids: ['a1'],
      total_budget: 250,
      pairs: [{ symbol: 'BTC/USD', budget_allocated: 250 }],
    });

    render(<AutoTradeModal {...defaultProps} />);
    fireEvent.change(screen.getByLabelText(/Quote currency/i), { target: { value: 'USD' } });
    fireEvent.click(screen.getByText(/Start Trading/i));

    await waitFor(() => expect(analyze).toHaveBeenCalledWith(0, 'USD'));
    await waitFor(() => expect(deploy).toHaveBeenCalledWith(expect.objectContaining({
      quote_currency: 'USD',
    })));
  });

  it('shows error message when deploy fails', async () => {
    const analyze = apiMock.analyzeMarket as ReturnType<typeof vi.fn>;
    analyze.mockRejectedValue(new Error('Network error'));
    render(<AutoTradeModal {...defaultProps} />);
    fireEvent.click(screen.getByText(/Start Trading/i));
    await waitFor(() => expect(screen.getByText(/Network error/i)).toBeInTheDocument());
  });

  it('shows the analyzed markets and reasoning while deployment is in progress', async () => {
    const analyze = apiMock.analyzeMarket as ReturnType<typeof vi.fn>;
    const deploy = apiMock.deployPortfolio as ReturnType<typeof vi.fn>;
    const markets = apiMock.getMarkets as ReturnType<typeof vi.fn>;

    markets.mockResolvedValue({
      symbols: ['AVAX/MXN', 'BTC/MXN', 'ETH/MXN', 'USDT/MXN', 'SOL/MXN', 'ADA/MXN'],
    });

    let finishAnalysis: ((value: { pairs: Array<Record<string, unknown>>; total_markets?: number }) => void) | undefined;
    analyze.mockReturnValue(new Promise(resolve => {
      finishAnalysis = resolve;
    }));

    const analyzedPairs = {
      total_markets: 6,
      pairs: [
        {
          symbol: 'AVAX/MXN',
          score: 82,
          strategy: 'trend_rsi',
          reason: 'Buy signal active — uptrend + RSI pullback + volume support',
          action: 'BUY SIGNAL',
          confidence: 0.74,
        },
        {
          symbol: 'BTC/MXN',
          score: 61,
          strategy: 'adaptive',
          reason: 'Waiting for a stronger pullback',
          action: 'WAITING',
          confidence: 0.21,
        },
        {
          symbol: 'ETH/MXN',
          score: 58,
          strategy: 'adaptive',
          reason: 'Watching for stronger momentum',
          action: 'WAITING',
          confidence: 0.18,
        },
        {
          symbol: 'USDT/MXN',
          score: 54,
          strategy: 'trend_rsi',
          reason: 'Flat structure, low urgency',
          action: 'WAITING',
          confidence: 0.14,
        },
        {
          symbol: 'SOL/MXN',
          score: 53,
          strategy: 'trend_rsi',
          reason: 'Healthy pullback but needs confirmation',
          action: 'WAITING',
          confidence: 0.16,
        },
        {
          symbol: 'ADA/MXN',
          score: 49,
          strategy: 'rsi',
          reason: 'Still below trigger',
          action: 'WAITING',
          confidence: 0.11,
        },
      ],
    };

    let finishDeploy: ((value: { agent_ids: string[]; total_budget: number; pairs: { symbol: string; budget_allocated: number }[] }) => void) | undefined;
    deploy.mockReturnValue(new Promise(resolve => {
      finishDeploy = resolve;
    }));

    render(<AutoTradeModal {...defaultProps} />);
    fireEvent.click(screen.getByText(/Start Trading/i));

    await waitFor(() => expect(screen.getByText(/Markets in this scan/i)).toBeInTheDocument());
    expect(screen.getByText('AVAX/MXN')).toBeInTheDocument();
    expect(screen.getByText('BTC/MXN')).toBeInTheDocument();
    expect(screen.getByText('ETH/MXN')).toBeInTheDocument();
    expect(screen.getByText('USDT/MXN')).toBeInTheDocument();
    expect(screen.getByText('SOL/MXN')).toBeInTheDocument();
    expect(screen.getByText('ADA/MXN')).toBeInTheDocument();

    finishAnalysis?.(analyzedPairs);

    await waitFor(() => expect(screen.getByText(/Markets reviewed/i)).toBeInTheDocument());
    expect(screen.getByText(/Showing all 6/i)).toBeInTheDocument();
    expect(screen.getByText(/Buy signal active — uptrend \+ RSI pullback \+ volume support/i)).toBeInTheDocument();
    expect(screen.getByText('SOL/MXN')).toBeInTheDocument();
    expect(screen.getByText('ADA/MXN')).toBeInTheDocument();
    expect(screen.getAllByText(/WAITING/i).length).toBeGreaterThan(0);

    finishDeploy?.({
      agent_ids: ['a1'],
      total_budget: 100,
      pairs: [{ symbol: 'AVAX/MXN', budget_allocated: 100 }],
    });

    await waitFor(() => expect(screen.getByText(/Agents started/i)).toBeInTheDocument());
  });

  it('shows success state after deploy', async () => {
    const analyze = apiMock.analyzeMarket as ReturnType<typeof vi.fn>;
    const deploy = apiMock.deployPortfolio as ReturnType<typeof vi.fn>;
    analyze.mockResolvedValue({ pairs: [] });
    deploy.mockResolvedValue({
      agent_ids: ['a1', 'a2'],
      total_budget: 100,
      pairs: [
        { symbol: 'XRP/MXN', budget_allocated: 50 },
        { symbol: 'SOL/MXN', budget_allocated: 50 },
      ],
    });

    render(<AutoTradeModal {...defaultProps} />);
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
    expect(screen.getByText(/@ 0.25 USD each/i)).toBeInTheDocument();
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

  it('calls onAvailableChange with wallet available amount', async () => {
    const onAvailableChange = vi.fn();
    render(<WalletHeader onAvailableChange={onAvailableChange} />);
    await waitFor(() => expect(onAvailableChange).toHaveBeenCalledWith(75));
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
