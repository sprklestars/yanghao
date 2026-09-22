'use client';

import { useState, useEffect, useRef } from 'react';
import { wsClient } from '@/lib/api';

interface ChatMessage {
  id: string;
  sender: 'user' | 'bot';
  content: string;
  timestamp: Date;
  status?: 'sending' | 'sent' | 'verified' | 'error';
  account?: string;
  senderName?: string;
}

const DEMO_MESSAGES: ChatMessage[] = [
  {
    id: '1',
    sender: 'user',
    content: 'Xin chào! Tôi muốn đổi tiền USD sang VND.',
    timestamp: new Date(Date.now() - 300000),
    status: 'verified',
  },
  {
    id: '2',
    sender: 'bot',
    content: 'Chào bạn! 👋 Vui lòng giải đáp câu hỏi xác minh trước:\n\n87 + 13 = ?',
    timestamp: new Date(Date.now() - 295000),
    status: 'sent',
  },
  {
    id: '3',
    sender: 'user',
    content: '100',
    timestamp: new Date(Date.now() - 290000),
    status: 'verified',
  },
  {
    id: '4',
    sender: 'bot',
    content: '✅ Xác minh thành công! Cảm ơn bạn đã kiên nhẫn.\n\nVề việc đổi tiền, hiện tại tỷ giá USD/VND khoảng 24,500. Bạn muốn đổi số tiền bao nhiêu?',
    timestamp: new Date(Date.now() - 285000),
    status: 'verified',
  },
];

export default function LiveChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const [demoMode, setDemoMode] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    let mounted = true;

    const connectWS = async () => {
      try {
        await wsClient.connect();
        if (!mounted) return;
        setIsConnected(true);
        setDemoMode(false);

        wsClient.on('telegram_message', (msg) => {
          const newMsg: ChatMessage = {
            id: `ws-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
            sender: msg.direction === 'inbound' ? 'user' : 'bot',
            content: msg.content,
            timestamp: new Date(msg.timestamp),
            status: 'verified',
            account: msg.account,
            senderName: msg.sender_name,
          };
          setMessages((prev) => [...prev, newMsg]);
        });
      } catch {
        if (!mounted) return;
        setIsConnected(false);
        setDemoMode(true);
        setMessages(DEMO_MESSAGES);
      }
    };

    connectWS();

    return () => {
      mounted = false;
      wsClient.disconnect();
    };
  }, []);

  // Fallback demo simulation when not connected
  useEffect(() => {
    if (!demoMode) return;

    const interval = setInterval(() => {
      const demoIncoming: ChatMessage[] = [
        { id: `demo-${Date.now()}`, sender: 'user', content: 'Tỷ giá hôm nay thế nào?', timestamp: new Date(), status: 'verified' },
        { id: `demo-${Date.now()}-b`, sender: 'bot', content: 'Hiện tại USD/VND là 25,500. Bạn cần đổi bao nhiêu? 💱', timestamp: new Date(), status: 'sent' },
      ];
      const pick = demoIncoming[Math.floor(Math.random() * demoIncoming.length)];
      setMessages((prev) => [...prev, pick]);
    }, Math.random() * 20000 + 10000);

    return () => clearInterval(interval);
  }, [demoMode]);

  const handleSendMessage = () => {
    if (!inputValue.trim()) return;

    const newMessage: ChatMessage = {
      id: `msg-${Date.now()}`,
      sender: 'user',
      content: inputValue,
      timestamp: new Date(),
      status: 'sending',
    };

    setMessages((prev) => [...prev, newMessage]);
    setInputValue('');

    if (demoMode) {
      setTimeout(() => {
        const responses = [
          'Vâng, chúng tôi có hỗ trợ đổi EUR/VND với tỷ giá cạnh tranh. 💱',
          'Văn phòng mở cửa từ 9:00 - 18:00, Thứ 2 - Thứ 7. 🕘',
          'Bạn có thể thanh toán bằng chuyển khoản hoặc tiền mặt. ✅',
        ];
        const botResponse: ChatMessage = {
          id: `msg-${Date.now()}-bot`,
          sender: 'bot',
          content: responses[Math.floor(Math.random() * responses.length)],
          timestamp: new Date(),
          status: 'sent',
        };
        setMessages((prev) => [...prev, botResponse]);
      }, 2000);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] p-4">
      {/* Header */}
      <div className="bg-white rounded-lg shadow-sm p-4 mb-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold">💬 Live Chat {demoMode ? '(Demo)' : '(Real-time)'}</h2>
            <p className="text-sm text-gray-600 mt-1">
              {demoMode
                ? 'Simulated conversation — start persistent_chat_demo.py for real data'
                : 'Receiving live Telegram messages via WebSocket'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div
              className={`w-3 h-3 rounded-full ${
                isConnected ? 'bg-green-500' : 'bg-red-500'
              }`}
            />
            <span className="text-sm text-gray-600">
              {isConnected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
        </div>
        {demoMode && (
          <div className="mt-2 px-3 py-2 bg-yellow-50 border border-yellow-200 rounded text-xs text-yellow-800">
            ⚠️ Demo Mode: Showing simulated messages. Connect backend + persistent_chat_demo.py for live chat.
          </div>
        )}
      </div>

      {/* Chat Messages Area */}
      <div
        ref={chatContainerRef}
        className="flex-1 bg-gray-50 rounded-lg overflow-y-auto p-4 space-y-3 mb-4"
      >
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-400">
            <div className="text-center">
              <p className="text-lg">No messages yet</p>
              <p className="text-sm mt-2">
                {demoMode ? 'Demo messages will appear shortly...' : 'Waiting for Telegram messages...'}
              </p>
            </div>
          </div>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${
                msg.sender === 'user' ? 'justify-end' : 'justify-start'
              }`}
            >
              <div
                className={`max-w-[70%] px-4 py-2 rounded-lg ${
                  msg.sender === 'user'
                    ? 'bg-blue-600 text-white'
                    : 'bg-white text-gray-900 shadow-sm'
                }`}
              >
                {msg.senderName && (
                  <div className={`text-xs mb-1 ${msg.sender === 'user' ? 'text-blue-200' : 'text-gray-400'}`}>
                    {msg.senderName} {msg.account && `(${msg.account})`}
                  </div>
                )}
                <p className="whitespace-pre-wrap">{msg.content}</p>
                <div
                  className={`text-xs mt-1 flex items-center gap-2 ${
                    msg.sender === 'user' ? 'text-blue-200' : 'text-gray-400'
                  }`}
                >
                  <span>
                    {msg.timestamp.toLocaleTimeString('vi-VN', {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </span>
                  {msg.status === 'verified' && <span title="Verified">✅</span>}
                  {msg.status === 'sending' && <span className="animate-pulse">⏳</span>}
                </div>
              </div>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="bg-white rounded-lg shadow-sm p-3">
        <div className="flex gap-2">
          <textarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder={demoMode ? "Type your message... (Press Enter to send)" : "Manual reply (will be sent via Telegram)..."}
            className="flex-1 px-3 py-2 border rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
            rows={2}
          />
          <button
            onClick={handleSendMessage}
            disabled={!inputValue.trim()}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Send
          </button>
        </div>
        <div className="mt-2 text-xs text-gray-500 flex items-center gap-4">
          <span>💡 Tip: First message triggers verification</span>
          <span>🤖 AI powered by DeepSeek-V3</span>
          <span>🌐 Vietnamese/Chinese/English</span>
        </div>
      </div>
    </div>
  );
}
