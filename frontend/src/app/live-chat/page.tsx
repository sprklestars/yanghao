'use client';

import { useState, useEffect, useRef } from 'react';

interface ChatMessage {
  id: string;
  sender: 'user' | 'bot';
  content: string;
  timestamp: Date;
  status?: 'sending' | 'sent' | 'verified' | 'error';
}

const DEMO_MODE = true;

// Demo messages for simulation
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
  {
    id: '5',
    sender: 'user',
    content: 'Tôi muốn đổi 500 USD',
    timestamp: new Date(Date.now() - 280000),
    status: 'verified',
  },
  {
    id: '6',
    sender: 'bot',
    content: 'Với 500 USD, bạn sẽ nhận được khoảng 12,250,000 VND theo tỷ giá hiện tại. 💰\n\nBạn có thể đến văn phòng chúng tôi tại:\n📍 123 Nguyễn Huệ, Quận 1, TP.HCM\n\nHoặc chúng tôi có thể giao dịch qua chuyển khoản ngân hàng. Bạn prefer cách nào? 😊',
    timestamp: new Date(Date.now() - 275000),
    status: 'verified',
  },
];

export default function LiveChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const [verificationState, setVerificationState] = useState<'idle' | 'pending' | 'verified'>('idle');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Load demo messages on mount
  useEffect(() => {
    if (DEMO_MODE) {
      setMessages(DEMO_MESSAGES);
      setIsConnected(true);
      setVerificationState('verified');
    }
  }, []);

  // Simulate incoming messages in demo mode
  useEffect(() => {
    if (!DEMO_MODE) return;

    const simulateIncomingMessage = () => {
      const newMessage: ChatMessage = {
        id: `msg-${Date.now()}`,
        sender: Math.random() > 0.5 ? 'user' : 'bot',
        content: getRandomDemoMessage(),
        timestamp: new Date(),
        status: 'verified',
      };
      setMessages((prev) => [...prev, newMessage]);
    };

    // Random interval between 10-30 seconds
    const interval = setInterval(simulateIncomingMessage, Math.random() * 20000 + 10000);
    return () => clearInterval(interval);
  }, []);

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

    // Simulate bot response after delay
    setTimeout(() => {
      const botResponse: ChatMessage = {
        id: `msg-${Date.now()}-bot`,
        sender: 'bot',
        content: getBotResponse(inputValue),
        timestamp: new Date(),
        status: 'sent',
      };
      setMessages((prev) => [...prev, botResponse]);
    }, 2000);
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
            <h2 className="text-xl font-bold">💬 Live Chat Demo - Printer Account</h2>
            <p className="text-sm text-gray-600 mt-1">
              Real-time AI conversation with arithmetic verification
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
        {DEMO_MODE && (
          <div className="mt-2 px-3 py-2 bg-yellow-50 border border-yellow-200 rounded text-xs text-yellow-800">
            ⚠️ Demo Mode: Showing simulated messages. Connect real Telegram session to see live chat.
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
                Send a message to start the conversation
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
                  {msg.status === 'verified' && (
                    <span title="Verified">✅</span>
                  )}
                  {msg.status === 'sending' && (
                    <span className="animate-pulse">⏳</span>
                  )}
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
            placeholder="Type your message... (Press Enter to send)"
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

// Helper functions for demo
function getRandomDemoMessage(): string {
  const messages = [
    'Cảm ơn bạn rất nhiều! 😊',
    'Tôi sẽ đến văn phòng lúc 3 giờ chiều nay.',
    'Bạn có nhận đổi EUR không?',
    'Tỷ giá hôm nay thế nào?',
    'OK, tôi sẽ chuyển khoản ngay.',
    'Địa chỉ cụ thể ở đâu vậy?',
  ];
  return messages[Math.floor(Math.random() * messages.length)];
}

function getBotResponse(userMessage: string): string {
  const responses = [
    'Vâng, chúng tôi có hỗ trợ đổi EUR/VND với tỷ giá cạnh tranh. 💱',
    'Văn phòng chúng tôi mở cửa từ 9:00 - 18:00, Thứ 2 - Thứ 7. 🕘',
    'Bạn có thể thanh toán bằng chuyển khoản hoặc tiền mặt. Cả hai đều được chấp nhận! ✅',
    'Để tôi kiểm tra tỷ giá mới nhất cho bạn nhé... ⏳',
    'Cảm ơn bạn đã quan tâm dịch vụ của chúng tôi! 🙏',
  ];
  return responses[Math.floor(Math.random() * responses.length)];
}
