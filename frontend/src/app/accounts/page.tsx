'use client';

import { useState, useEffect, useRef } from 'react';
import { type Account, DEMO_ACCOUNTS, accountAPI, serviceAPI, type ServiceStatus, wsClient } from '@/lib/api';

const PLATFORM_ICONS: Record<string, string> = {
  telegram: '✈️',
  facebook: '📘',
  zalo: '💬',
};

interface LiveMessage {
  id: string;
  direction: 'inbound' | 'outbound';
  content: string;
  sender_name: string;
  account: string;
  platform?: string;
  timestamp: string;
}

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [services, setServices] = useState<ServiceStatus[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [demoMode, setDemoMode] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [logView, setLogView] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [chatView, setChatView] = useState<string | null>(null);
  const [liveMessages, setLiveMessages] = useState<LiveMessage[]>([]);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const loadData = async () => {
    try {
      const [accData, svcData] = await Promise.all([
        accountAPI.list(),
        serviceAPI.status(),
      ]);
      if (accData && accData.length > 0) {
        setAccounts(accData);
        setDemoMode(false);
      } else {
        setAccounts(DEMO_ACCOUNTS);
        setDemoMode(true);
      }
      setServices(svcData || []);
    } catch {
      setAccounts(DEMO_ACCOUNTS);
      setDemoMode(true);
    }
    setLoaded(true);
  };

  useEffect(() => { loadData(); }, []);

  // WebSocket for live messages
  useEffect(() => {
    let mounted = true;
    const connectWS = async () => {
      try {
        await wsClient.connect();
        wsClient.on('telegram_message', (msg) => {
          if (!mounted) return;
          setLiveMessages((prev) => [...prev.slice(-500), {
            id: `live-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
            direction: msg.direction,
            content: msg.content,
            sender_name: msg.sender_name || 'Unknown',
            account: msg.account || '',
            platform: msg.platform || 'telegram',
            timestamp: msg.timestamp,
          }]);
        });
      } catch { /* ignore */ }
    };
    connectWS();
    return () => { mounted = false; };
  }, []);

  // Auto-scroll chat
  useEffect(() => {
    if (chatView) {
      chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [liveMessages, chatView]);

  const getServiceForPlatform = (platform: string) =>
    services.find((s) => s.platform === platform);

  const handleStart = async (platform: string) => {
    setActionLoading(platform);
    try { await serviceAPI.start(platform); await loadData(); }
    catch (e) { console.error('Start failed:', e); }
    setActionLoading(null);
  };

  const handleStop = async (platform: string) => {
    setActionLoading(platform);
    try { await serviceAPI.stop(platform); await loadData(); }
    catch (e) { console.error('Stop failed:', e); }
    setActionLoading(null);
  };

  const handleViewLogs = async (platform: string) => {
    if (logView === platform) { setLogView(null); return; }
    try {
      const data = await serviceAPI.logs(platform, 30);
      setLogs(data.logs || []);
      setLogView(platform);
    } catch { setLogs(['Failed to load logs']); setLogView(platform); }
  };

  const getMessagesForAccount = (accountId: string) =>
    liveMessages.filter((m) => m.account === accountId);

  const getHealthColor = (health: string) => {
    switch (health) {
      case 'green': return 'bg-green-100 text-green-800';
      case 'yellow': return 'bg-yellow-100 text-yellow-800';
      case 'red': return 'bg-red-100 text-red-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const getDaysSince = (createdAt: string) => {
    const ts = typeof createdAt === 'number' ? createdAt * 1000 : new Date(createdAt).getTime();
    return Math.floor((Date.now() - ts) / (1000 * 60 * 60 * 24));
  };

  const getWarmingStage = (days: number) => {
    if (days < 7) return { label: '新号期', color: 'text-yellow-600' };
    if (days < 30) return { label: '温号期', color: 'text-orange-600' };
    if (days < 90) return { label: '稳定期', color: 'text-blue-600' };
    return { label: '成熟期', color: 'text-green-600' };
  };

  const platforms = [...new Set(accounts.map((a) => a.platform))];

  return (
    <div className="flex flex-col h-[calc(100vh-3rem)]">
      {demoMode && (
        <div className="bg-yellow-50 border-b border-yellow-200 px-4 py-2 text-sm text-yellow-800 mb-4 rounded">
          💡 <strong>演示模式:</strong> 后端不可达，显示模拟数据。
        </div>
      )}
      {!demoMode && (
        <div className="bg-green-50 border-b border-green-200 px-4 py-2 text-sm text-green-800 mb-4 rounded">
          ✅ <strong>实时模式:</strong> 显示已登录账号和持久化服务状态
        </div>
      )}

      <div className="flex items-center justify-between mb-4">
        <h2 className="text-2xl font-bold">账号管理</h2>
        <button onClick={loadData} className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm">
          刷新
        </button>
      </div>

      {!loaded ? (
        <p className="text-gray-500">加载中...</p>
      ) : (
        <div className="space-y-6 overflow-y-auto">
          {platforms.map((platform) => {
            const svc = getServiceForPlatform(platform);
            const platformAccounts = accounts.filter((a) => a.platform === platform);
            const isRunning = svc?.running ?? false;
            const isLoading = actionLoading === platform;

            return (
              <div key={platform} className="bg-white rounded-lg shadow">
                {/* Platform header */}
                <div className="flex items-center justify-between p-4 border-b">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{PLATFORM_ICONS[platform] || '🔗'}</span>
                    <h3 className="text-lg font-semibold capitalize">{platform}</h3>
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${isRunning ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'}`}>
                      {isRunning ? '运行中' : '未运行'}
                    </span>
                    {svc?.pid && isRunning && <span className="text-xs text-gray-400">PID: {svc.pid}</span>}
                  </div>
                  <div className="flex items-center gap-2">
                    {!isRunning ? (
                      <button onClick={() => handleStart(platform)} disabled={isLoading}
                        className="px-3 py-1.5 bg-green-600 text-white rounded text-sm hover:bg-green-700 disabled:opacity-50">
                        {isLoading ? '启动中...' : '▶ 启动监听'}
                      </button>
                    ) : (
                      <button onClick={() => handleStop(platform)} disabled={isLoading}
                        className="px-3 py-1.5 bg-red-600 text-white rounded text-sm hover:bg-red-700 disabled:opacity-50">
                        {isLoading ? '停止中...' : '⏹ 停止'}
                      </button>
                    )}
                    <button onClick={() => handleViewLogs(platform)}
                      className={`px-3 py-1.5 rounded text-sm ${logView === platform ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}>
                      📋 日志
                    </button>
                  </div>
                </div>

                {/* Log viewer */}
                {logView === platform && (
                  <div className="bg-gray-900 text-green-400 p-3 text-xs font-mono max-h-48 overflow-y-auto border-b">
                    {logs.length === 0 ? <p className="text-gray-500">暂无日志</p> : logs.map((line, i) => <div key={i}>{line}</div>)}
                  </div>
                )}

                {/* Account cards */}
                <div className="p-4 grid gap-3">
                  {platformAccounts.map((account) => {
                    const days = getDaysSince(account.created_at);
                    const stage = getWarmingStage(days);
                    const accountMsgs = getMessagesForAccount(account.id);
                    const isChatOpen = chatView === account.id;

                    return (
                      <div key={account.id} className="border rounded-lg overflow-hidden">
                        <div className="p-3 flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <div>
                              <div className="flex items-center gap-2">
                                <span className="font-semibold">{account.username}</span>
                                <span className={`px-2 py-0.5 rounded text-xs ${getHealthColor(account.health)}`}>
                                  {account.health.toUpperCase()}
                                </span>
                              </div>
                              <div className="text-xs text-gray-500 mt-1">
                                {stage.label} ({days}天) · {account.is_active ? '✅ 活跃' : '❌ 停用'}
                                {account.proxy_url && ` · ${account.proxy_url}`}
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-gray-400">{account.session_file}</span>
                            <button
                              onClick={() => setChatView(isChatOpen ? null : account.id)}
                              className={`px-3 py-1.5 rounded text-sm ${isChatOpen ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
                            >
                              💬 {isChatOpen ? '收起对话' : '查看对话'}
                            </button>
                          </div>
                        </div>

                        {/* Per-account live chat panel */}
                        {isChatOpen && (
                          <div className="border-t bg-gray-50">
                            <div className="p-2 border-b flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                                <span className="text-xs font-medium text-gray-600">
                                  {account.username} 实时消息
                                </span>
                              </div>
                              <span className="text-xs text-gray-400">{accountMsgs.length} 条</span>
                            </div>
                            <div className="max-h-64 overflow-y-auto p-3 space-y-2">
                              {accountMsgs.length === 0 ? (
                                <p className="text-gray-400 text-sm text-center py-4">
                                  暂无消息，等待对方发送...
                                </p>
                              ) : (
                                accountMsgs.map((msg) => (
                                  <div key={msg.id} className={`flex ${msg.direction === 'outbound' ? 'justify-end' : 'justify-start'}`}>
                                    <div className={`max-w-[75%] px-3 py-2 rounded-lg text-sm ${
                                      msg.direction === 'outbound' ? 'bg-blue-600 text-white' : 'bg-white border text-gray-900'
                                    }`}>
                                      <div className={`text-xs mb-0.5 ${msg.direction === 'outbound' ? 'text-blue-200' : 'text-gray-400'}`}>
                                        {msg.direction === 'inbound' ? msg.sender_name : 'Bot'} ·{' '}
                                        {new Date(msg.timestamp).toLocaleTimeString()}
                                      </div>
                                      <p className="whitespace-pre-wrap">{msg.content}</p>
                                    </div>
                                  </div>
                                ))
                              )}
                              <div ref={chatEndRef} />
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}

          {accounts.length === 0 && <p className="text-gray-500 text-center py-8">暂无账号数据</p>}
        </div>
      )}
    </div>
  );
}
