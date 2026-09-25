'use client';

import { useState, useEffect, useRef } from 'react';
import { fetchAPI, type Conversation, wsClient } from '@/lib/api';

interface LiveMessage {
  id: string;
  direction: 'inbound' | 'outbound';
  content: string;
  sender_name: string;
  account: string;
  platform?: string;
  timestamp: string;
}

export default function ConversationsPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<Conversation | null>(null);
  const [loaded, setLoaded] = useState(false);
  // 只有真的连不上后端才设置；没有对话记录是正常状态
  const [backendError, setBackendError] = useState('');
  const [blockedUsers, setBlockedUsers] = useState<Set<string>>(new Set());
  const [liveMessages, setLiveMessages] = useState<LiveMessage[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll live messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [liveMessages]);

  async function loadConversations() {
    try {
      const data = await fetchAPI<Conversation[]>('/conversations');
      setConversations((data || []).filter((c) => !blockedUsers.has(c.target_user_id)));
      setBackendError('');
    } catch (e: any) {
      setConversations([]);
      setBackendError(e?.message || '后端不可达');
    }
    setLoaded(true);
  }

  useEffect(() => {
    loadConversations();
  }, []);

  // Connect WebSocket for live messages
  useEffect(() => {
    let mounted = true;

    const connectWS = async () => {
      try {
        await wsClient.connect();
        wsClient.on('telegram_message', (msg) => {
          if (!mounted) return;
          const liveMsg: LiveMessage = {
            id: `live-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
            direction: msg.direction,
            content: msg.content,
            sender_name: msg.sender_name || 'Unknown',
            account: msg.account || '',
            platform: msg.platform || 'telegram',
            timestamp: msg.timestamp,
          };
          setLiveMessages((prev) => [...prev.slice(-200), liveMsg]);
        });
      } catch {
        // WebSocket not available
      }
    };

    connectWS();
    return () => {
      mounted = false;
    };
  }, []);

  async function blockUser(conversationId: string, targetUserId: string) {
    try {
      await fetchAPI(`/conversations/${conversationId}/end`, { method: 'POST' });
    } catch {
      // ignore
    }
    setBlockedUsers((prev) => new Set(prev).add(targetUserId));
    setConversations((prev) => prev.filter((c) => c.id !== conversationId));
    if (selected?.id === conversationId) setSelected(null);
  }

  return (
    <div className="flex flex-col h-[calc(100vh-3rem)]">
      {backendError && (
        <div className="bg-rose-50 border border-rose-200 px-4 py-2 text-sm text-rose-800 mb-2 rounded">
          ⚠️ <strong>后端不可达:</strong> {backendError}
        </div>
      )}

      <div className="flex gap-4 flex-1 min-h-0">
        {/* Left: conversation list + live feed */}
        <div className="w-80 flex flex-col gap-3">
          {/* Historical conversations */}
          <div className="flex-1 bg-white rounded shadow overflow-hidden flex flex-col min-h-0">
            <div className="p-3 border-b flex items-center justify-between">
              <h3 className="font-semibold text-sm">历史对话</h3>
              <button onClick={loadConversations} className="text-xs text-blue-600 hover:underline">
                {loaded ? '刷新' : '加载'}
              </button>
            </div>
            <div className="flex-1 overflow-y-auto">
              {!loaded && <p className="p-3 text-gray-500 text-sm">点击加载获取对话列表</p>}
              {conversations.map((c) => (
                <div
                  key={c.id}
                  onClick={() => setSelected(c)}
                  className={`p-3 border-b cursor-pointer hover:bg-gray-50 text-sm relative ${
                    selected?.id === c.id ? 'bg-blue-50' : ''
                  }`}
                >
                  <div className="font-medium">{c.target_display_name || c.target_user_id}</div>
                  <div className="text-gray-500 text-xs mt-0.5">
                    {c.state} · {c.turn_count} turns · {c.account_id}
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); blockUser(c.id, c.target_user_id); }}
                    className="absolute right-2 top-2 text-xs px-2 py-1 bg-red-100 hover:bg-red-200 text-red-700 rounded"
                  >
                    拉黑
                  </button>
                </div>
              ))}
              {loaded && conversations.length === 0 && (
                <p className="p-3 text-gray-400 text-sm text-center">暂无历史对话</p>
              )}
            </div>
          </div>
        </div>

        {/* Center: selected conversation or live feed */}
        <div className="flex-1 flex flex-col gap-3 min-h-0">
          {/* Selected historical conversation */}
          {selected && (
            <div className="bg-white rounded shadow flex flex-col overflow-hidden flex-1 min-h-0">
              <div className="p-3 border-b flex items-center justify-between">
                <div>
                  <div className="font-semibold">{selected.target_display_name || selected.target_user_id}</div>
                  <div className="text-xs text-gray-500">State: {selected.state} · Account: {selected.account_id}</div>
                </div>
                <button onClick={() => setSelected(null)} className="text-xs text-gray-500 hover:text-gray-800">
                  ✕ 关闭
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-4 space-y-2">
                {selected.messages.map((m) => (
                  <div
                    key={m.id}
                    className={`max-w-[70%] px-3 py-2 rounded-lg text-sm ${
                      m.direction === 'outbound' ? 'ml-auto bg-blue-600 text-white' : 'mr-auto bg-gray-100'
                    }`}
                  >
                    <p>{m.content}</p>
                    <div className={`text-xs mt-1 ${m.direction === 'outbound' ? 'text-blue-200' : 'text-gray-400'}`}>
                      {new Date(m.created_at).toLocaleTimeString()}
                    </div>
                  </div>
                ))}
                {selected.messages.length === 0 && (
                  <p className="text-gray-400 text-sm text-center mt-8">暂无消息</p>
                )}
              </div>
            </div>
          )}

          {/* Live message feed (always visible) */}
          <div className={`bg-white rounded shadow flex flex-col overflow-hidden ${selected ? 'h-1/2' : 'flex-1'} min-h-0`}>
            <div className="p-3 border-b flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                <h3 className="font-semibold text-sm">实时消息流</h3>
              </div>
              <span className="text-xs text-gray-400">{liveMessages.length} 条消息</span>
            </div>
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {liveMessages.length === 0 ? (
                <div className="flex items-center justify-center h-full text-gray-400 text-sm">
                  <div className="text-center">
                    <p>等待实时消息...</p>
                    <p className="text-xs mt-1">启动持久化监听服务后，消息将在此处实时显示</p>
                  </div>
                </div>
              ) : (
                liveMessages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`flex ${msg.direction === 'outbound' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`max-w-[70%] px-3 py-2 rounded-lg text-sm ${
                        msg.direction === 'outbound'
                          ? 'bg-blue-600 text-white'
                          : 'bg-gray-100 text-gray-900'
                      }`}
                    >
                      <div className={`text-xs mb-1 ${msg.direction === 'outbound' ? 'text-blue-200' : 'text-gray-400'}`}>
                        {msg.sender_name} · {msg.account}
                        {msg.platform && msg.platform !== 'telegram' && ` · ${msg.platform}`}
                      </div>
                      <p className="whitespace-pre-wrap">{msg.content}</p>
                      <div className={`text-xs mt-1 ${msg.direction === 'outbound' ? 'text-blue-200' : 'text-gray-400'}`}>
                        {new Date(msg.timestamp).toLocaleTimeString()}
                      </div>
                    </div>
                  </div>
                ))
              )}
              <div ref={messagesEndRef} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
