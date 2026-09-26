'use client';

import { useEffect, useRef, useState } from 'react';
import { fetchAPI, wsClient, type Conversation, type Message } from '@/lib/api';

export default function LiveChatPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [backendError, setBackendError] = useState('');
  const [inputValue, setInputValue] = useState('');
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const selected = conversations.find((c) => c.id === selectedId) || null;

  async function loadConversations() {
    try {
      const data = await fetchAPI<Conversation[]>('/conversations');
      setConversations(data || []);
      setSelectedId((current) => current || data?.[0]?.id || null);
      setLoaded(true);
      setBackendError('');
    } catch (e: any) {
      setConversations([]);
      setLoaded(true);
      setBackendError(e?.message || '后端不可达');
    }
  }

  useEffect(() => {
    loadConversations();

    let mounted = true;
    const connectWS = async () => {
      try {
        await wsClient.connect();
        if (!mounted) return;
        setIsConnected(true);
        wsClient.on('telegram_message', (msg) => {
          if (!mounted) return;
          const targetId = String(msg.sender_id ?? '');
          const created = msg.timestamp
            ? new Date(msg.timestamp).toISOString()
            : new Date().toISOString();
          const live: Message = {
            id: `ws-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
            direction: msg.direction === 'inbound' ? 'inbound' : 'outbound',
            content: msg.content,
            created_at: created,
          };
          setConversations((prev) =>
            prev.map((c) => {
              if (c.target_user_id === targetId && msg.account === c.account_name) {
                return { ...c, messages: [...c.messages, live] };
              }
              return c;
            }),
          );
        });
      } catch {
        if (mounted) setIsConnected(false);
      }
    };
    connectWS();

    return () => {
      mounted = false;
      wsClient.disconnect();
    };
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [selected?.messages.length, selectedId]);

  async function handleSend() {
    const text = inputValue.trim();
    if (!text || !selectedId) return;
    setSending(true);
    setNotice('');
    try {
      await fetchAPI(`/conversations/${selectedId}/reply`, {
        method: 'POST',
        body: JSON.stringify({ text }),
      });
      setInputValue('');
      loadConversations();
    } catch (e: any) {
      setNotice(`发送失败：${e?.message || '请检查后端服务'}`);
    } finally {
      setSending(false);
    }
  }

  const messages = selected?.messages || [];

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] p-4">
      <div className="bg-white rounded-lg shadow-sm p-4 mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold">💬 实时对话</h2>
          <p className="text-sm text-slate-500 mt-1">
            真实会话：历史消息来自数据库，新消息通过 WebSocket 实时推送
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-emerald-500' : 'bg-rose-500'}`} />
          <span className="text-sm text-slate-600">{isConnected ? 'Connected' : 'Disconnected'}</span>
          <button onClick={loadConversations} className="ml-2 text-sm text-blue-600 hover:underline">
            刷新
          </button>
        </div>
      </div>

      {backendError && (
        <div className="mb-4 px-4 py-2 bg-rose-50 border border-rose-200 rounded text-sm text-rose-800">
          ⚠️ {backendError}
        </div>
      )}

      <div className="flex gap-4 flex-1 min-h-0">
        <div className="w-72 bg-white rounded-lg shadow-sm overflow-y-auto flex flex-col">
          <div className="p-3 border-b text-sm font-semibold text-slate-700">会话列表</div>
          {!loaded && <p className="p-3 text-sm text-slate-500">加载中…</p>}
          {loaded && conversations.length === 0 && (
            <p className="p-3 text-sm text-slate-500">
              还没有会话，等任务外呼或有人主动私聊后这里会出现记录。
            </p>
          )}
          {conversations.map((c) => (
            <div
              key={c.id}
              onClick={() => setSelectedId(c.id)}
              className={`p-3 border-b cursor-pointer hover:bg-slate-50 text-sm ${selectedId === c.id ? 'bg-blue-50' : ''}`}
            >
              <div className="font-medium text-slate-800">{c.target_display_name || c.target_user_id}</div>
              <div className="text-xs text-slate-500 mt-0.5">
                账号 {c.account_name || '—'} · {c.turn_count} 轮
              </div>
            </div>
          ))}
        </div>

        <div className="flex-1 flex flex-col bg-slate-50 rounded-lg overflow-hidden">
          <div className="bg-white border-b px-4 py-2 text-sm font-medium text-slate-700">
            {selected
              ? `与 ${selected.target_display_name || selected.target_user_id} 的对话（账号 ${selected.account_name || '—'}）`
              : '请选择左侧会话'}
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {messages.length === 0 && (
              <div className="flex items-center justify-center h-full text-slate-400 text-sm">
                还没有消息
              </div>
            )}
            {messages.map((m) => (
              <div key={m.id} className={`flex ${m.direction === 'inbound' ? 'justify-start' : 'justify-end'}`}>
                <div
                  className={`max-w-[70%] px-4 py-2 rounded-lg ${
                    m.direction === 'inbound' ? 'bg-white text-slate-900 shadow-sm' : 'bg-blue-600 text-white'
                  }`}
                >
                  <p className="whitespace-pre-wrap">{m.content}</p>
                  <div className={`text-xs mt-1 ${m.direction === 'inbound' ? 'text-slate-400' : 'text-blue-200'}`}>
                    {new Date(m.created_at).toLocaleString('zh-CN', { hour12: false })}
                  </div>
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          <div className="bg-white border-t p-3">
            {notice && <p className="mb-2 text-xs text-rose-600">{notice}</p>}
            <div className="flex gap-2">
              <input
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
                disabled={!selectedId}
                placeholder={selectedId ? '输入要发送给目标的消息（回车发送）' : '先选择会话'}
                className="flex-1 px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                onClick={handleSend}
                disabled={!selectedId || !inputValue.trim() || sending}
                className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                {sending ? '发送中…' : '发送'}
              </button>
            </div>
            <p className="mt-2 text-xs text-slate-500">
              手动回复会以该会话所属账号发出；若账号正被常驻服务/任务占用，会提示先停止。
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
