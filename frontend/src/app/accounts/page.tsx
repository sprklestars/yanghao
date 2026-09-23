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

  // Login modal state
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [loginStep, setLoginStep] = useState<'platform' | 'phone' | 'code' | 'password'>('platform');
  const [loginPlatform, setLoginPlatform] = useState<'telegram' | 'facebook' | 'zalo'>('telegram');
  const [loginPhone, setLoginPhone] = useState('');
  const [loginCode, setLoginCode] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [loginSessionName, setLoginSessionName] = useState('');
  const [loginError, setLoginError] = useState('');
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginSuccess, setLoginSuccess] = useState('');

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

  const openLoginModal = () => {
    setLoginStep('platform');
    setLoginPlatform('telegram');
    setLoginPhone('');
    setLoginCode('');
    setLoginPassword('');
    setLoginSessionName('');
    setLoginError('');
    setLoginSuccess('');
    setShowLoginModal(true);
  };

  const handleSendCode = async () => {
    if (!loginPhone || !loginSessionName) {
      setLoginError('Please enter both session name and phone number');
      return;
    }
    setLoginLoading(true);
    setLoginError('');
    try {
      await accountAPI.telegramSendCode(loginPhone, loginSessionName);
      setLoginStep('code');
    } catch (e: any) {
      setLoginError(e?.message || 'Failed to send code');
    }
    setLoginLoading(false);
  };

  const handleVerifyCode = async () => {
    if (!loginCode) {
      setLoginError('Please enter the verification code');
      return;
    }
    setLoginLoading(true);
    setLoginError('');
    try {
      const result = await accountAPI.telegramVerifyCode(loginSessionName, loginCode, loginPassword || undefined);
      if (result.status === 'need_password') {
        setLoginStep('password');
        setLoginError('');
      } else if (result.status === 'success') {
        setLoginSuccess(`Logged in as ${result.username}`);
        setTimeout(() => { setShowLoginModal(false); loadData(); }, 1500);
      }
    } catch (e: any) {
      setLoginError(e?.message || 'Verification failed');
    }
    setLoginLoading(false);
  };

  const handlePasswordSubmit = async () => {
    if (!loginPassword) {
      setLoginError('Please enter your 2FA password');
      return;
    }
    await handleVerifyCode();
  };

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
        <div className="flex gap-2">
          <button onClick={openLoginModal} className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 text-sm">
            + 添加账号
          </button>
          <button onClick={loadData} className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm">
            刷新
          </button>
        </div>
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

      {/* Login Modal */}
      {showLoginModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold">添加新账号</h3>
              <button onClick={() => setShowLoginModal(false)} className="text-gray-400 hover:text-gray-600 text-xl">&times;</button>
            </div>

            {loginSuccess && (
              <div className="mb-4 p-3 bg-green-50 border border-green-200 text-green-800 rounded text-sm">
                {loginSuccess}
              </div>
            )}

            {loginError && (
              <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-800 rounded text-sm">
                {loginError}
              </div>
            )}

            {loginStep === 'platform' && (
              <div className="space-y-3">
                <p className="text-sm text-gray-600 mb-2">选择平台:</p>
                <div className="grid grid-cols-3 gap-3">
                  <button
                    onClick={() => { setLoginPlatform('telegram'); setLoginStep('phone'); }}
                    className="p-4 border-2 border-blue-500 bg-blue-50 rounded-lg hover:bg-blue-100 text-center"
                  >
                    <div className="text-2xl mb-1">✈️</div>
                    <div className="font-medium">Telegram</div>
                  </button>
                  <button
                    onClick={() => { setLoginPlatform('facebook'); setLoginStep('phone'); }}
                    className="p-4 border-2 border-gray-200 rounded-lg hover:bg-gray-50 text-center"
                  >
                    <div className="text-2xl mb-1">📘</div>
                    <div className="font-medium">Facebook</div>
                  </button>
                  <button
                    onClick={() => { setLoginPlatform('zalo'); setLoginStep('phone'); }}
                    className="p-4 border-2 border-gray-200 rounded-lg hover:bg-gray-50 text-center"
                  >
                    <div className="text-2xl mb-1">💬</div>
                    <div className="font-medium">Zalo</div>
                  </button>
                </div>
              </div>
            )}

            {loginStep === 'phone' && loginPlatform === 'telegram' && (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Session 名称</label>
                  <input
                    type="text"
                    value={loginSessionName}
                    onChange={(e) => setLoginSessionName(e.target.value)}
                    placeholder="例如: user5"
                    className="w-full px-3 py-2 border rounded focus:ring-2 focus:ring-blue-500 outline-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">手机号码 (含国际区号)</label>
                  <input
                    type="tel"
                    value={loginPhone}
                    onChange={(e) => setLoginPhone(e.target.value)}
                    placeholder="+8613800138000"
                    className="w-full px-3 py-2 border rounded focus:ring-2 focus:ring-blue-500 outline-none"
                  />
                </div>
                <div className="flex gap-2 pt-2">
                  <button onClick={() => setLoginStep('platform')} className="px-4 py-2 border rounded text-gray-600 hover:bg-gray-50">返回</button>
                  <button
                    onClick={handleSendCode}
                    disabled={loginLoading}
                    className="flex-1 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                  >
                    {loginLoading ? '发送中...' : '发送验证码'}
                  </button>
                </div>
              </div>
            )}

            {loginStep === 'phone' && loginPlatform === 'facebook' && (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Session 名称</label>
                  <input
                    type="text"
                    value={loginSessionName}
                    onChange={(e) => setLoginSessionName(e.target.value || 'fb_default')}
                    placeholder="fb_default"
                    className="w-full px-3 py-2 border rounded focus:ring-2 focus:ring-blue-500 outline-none"
                  />
                </div>
                <div className="p-3 bg-yellow-50 border border-yellow-200 rounded text-sm text-yellow-800">
                  Facebook 需要手动登录。请在终端运行:<br/>
                  <code className="bg-yellow-100 px-1 rounded">python quick_login_facebook.py {loginSessionName || 'fb_default'}</code>
                </div>
                <div className="flex gap-2 pt-2">
                  <button onClick={() => setLoginStep('platform')} className="px-4 py-2 border rounded text-gray-600 hover:bg-gray-50">返回</button>
                  <button onClick={() => { setShowLoginModal(false); loadData(); }} className="flex-1 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">完成</button>
                </div>
              </div>
            )}

            {loginStep === 'phone' && loginPlatform === 'zalo' && (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Session 名称</label>
                  <input
                    type="text"
                    value={loginSessionName}
                    onChange={(e) => setLoginSessionName(e.target.value)}
                    placeholder="例如: zalo_user1"
                    className="w-full px-3 py-2 border rounded focus:ring-2 focus:ring-blue-500 outline-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">手机号码</label>
                  <input
                    type="tel"
                    value={loginPhone}
                    onChange={(e) => setLoginPhone(e.target.value)}
                    placeholder="0912345678"
                    className="w-full px-3 py-2 border rounded focus:ring-2 focus:ring-blue-500 outline-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">密码</label>
                  <input
                    type="password"
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    placeholder="Zalo 登录密码"
                    className="w-full px-3 py-2 border rounded focus:ring-2 focus:ring-blue-500 outline-none"
                  />
                </div>
                <div className="p-3 bg-blue-50 border border-blue-200 rounded text-sm text-blue-800">
                  Zalo 使用手机号+密码登录，session 将保存到 sessions/ 目录。
                </div>
                <div className="flex gap-2 pt-2">
                  <button onClick={() => setLoginStep('platform')} className="px-4 py-2 border rounded text-gray-600 hover:bg-gray-50">返回</button>
                  <button
                    onClick={async () => {
                      if (!loginPhone || !loginPassword || !loginSessionName) {
                        setLoginError('请填写所有字段');
                        return;
                      }
                      setLoginLoading(true);
                      setLoginError('');
                      try {
                        const result = await fetchAPI('/accounts/zalo/login', {
                          method: 'POST',
                          body: JSON.stringify({ phone: loginPhone, password: loginPassword, session_name: loginSessionName }),
                        });
                        if (result.status === 'success') {
                          setLoginSuccess(`Zalo 登录成功: ${loginSessionName}`);
                          setTimeout(() => { setShowLoginModal(false); loadData(); }, 1500);
                        } else {
                          setLoginError(result.message || '登录失败');
                        }
                      } catch (e: any) {
                        setLoginError(e?.message || 'Zalo 登录失败');
                      }
                      setLoginLoading(false);
                    }}
                    disabled={loginLoading}
                    className="flex-1 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                  >
                    {loginLoading ? '登录中...' : '登录'}
                  </button>
                </div>
              </div>
            )}

            {loginStep === 'code' && (
              <div className="space-y-4">
                <p className="text-sm text-gray-600">验证码已发送到 {loginPhone}</p>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">验证码</label>
                  <input
                    type="text"
                    value={loginCode}
                    onChange={(e) => setLoginCode(e.target.value)}
                    placeholder="12345"
                    maxLength={5}
                    className="w-full px-3 py-2 border rounded text-center text-2xl tracking-widest focus:ring-2 focus:ring-blue-500 outline-none"
                  />
                </div>
                <div className="flex gap-2 pt-2">
                  <button onClick={() => setLoginStep('phone')} className="px-4 py-2 border rounded text-gray-600 hover:bg-gray-50">返回</button>
                  <button
                    onClick={handleVerifyCode}
                    disabled={loginLoading}
                    className="flex-1 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                  >
                    {loginLoading ? '验证中...' : '验证'}
                  </button>
                </div>
              </div>
            )}

            {loginStep === 'password' && (
              <div className="space-y-4">
                <p className="text-sm text-gray-600">此账号开启了两步验证，请输入密码</p>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">2FA 密码</label>
                  <input
                    type="password"
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    placeholder="输入两步验证密码"
                    className="w-full px-3 py-2 border rounded focus:ring-2 focus:ring-blue-500 outline-none"
                  />
                </div>
                <div className="flex gap-2 pt-2">
                  <button onClick={() => setLoginStep('code')} className="px-4 py-2 border rounded text-gray-600 hover:bg-gray-50">返回</button>
                  <button
                    onClick={handlePasswordSubmit}
                    disabled={loginLoading}
                    className="flex-1 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                  >
                    {loginLoading ? '验证中...' : '确认'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
