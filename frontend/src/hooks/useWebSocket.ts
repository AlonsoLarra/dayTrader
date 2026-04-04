import { useEffect, useRef, useState, useCallback } from 'react';
import type { WsMessage } from '../types';

const WS_URL = 'ws://localhost:8000/ws';

export function useWebSocket() {
  const [messages, setMessages] = useState<WsMessage[]>([]);
  const [lastMessage, setLastMessage] = useState<WsMessage | null>(null);
  const [readyState, setReadyState] = useState<number>(WebSocket.CONNECTING);
  const ws = useRef<WebSocket | null>(null);
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectDelay = useRef(1000);

  const connect = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) return;

    try {
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
        setReadyState(WebSocket.CLOSED);
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
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current);
      ws.current?.close();
    };
  }, [connect]);

  const sendMessage = useCallback((msg: object) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(msg));
    }
  }, []);

  return { messages, lastMessage, readyState, sendMessage };
}
