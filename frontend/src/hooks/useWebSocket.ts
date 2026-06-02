import { useEffect, useRef, useState, useCallback } from 'react';
import type { WsMessage } from '../types';
import { getWsUrl } from '../config';

const WS_URL = getWsUrl();

export function useWebSocket(enabled = true) {
  const [messages, setMessages] = useState<WsMessage[]>([]);
  const [lastMessage, setLastMessage] = useState<WsMessage | null>(null);
  const [readyState, setReadyState] = useState<number>(WebSocket.CONNECTING);
  const ws = useRef<WebSocket | null>(null);
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectDelay = useRef(1000);
  const manualClose = useRef(false);

  const connect = useCallback(() => {
    if (!enabled || (ws.current && (ws.current.readyState === WebSocket.OPEN || ws.current.readyState === WebSocket.CONNECTING))) return;

    try {
      manualClose.current = false;
      setReadyState(WebSocket.CONNECTING);
      const socket = new WebSocket(WS_URL);
      ws.current = socket;

      socket.onopen = () => {
        setReadyState(WebSocket.OPEN);
        reconnectDelay.current = 1000;
      };

      socket.onmessage = (event) => {
        try {
          const msg: WsMessage = JSON.parse(event.data as string);
          if (msg.type === 'ping' || msg.type === 'pong') return;
          setLastMessage(msg);
          setMessages(prev => [...prev.slice(-99), msg]);
        } catch {
          // ignore malformed messages
        }
      };

      socket.onclose = () => {
        ws.current = null;
        setReadyState(WebSocket.CLOSED);
        if (manualClose.current || !enabled) return;

        reconnectTimeout.current = setTimeout(() => {
          reconnectDelay.current = Math.min(reconnectDelay.current * 2, 30000);
          connect();
        }, reconnectDelay.current);
      };

      socket.onerror = () => {
        socket.close();
      };
    } catch {
      // ignore connection errors - will retry
    }
  }, [enabled]);

  useEffect(() => {
    if (!enabled) {
      manualClose.current = true;
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current);
      ws.current?.close();
      ws.current = null;
      setReadyState(WebSocket.CLOSED);
      return;
    }

    connect();
    return () => {
      manualClose.current = true;
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current);
      ws.current?.close();
      ws.current = null;
    };
  }, [connect, enabled]);

  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === 'visible' && enabled) {
        reconnectDelay.current = 1000;
        if (!ws.current || ws.current.readyState === WebSocket.CLOSED) {
          connect();
        }
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => document.removeEventListener('visibilitychange', handleVisibility);
  }, [connect, enabled]);

  const sendMessage = useCallback((msg: object) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(msg));
    }
  }, []);

  return { messages, lastMessage, readyState, sendMessage };
}
