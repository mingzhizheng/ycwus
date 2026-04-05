import React, { createContext, useContext, useEffect, useRef, useState, ReactNode } from 'react';

interface WSContextType {
  lastMessage: any;
  sendMessage: (data: any) => void;
  connected: boolean;
}

const WSContext = createContext<WSContextType>({
  lastMessage: null,
  sendMessage: () => {},
  connected: false,
});

export function useWebSocket() {
  return useContext(WSContext);
}

export function WebSocketProvider({ children, facilityId = 1 }: { children: ReactNode; facilityId?: number }) {
  const wsRef = useRef<WebSocket | null>(null);
  const [lastMessage, setLastMessage] = useState<any>(null);
  const [connected, setConnected] = useState(false);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();

  function connect() {
    const token = localStorage.getItem('dyms_token');
    if (!token) return;

    const ws = new WebSocket(`ws://${location.host}/ws/calendar?facility_id=${facilityId}&token=${token}`);

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      reconnectTimer.current = setTimeout(connect, 3000);
    };
    ws.onmessage = (event) => {
      try {
        setLastMessage(JSON.parse(event.data));
      } catch {}
    };

    wsRef.current = ws;
  }

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    };
  }, [facilityId]);

  function sendMessage(data: any) {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }

  return (
    <WSContext.Provider value={{ lastMessage, sendMessage, connected }}>
      {children}
    </WSContext.Provider>
  );
}
