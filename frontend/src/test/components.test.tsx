/**
 * Frontend component tests.
 * API calls are mocked — no real backend needed.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AutoTradeModal } from '../components/AutoTradeModal';
import { WalletHeader } from '../components/WalletHeader';

// vi.mock is hoisted — use vi.fn() inside the factory, not external variables
vi.mock('../api/client', () => ({
  analyzeMarket: vi.fn(),
  deployPortfolio: vi.fn(),
  getWallet: vi.fn(),
  getMode: vi.fn(),
  setMode: vi.fn(),
  getPaperWallet: vi.fn(),
  setPaperWallet: vi.fn(),
}));

// Import after mock is set up so we get the mocked versions
import * as apiMock from '../api/client';

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
    analyze.mockResolvedValue({ pairs: [{ symbol: 'XRP/MXN', score: 75 }] });
    deploy.mockResolvedValue({
      agent_ids: ['a1'],
      total_budget: 100,
      pairs: [{ symbol: 'XRP/MXN', budget_allocated: 100 }],
    });

    render(<AutoTradeModal {...defaultProps} />);
    fireEvent.click(screen.getByText(/Start Trading/i));

    await waitFor(() => expect(analyze).toHaveBeenCalledWith(10));
    await waitFor(() => expect(deploy).toHaveBeenCalled());
  });

  it('shows error message when deploy fails', async () => {
    const analyze = apiMock.analyzeMarket as ReturnType<typeof vi.fn>;
    analyze.mockRejectedValue(new Error('Network error'));
    render(<AutoTradeModal {...defaultProps} />);
    fireEvent.click(screen.getByText(/Start Trading/i));
    await waitFor(() => expect(screen.getByText(/Network error/i)).toBeInTheDocument());
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

describe('WalletHeader', () => {
  const mockWallet = {
    starting_balance: 100,
    available: 75,
    deployed: 25,
    in_market: 10,
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
