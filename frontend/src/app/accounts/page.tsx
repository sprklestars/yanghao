'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { type Account, type ReplyPolicy, type PersonaPreset, accountAPI, serviceAPI, type ServiceStatus, wsClient, fetchAPI } from '@/lib/api';

const PLATFORM_CONFIG: Record<string, { icon: string; color: string; label: string }> = {
  telegram: { icon: '✈️', color: 'from-sky-500 to-blue-600', label: 'Telegram' },
  facebook: { icon: '📘', color: 'from-blue-600 to-indigo-700', label: 'Facebook' },
  zalo: { icon: '💬', color: 'from-cyan-500 to-teal-600', label: 'Zalo' },
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
  // 会话名会拼成 sessions/<name>.session，字符集必须和后端 _require_valid_session_name 一致
  const SESSION_NAME_RE = /^[a-z0-9][a-z0-9_-]{0,47}$/;
  const deriveSessionName = (phone: string) => {
    const digits = phone.replace(/\D/g, '');
    return digits ? `tg${digits}` : '';
  };
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [services, setServices] = useState<ServiceStatus[]>([]);
  const [loaded, setLoaded] = useState(false);
  // 后端不可达时才设置；账号列表为空是正常状态，不再当成"演示模式"
  const [backendError, setBackendError] = useState('');
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  // 启动/停止平台服务失败时的提示（以前只 console.error，界面上看着像"没反应"）
  const [serviceError, setServiceError] = useState('');
  // 账号级操作的失败提示（例如会话文件被占用导致删不掉）
  const [pageError, setPageError] = useState('');
  const [logView, setLogView] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [chatView, setChatView] = useState<string | null>(null);
  const [liveMessages, setLiveMessages] = useState<LiveMessage[]>([]);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const personaBtnRef = useRef<HTMLButtonElement>(null);

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
  const [testConnLoading, setTestConnLoading] = useState(false);
  const [testConnResult, setTestConnResult] = useState<{ ok: boolean; message: string } | null>(null);

  // Per-account health check & edit
  const [healthCheckLoading, setHealthCheckLoading] = useState<string | null>(null);
  const [healthCheckResults, setHealthCheckResults] = useState<Record<string, { ok: boolean; message: string }>>({});
  const [editingName, setEditingName] = useState<string | null>(null);
  const [editNameValue, setEditNameValue] = useState('');
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [personaPresets, setPersonaPresets] = useState<PersonaPreset[]>([]);
  const [personaSelector, setPersonaSelector] = useState<string | null>(null);

  const loadData = async () => {
    try {
      const [accData, svcData] = await Promise.all([
        accountAPI.list(),
        serviceAPI.status(),
      ]);
      setAccounts(accData || []);
      setServices(svcData || []);
      setBackendError('');
      try {
        const pData = await accountAPI.listPersonas();
        if (pData?.personas) setPersonaPresets(pData.personas);
      } catch { /* ignore */ }
    } catch (e: any) {
      setAccounts([]);
      setServices([]);
      setBackendError(e?.message || '后端不可达');
    }
    setLoaded(true);
  };

  useEffect(() => { loadData(); }, []);

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

  useEffect(() => {
    if (chatView) chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [liveMessages, chatView]);

  const getServiceForPlatform = (platform: string) => services.find((s) => s.platform === platform);

  const handleStart = async (platform: string, session?: string) => {
    setActionLoading(platform);
    setServiceError('');
    try {
      await serviceAPI.start(platform, session);
      await loadData();
    } catch (e: any) {
      console.error('Start failed:', e);
      setServiceError(`启动 ${platform} 服务失败：${e?.message || e}`);
    }
    setActionLoading(null);
  };

  const handleStop = async (platform: string) => {
    setActionLoading(platform);
    setServiceError('');
    try {
      await serviceAPI.stop(platform);
      await loadData();
    } catch (e: any) {
      console.error('Stop failed:', e);
      setServiceError(`停止 ${platform} 服务失败：${e?.message || e}`);
    }
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

  const getMessagesForAccount = (accountId: string) => liveMessages.filter((m) => m.account === accountId);

  const getHealthBadge = (health: string) => {
    switch (health) {
      case 'green': return { bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200', dot: 'bg-emerald-500', label: '健康' };
      case 'yellow': return { bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200', dot: 'bg-amber-500', label: '警告' };
      case 'red': return { bg: 'bg-rose-50', text: 'text-rose-700', border: 'border-rose-200', dot: 'bg-rose-500', label: '危险' };
      case 'black': return { bg: 'bg-gray-900', text: 'text-white', border: 'border-gray-700', dot: 'bg-gray-900', label: '封禁' };
      default: return { bg: 'bg-slate-50', text: 'text-slate-600', border: 'border-slate-200', dot: 'bg-slate-400', label: '未知' };
    }
  };

  const getDaysSince = (createdAt?: string | number) => {
    if (createdAt === undefined || createdAt === null) return 0;
    const ts = typeof createdAt === 'number' ? createdAt * 1000 : new Date(createdAt).getTime();
    if (Number.isNaN(ts)) return 0;
    return Math.floor((Date.now() - ts) / (1000 * 60 * 60 * 24));
  };

  const getWarmingStage = (days: number) => {
    if (days < 7) return { label: '新号期', color: 'text-amber-600', bg: 'bg-amber-50' };
    if (days < 30) return { label: '温号期', color: 'text-orange-600', bg: 'bg-orange-50' };
    if (days < 90) return { label: '稳定期', color: 'text-blue-600', bg: 'bg-blue-50' };
    return { label: '成熟期', color: 'text-emerald-600', bg: 'bg-emerald-50' };
  };

  const platforms = Array.from(new Set(accounts.map((a) => a.platform)));

  const handleAccountHealthCheck = async (account: Account) => {
    setHealthCheckLoading(account.id);
    try {
      const result = await accountAPI.checkSession(account.id);
      setHealthCheckResults((prev) => ({ ...prev, [account.id]: { ok: result.valid, message: result.message } }));
      if (!result.valid) loadData();
    } catch (e: any) {
      setHealthCheckResults((prev) => ({ ...prev, [account.id]: { ok: false, message: e?.message || '检测失败' } }));
    } finally {
      setHealthCheckLoading(null);
    }
  };

  const handleSaveDisplayName = async (accountId: string) => {
    try {
      await accountAPI.updateDisplayName(accountId, editNameValue);
      setEditingName(null);
      loadData();
    } catch (e) {
      console.error('Failed to save display name:', e);
    }
  };

  const handleDeleteAccount = async (accountId: string) => {
    try {
      await accountAPI.delete(accountId);
      setDeleteConfirm(null);
      setPageError('');
      loadData();
    } catch (e: any) {
      console.error('Failed to delete account:', e);
      setPageError(`删除账号 ${accountId} 失败：${e?.message || e}`);
    }
  };

  const handleToggleReplyPolicy = async (accountId: string, field: keyof ReplyPolicy) => {
    const account = accounts.find((a) => a.id === accountId);
    if (!account) return;
    const current = account.reply_policy || { private: true, groups: false, channels: false, bots: false };
    const updated = { ...current, [field]: !current[field] };
    try {
      await accountAPI.updateReplyPolicy(accountId, updated);
      loadData();
    } catch (e) {
      console.error('Failed to update reply policy:', e);
    }
  };

  const handleTogglePause = async (accountId: string) => {
    const account = accounts.find((a) => a.id === accountId);
    if (!account) return;
    try {
      await accountAPI.setPaused(accountId, !account.paused);
      loadData();
    } catch (e) {
      console.error('Failed to toggle pause:', e);
    }
  };

  const handleSetPersona = async (accountId: string, personaKey: string) => {
    try {
      await accountAPI.setPersona(accountId, personaKey);
      setPersonaSelector(null);
      loadData();
    } catch (e) {
      console.error('Failed to set persona:', e);
    }
  };

  // Login handlers
  const openLoginModal = () => {
    setLoginStep('platform');
    setLoginPlatform('telegram');
    setLoginPhone('');
    setLoginCode('');
    setLoginPassword('');
    setLoginSessionName('');
    setLoginError('');
    setLoginSuccess('');
    setTestConnResult(null);
    setShowLoginModal(true);
  };

  const handleTestConnection = async () => {
    setTestConnLoading(true);
    setTestConnResult(null);
    try {
      const result = await accountAPI.telegramTestConnection(loginSessionName || undefined);
      setTestConnResult({ ok: result.connected, message: result.message });
    } catch (e: any) {
      setTestConnResult({ ok: false, message: e?.message || '测试请求失败' });
    } finally {
      setTestConnLoading(false);
    }
  };

  const handleSendCode = async () => {
    const sessionName = loginSessionName.trim();
    if (!SESSION_NAME_RE.test(sessionName)) {
      setLoginError('Session 名称只能用 1-48 位小写字母、数字、下划线或短横线，并以字母/数字开头');
      return;
    }
    if (!loginPhone) { setLoginError('请输入手机号码'); return; }
    setLoginLoading(true);
    setLoginError('');
    try {
      await accountAPI.telegramSendCode(loginPhone, sessionName);
      setLoginStep('code');
    } catch (e: any) {
      const msg = e?.message || '';
      const match = msg.match(/- (.+)$/);
      setLoginError(match ? match[1] : msg || '发送验证码失败，请稍后重试');
    } finally {
      setLoginLoading(false);
    }
  };

  const handleVerifyCode = async () => {
    if (!loginCode) { setLoginError('请输入验证码'); return; }
    setLoginLoading(true);
    setLoginError('');
    try {
      const result = await accountAPI.telegramVerifyCode(loginSessionName, loginCode, loginPassword || undefined);
      if (result.status === 'need_password') {
        setLoginStep('password');
        setLoginError('');
      } else if (result.status === 'success') {
        setLoginSuccess(`登录成功: ${result.username}`);
        setTimeout(() => { setShowLoginModal(false); loadData(); }, 1500);
      } else {
        setLoginError(result.message || `未知状态: ${result.status}`);
      }
    } catch (e: any) {
      const msg = e?.message || '';
      const match = msg.match(/- (.+)$/);
      setLoginError(match ? match[1] : msg || '验证失败，请重试');
    } finally {
      setLoginLoading(false);
    }
  };

  const handlePasswordSubmit = async () => {
    if (!loginPassword) { setLoginError('请输入两步验证密码'); return; }
    setLoginLoading(true);
    setLoginError('');
    try {
      const result = await accountAPI.telegramVerifyCode(loginSessionName, '', loginPassword);
      if (result.status === 'success') {
        setLoginSuccess(`登录成功: ${result.username}`);
        setTimeout(() => { setShowLoginModal(false); loadData(); }, 1500);
      } else {
        setLoginError(result.message || '密码验证失败');
      }
    } catch (e: any) {
      const msg = e?.message || '';
      const match = msg.match(/- (.+)$/);
      setLoginError(match ? match[1] : msg || '密码验证失败，请重试');
    } finally {
      setLoginLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-3rem)]">
      {/* Status banner */}
      <div className={`mb-6 px-4 py-2.5 rounded-lg text-sm font-medium flex items-center gap-2 ${
        backendError ? 'bg-rose-50 text-rose-800 border border-rose-200' : 'bg-emerald-50 text-emerald-800 border border-emerald-200'
      }`}>
        <span>{backendError ? '⚠️' : '✅'}</span>
        {backendError
          ? `后端不可达 — 请确认 API 已在 8000 端口启动（${backendError}）`
          : '已连接后端服务'}
      </div>
      {serviceError && (
        <div className="mb-6 px-4 py-2.5 rounded-lg text-sm font-medium bg-rose-50 text-rose-800 border border-rose-200 whitespace-pre-wrap">
          ⚠️ {serviceError}
        </div>
      )}
      {pageError && (
        <div className="mb-6 px-4 py-2.5 rounded-lg text-sm font-medium bg-rose-50 text-rose-800 border border-rose-200 whitespace-pre-wrap">
          ⚠️ {pageError}
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-slate-900">账号管理</h2>
          <p className="text-sm text-slate-500 mt-1">管理平台账号、监控健康状态</p>
        </div>
        <div className="flex gap-3">
          <button onClick={loadData} className="px-4 py-2 bg-white border border-slate-200 text-slate-700 rounded-lg hover:bg-slate-50 text-sm font-medium transition-colors shadow-sm">
            刷新
          </button>
          <button onClick={openLoginModal} className="px-4 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800 text-sm font-medium transition-colors shadow-sm">
            + 添加账号
          </button>
        </div>
      </div>

      {!loaded ? (
        <div className="flex items-center justify-center py-20">
          <div className="animate-spin w-6 h-6 border-2 border-slate-300 border-t-slate-900 rounded-full" />
          <span className="ml-3 text-slate-500">加载中...</span>
        </div>
      ) : (
        <div className="space-y-6 overflow-y-auto pb-8">
          {platforms.map((platform) => {
            const svc = getServiceForPlatform(platform);
            const platformAccounts = accounts.filter((a) => a.platform === platform);
            const isRunning = svc?.running ?? false;
            const isLoading = actionLoading === platform;
            const config = PLATFORM_CONFIG[platform] || { icon: '🔗', color: 'from-gray-500 to-gray-600', label: platform };

            return (
              <div key={platform} className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                {/* Platform header */}
                <div className={`bg-gradient-to-r ${config.color} px-5 py-3.5 flex items-center justify-between`}>
                  <div className="flex items-center gap-3 text-white">
                    <span className="text-xl">{config.icon}</span>
                    <h3 className="font-semibold text-base">{config.label}</h3>
                    <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${isRunning ? 'bg-white/20 text-white' : 'bg-black/20 text-white/70'}`}>
                      {isRunning
                        ? `运行中${svc?.session ? ` · @${svc.session}` : ''}`
                        : '未运行'}
                    </span>
                    <span className="text-xs text-white/60">{platformAccounts.length} 个账号</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {platform === 'zalo' ? (
                      <span className="px-3 py-1.5 text-xs text-white/70">暂不支持常驻服务</span>
                    ) : !isRunning ? (
                      <button
                        onClick={() => handleStart(platform, platformAccounts[0]?.id)}
                        disabled={isLoading}
                        title="启动常驻在线服务：保持在线、监听私聊并自动回复（用于养号/实时对话）；它与任务管理里的外呼任务互斥"
                        className="px-3 py-1.5 bg-white/20 backdrop-blur text-white rounded-lg text-xs font-medium hover:bg-white/30 disabled:opacity-50 transition-colors"
                      >
                        {isLoading ? '启动中...' : '▶ 启动在线服务'}
                      </button>
                    ) : (
                      <button
                        onClick={() => handleStop(platform)}
                        disabled={isLoading}
                        title="停止常驻在线服务，之后该账号就可以用来跑外呼任务"
                        className="px-3 py-1.5 bg-black/20 backdrop-blur text-white rounded-lg text-xs font-medium hover:bg-black/30 disabled:opacity-50 transition-colors"
                      >
                        {isLoading ? '停止中...' : '⏹ 停止'}
                      </button>
                    )}
                    <button onClick={() => handleViewLogs(platform)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${logView === platform ? 'bg-white text-slate-900' : 'bg-white/10 text-white hover:bg-white/20'}`}>
                      日志
                    </button>
                  </div>
                </div>
                {platform !== 'zalo' && (
                  <div className="px-5 py-2 text-xs text-slate-500 bg-slate-50 border-b border-slate-100">
                    常驻在线服务 = 该账号登录后一直在线，监听私聊并按人设自动回复（养号 / 实时对话）。
                    它与「任务管理」里的外呼任务<strong className="text-slate-700">互斥</strong>
                    ：同一个账号同一时刻只能有一个 Telegram 客户端，启动任务前请先停掉服务。
                  </div>
                )}

                {/* Log viewer */}
                {logView === platform && (
                  <div className="bg-slate-900 text-emerald-400 p-4 text-xs font-mono max-h-48 overflow-y-auto border-b border-slate-200">
                    {logs.length === 0 ? <p className="text-slate-500">暂无日志</p> : logs.map((line, i) => <div key={i} className="py-0.5">{line}</div>)}
                  </div>
                )}

                {/* Account cards */}
                <div className="p-4 grid gap-3">
                  {platformAccounts.map((account) => {
                    const days = getDaysSince(account.created_at);
                    const stage = getWarmingStage(days);
                    const health = getHealthBadge(account.health);
                    const accountMsgs = getMessagesForAccount(account.id);
                    const isChatOpen = chatView === account.id;
                    const hcResult = healthCheckResults[account.id];
                    const isEditing = editingName === account.id;

                    return (
                      <div key={account.id} className="group border border-slate-100 rounded-lg hover:border-slate-300 hover:shadow-md transition-all duration-200 overflow-hidden">
                        <div className="p-4 flex items-start justify-between gap-4">
                          <div className="flex-1 min-w-0">
                            {/* Name row */}
                            <div className="flex items-center gap-2 mb-1">
                              {isEditing ? (
                                <div className="flex items-center gap-2">
                                  <input
                                    type="text"
                                    value={editNameValue}
                                    onChange={(e) => setEditNameValue(e.target.value)}
                                    onKeyDown={(e) => { if (e.key === 'Enter') handleSaveDisplayName(account.id); if (e.key === 'Escape') setEditingName(null); }}
                                    className="px-2 py-1 border border-blue-300 rounded text-sm focus:ring-2 focus:ring-blue-500 outline-none w-40"
                                    autoFocus
                                  />
                                  <button onClick={() => handleSaveDisplayName(account.id)} className="text-xs text-emerald-600 hover:text-emerald-700 font-medium">保存</button>
                                  <button onClick={() => setEditingName(null)} className="text-xs text-slate-400 hover:text-slate-600">取消</button>
                                </div>
                              ) : (
                                <div className="flex items-center gap-2 cursor-pointer group/name" onClick={() => { setEditingName(account.id); setEditNameValue(account.display_name || ''); }}>
                                  <span className="font-semibold text-slate-900 text-base truncate">
                                    {account.display_name || account.username}
                                  </span>
                                  <span className="opacity-0 group-hover/name:opacity-100 text-xs text-slate-400 transition-opacity">✏️</span>
                                </div>
                              )}
                              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${health.bg} ${health.text} ${health.border}`}>
                                <span className={`w-1.5 h-1.5 rounded-full ${health.dot}`} />
                                {health.label}
                              </span>
                            </div>
                            {/* Real username line */}
                            {account.display_name && (
                              <div className="text-xs text-slate-400 mb-1">{account.username}</div>
                            )}
                            {/* Meta line */}
                            <div className="flex items-center gap-3 text-xs text-slate-500">
                              <span className={`px-1.5 py-0.5 rounded ${stage.bg} ${stage.color} font-medium`}>{stage.label}</span>
                              <span>{days}天</span>
                              <span className={account.is_active ? 'text-emerald-600' : 'text-rose-500'}>{account.is_active ? '活跃' : '停用'}</span>
                              {account.proxy_url && <span className="text-slate-400 truncate max-w-[200px]">{account.proxy_url}</span>}
                            </div>
                            {/* Reply policy toggles */}
                            <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                              <span className="text-xs text-slate-400 mr-1">回复策略:</span>
                              {([
                                { key: 'private' as const, label: '私聊' },
                                { key: 'groups' as const, label: '群组' },
                                { key: 'channels' as const, label: '频道' },
                                { key: 'bots' as const, label: '机器人' },
                              ]).map((item) => {
                                const policy = account.reply_policy || { private: true, groups: false, channels: false, bots: false };
                                const active = policy[item.key];
                                return (
                                  <button
                                    key={item.key}
                                    onClick={() => handleToggleReplyPolicy(account.id, item.key)}
                                    className={`px-2 py-0.5 rounded-full text-xs font-medium transition-colors border ${
                                      active
                                        ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                                        : 'bg-slate-50 text-slate-400 border-slate-200 hover:border-slate-300'
                                    }`}
                                  >
                                    {active ? '✓' : '✗'} {item.label}
                                  </button>
                                );
                              })}
                            </div>
                            {/* Pause & Persona controls */}
                            <div className="flex items-center gap-2 mt-2 flex-wrap">
                              <button
                                onClick={() => handleTogglePause(account.id)}
                                className={`px-3 py-1 rounded-full text-xs font-semibold transition-colors border ${
                                  account.paused
                                    ? 'bg-amber-50 text-amber-700 border-amber-300 hover:bg-amber-100'
                                    : 'bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100'
                                }`}
                              >
                                {account.paused ? '⏸ 已暂停' : '▶ 对话中'}
                              </button>
                              <div className="relative inline-block">
                                <button
                                  ref={personaBtnRef}
                                  onClick={() => setPersonaSelector(personaSelector === account.id ? null : account.id)}
                                  className="px-3 py-1 rounded-full text-xs font-medium border border-indigo-200 bg-indigo-50 text-indigo-700 hover:bg-indigo-100 transition-colors"
                                >
                                  🎭 {personaPresets.find((p) => p.key === account.persona)?.name || '选择人设'}
                                </button>
                              </div>
                            </div>
                          </div>

                          {/* Action buttons */}
                          <div className="flex items-center gap-1.5 shrink-0">
                              <button
                                onClick={() => handleAccountHealthCheck(account)}
                                disabled={healthCheckLoading === account.id}
                                className="px-2.5 py-1.5 rounded-lg text-xs font-medium border border-slate-200 text-slate-600 hover:bg-slate-50 hover:border-slate-300 disabled:opacity-50 transition-colors"
                                title="检测 Session 是否过期"
                              >
                                {healthCheckLoading === account.id ? '...' : '🔗'}
                              </button>
                            <button
                              onClick={() => setChatView(isChatOpen ? null : account.id)}
                              className={`px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors ${isChatOpen ? 'bg-slate-900 text-white' : 'border border-slate-200 text-slate-600 hover:bg-slate-50'}`}
                            >
                              💬
                            </button>
                            {deleteConfirm === account.id ? (
                              <div className="flex items-center gap-1">
                                <button onClick={() => handleDeleteAccount(account.id)} className="px-2 py-1.5 bg-rose-600 text-white rounded-lg text-xs font-medium hover:bg-rose-700">确认</button>
                                <button onClick={() => setDeleteConfirm(null)} className="px-2 py-1.5 border border-slate-200 text-slate-500 rounded-lg text-xs hover:bg-slate-50">取消</button>
                              </div>
                            ) : (
                              <button
                                onClick={() => setDeleteConfirm(account.id)}
                                className="px-2.5 py-1.5 rounded-lg text-xs font-medium border border-slate-200 text-slate-400 hover:text-rose-600 hover:border-rose-200 hover:bg-rose-50 transition-colors opacity-0 group-hover:opacity-100"
                                title="删除账号"
                              >
                                🗑
                              </button>
                            )}
                          </div>
                        </div>

                        {/* Health check result */}
                        {hcResult && (
                          <div className={`mx-4 mb-3 px-3 py-2 rounded-lg text-xs font-medium ${hcResult.ok ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-rose-50 text-rose-700 border border-rose-200'}`}>
                            {hcResult.ok ? '✅' : '❌'} {hcResult.message}
                          </div>
                        )}

                        {/* Chat panel */}
                        {isChatOpen && (
                          <div className="border-t border-slate-100 bg-slate-50">
                            <div className="px-4 py-2 border-b border-slate-100 flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                                <span className="text-xs font-medium text-slate-600">实时消息</span>
                              </div>
                              <span className="text-xs text-slate-400">{accountMsgs.length} 条</span>
                            </div>
                            <div className="max-h-64 overflow-y-auto p-4 space-y-2">
                              {accountMsgs.length === 0 ? (
                                <p className="text-slate-400 text-sm text-center py-6">暂无消息</p>
                              ) : (
                                accountMsgs.map((msg) => (
                                  <div key={msg.id} className={`flex ${msg.direction === 'outbound' ? 'justify-end' : 'justify-start'}`}>
                                    <div className={`max-w-[75%] px-3 py-2 rounded-lg text-sm ${
                                      msg.direction === 'outbound' ? 'bg-slate-900 text-white' : 'bg-white border border-slate-200 text-slate-900'
                                    }`}>
                                      <div className={`text-xs mb-0.5 ${msg.direction === 'outbound' ? 'text-slate-400' : 'text-slate-400'}`}>
                                        {msg.direction === 'inbound' ? msg.sender_name : 'Bot'} · {new Date(msg.timestamp).toLocaleTimeString()}
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

          {accounts.length === 0 && (
            <div className="text-center py-16">
              <div className="text-4xl mb-3 opacity-30">👤</div>
              <p className="text-slate-500">暂无账号</p>
              <button onClick={openLoginModal} className="mt-3 text-sm text-blue-600 hover:text-blue-700 font-medium">添加第一个账号</button>
            </div>
          )}
        </div>
      )}

      {/* Login Modal */}
      {showLoginModal && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6 border border-slate-100">
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-lg font-bold text-slate-900">添加新账号</h3>
              <button onClick={() => setShowLoginModal(false)} className="w-8 h-8 flex items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-colors">&times;</button>
            </div>

            {loginSuccess && (
              <div className="mb-4 p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg text-sm font-medium">{loginSuccess}</div>
            )}
            {loginError && (
              <div className="mb-4 p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-lg text-sm font-medium">{loginError}</div>
            )}

            {loginStep === 'platform' && (
              <div className="space-y-3">
                <p className="text-sm text-slate-500 mb-2">选择平台</p>
                <div className="grid grid-cols-3 gap-3">
                  {(['telegram', 'facebook', 'zalo'] as const).map((p) => (
                    <button key={p} onClick={() => { setLoginPlatform(p); setLoginStep('phone'); }}
                      className="p-4 border-2 border-slate-100 rounded-xl hover:border-slate-300 hover:bg-slate-50 text-center transition-all">
                      <div className="text-2xl mb-1.5">{PLATFORM_CONFIG[p].icon}</div>
                      <div className="font-medium text-sm text-slate-700">{PLATFORM_CONFIG[p].label}</div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {loginStep === 'phone' && loginPlatform === 'telegram' && (
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">Session 名称</label>
                  <input type="text" value={loginSessionName} onChange={(e) => setLoginSessionName(e.target.value)}
                    placeholder="留空会按手机号自动生成，例如 tg8801934061959" className="w-full px-3 py-2.5 border border-slate-200 rounded-lg focus:ring-2 focus:ring-slate-900 focus:border-transparent outline-none text-sm transition-shadow" />
                  <p className="text-xs text-slate-400 mt-1">1-48 位小写字母、数字、下划线或短横线，并以字母/数字开头（会作为 sessions/&lt;名称&gt;.session 的文件名）</p>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">手机号码 (含国际区号)</label>
                  <input type="tel" value={loginPhone}
                    onChange={(e) => {
                      const value = e.target.value;
                      // 没手动改过会话名时，按手机号自动生成，省得手输
                      setLoginSessionName((current) =>
                        current === '' || current === deriveSessionName(loginPhone)
                          ? deriveSessionName(value)
                          : current,
                      );
                      setLoginPhone(value);
                    }}
                    placeholder="+8613800138000" className="w-full px-3 py-2.5 border border-slate-200 rounded-lg focus:ring-2 focus:ring-slate-900 focus:border-transparent outline-none text-sm transition-shadow" />
                </div>
                <div className="flex gap-2 pt-1">
                  <button onClick={() => setLoginStep('platform')} className="px-4 py-2.5 border border-slate-200 rounded-lg text-slate-600 hover:bg-slate-50 text-sm font-medium transition-colors">返回</button>
                  <button onClick={handleTestConnection} disabled={testConnLoading}
                    className="px-4 py-2.5 border border-emerald-200 text-emerald-700 rounded-lg hover:bg-emerald-50 text-sm font-medium disabled:opacity-50 transition-colors">
                    {testConnLoading ? '测试中...' : '🔗 测试连接'}
                  </button>
                  <button onClick={handleSendCode} disabled={loginLoading}
                    className="flex-1 px-4 py-2.5 bg-slate-900 text-white rounded-lg hover:bg-slate-800 text-sm font-medium disabled:opacity-50 transition-colors">
                    {loginLoading ? '发送中...' : '发送验证码'}
                  </button>
                </div>
                {testConnResult && (
                  <div className={`p-3 rounded-lg text-sm font-medium ${testConnResult.ok ? 'bg-emerald-50 border border-emerald-200 text-emerald-800' : 'bg-rose-50 border border-rose-200 text-rose-800'}`}>
                    {testConnResult.ok ? '✅' : '❌'} {testConnResult.message}
                  </div>
                )}
              </div>
            )}

            {loginStep === 'phone' && loginPlatform === 'facebook' && (
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">Session 名称</label>
                  <input type="text" value={loginSessionName} onChange={(e) => setLoginSessionName(e.target.value || 'fb_default')}
                    placeholder="fb_default" className="w-full px-3 py-2.5 border border-slate-200 rounded-lg focus:ring-2 focus:ring-slate-900 focus:border-transparent outline-none text-sm" />
                </div>
                <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-800 space-y-2">
                  <p className="font-medium">Facebook 浏览器登录流程：</p>
                  <ol className="list-decimal list-inside space-y-1 text-xs">
                    <li>点击下方「打开浏览器」按钮</li>
                    <li>在弹出的浏览器中手动登录 Facebook</li>
                    <li>处理完验证码/二步验证后，回到此页面</li>
                    <li>点击「完成登录」保存会话</li>
                  </ol>
                </div>
                <div className="flex gap-2 pt-1">
                  <button onClick={() => setLoginStep('platform')} className="px-4 py-2.5 border border-slate-200 rounded-lg text-slate-600 hover:bg-slate-50 text-sm font-medium">返回</button>
                  <button onClick={async () => {
                    const name = loginSessionName || 'fb_default';
                    setLoginLoading(true); setLoginError('');
                    try {
                      await accountAPI.facebookLoginStart(name);
                      setLoginSuccess('浏览器已打开，请在浏览器中完成登录后点击「完成登录」');
                    } catch (e: any) { setLoginError(e?.message || '无法启动浏览器'); }
                    setLoginLoading(false);
                  }} disabled={loginLoading} className="flex-1 px-4 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium disabled:opacity-50 transition-colors">
                    {loginLoading ? '启动中...' : '🌐 打开浏览器'}
                  </button>
                </div>
                <div className="flex gap-2">
                  <button onClick={async () => {
                    const name = loginSessionName || 'fb_default';
                    setLoginLoading(true); setLoginError(''); setLoginSuccess('');
                    try {
                      const result = await accountAPI.facebookLoginComplete(name);
                      if (result.status === 'success') {
                        setLoginSuccess(`Facebook 登录成功: ${name}`);
                        setTimeout(() => { setShowLoginModal(false); loadData(); }, 1500);
                      } else {
                        setLoginError(result.message || '登录完成失败');
                      }
                    } catch (e: any) { setLoginError(e?.message || '完成登录失败'); }
                    setLoginLoading(false);
                  }} disabled={loginLoading} className="flex-1 px-4 py-2.5 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 text-sm font-medium disabled:opacity-50 transition-colors">
                    {loginLoading ? '保存中...' : '✅ 完成登录'}
                  </button>
                </div>
              </div>
            )}

            {loginStep === 'phone' && loginPlatform === 'zalo' && (
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">Session 名称</label>
                  <input type="text" value={loginSessionName} onChange={(e) => setLoginSessionName(e.target.value)}
                    placeholder="例如: zalo_user1" className="w-full px-3 py-2.5 border border-slate-200 rounded-lg focus:ring-2 focus:ring-slate-900 focus:border-transparent outline-none text-sm" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">手机号码</label>
                  <input type="tel" value={loginPhone} onChange={(e) => setLoginPhone(e.target.value)}
                    placeholder="0912345678" className="w-full px-3 py-2.5 border border-slate-200 rounded-lg focus:ring-2 focus:ring-slate-900 focus:border-transparent outline-none text-sm" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">密码</label>
                  <input type="password" value={loginPassword} onChange={(e) => setLoginPassword(e.target.value)}
                    placeholder="Zalo 登录密码" className="w-full px-3 py-2.5 border border-slate-200 rounded-lg focus:ring-2 focus:ring-slate-900 focus:border-transparent outline-none text-sm" />
                </div>
                <div className="flex gap-2 pt-1">
                  <button onClick={() => setLoginStep('platform')} className="px-4 py-2.5 border border-slate-200 rounded-lg text-slate-600 hover:bg-slate-50 text-sm font-medium">返回</button>
                  <button onClick={async () => {
                    if (!loginPhone || !loginPassword || !loginSessionName) { setLoginError('请填写所有字段'); return; }
                    setLoginLoading(true); setLoginError('');
                    try {
                      const result = await fetchAPI('/accounts/zalo/login', { method: 'POST', body: JSON.stringify({ phone: loginPhone, password: loginPassword, session_name: loginSessionName }) });
                      if (result.status === 'success') { setLoginSuccess(`Zalo 登录成功: ${loginSessionName}`); setTimeout(() => { setShowLoginModal(false); loadData(); }, 1500); }
                      else setLoginError(result.message || '登录失败');
                    } catch (e: any) { setLoginError(e?.message || 'Zalo 登录失败'); }
                    setLoginLoading(false);
                  }} disabled={loginLoading} className="flex-1 px-4 py-2.5 bg-slate-900 text-white rounded-lg hover:bg-slate-800 text-sm font-medium disabled:opacity-50">
                    {loginLoading ? '登录中...' : '登录'}
                  </button>
                </div>
              </div>
            )}

            {loginStep === 'code' && (
              <div className="space-y-4">
                <p className="text-sm text-slate-500">验证码已发送到 {loginPhone}</p>
                <div>
                  <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">验证码</label>
                  <input type="text" value={loginCode} onChange={(e) => setLoginCode(e.target.value)}
                    placeholder="12345" maxLength={5}
                    className="w-full px-3 py-3 border border-slate-200 rounded-lg text-center text-2xl tracking-[0.3em] focus:ring-2 focus:ring-slate-900 focus:border-transparent outline-none" />
                </div>
                <div className="flex gap-2 pt-1">
                  <button onClick={() => setLoginStep('phone')} className="px-4 py-2.5 border border-slate-200 rounded-lg text-slate-600 hover:bg-slate-50 text-sm font-medium">返回</button>
                  <button onClick={handleVerifyCode} disabled={loginLoading}
                    className="flex-1 px-4 py-2.5 bg-slate-900 text-white rounded-lg hover:bg-slate-800 text-sm font-medium disabled:opacity-50">
                    {loginLoading ? '验证中...' : '验证'}
                  </button>
                </div>
              </div>
            )}

            {loginStep === 'password' && (
              <div className="space-y-4">
                <p className="text-sm text-slate-500">此账号开启了两步验证，请输入密码</p>
                <div>
                  <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">2FA 密码</label>
                  <input type="password" value={loginPassword} onChange={(e) => setLoginPassword(e.target.value)}
                    placeholder="输入两步验证密码" className="w-full px-3 py-2.5 border border-slate-200 rounded-lg focus:ring-2 focus:ring-slate-900 focus:border-transparent outline-none text-sm" />
                </div>
                <div className="flex gap-2 pt-1">
                  <button onClick={() => setLoginStep('code')} className="px-4 py-2.5 border border-slate-200 rounded-lg text-slate-600 hover:bg-slate-50 text-sm font-medium">返回</button>
                  <button onClick={handlePasswordSubmit} disabled={loginLoading}
                    className="flex-1 px-4 py-2.5 bg-slate-900 text-white rounded-lg hover:bg-slate-800 text-sm font-medium disabled:opacity-50">
                    {loginLoading ? '验证中...' : '确认'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Persona selector dropdown (portal to avoid overflow clipping) */}
      {personaSelector && typeof document !== 'undefined' && createPortal(
        <>
          <div className="fixed inset-0 z-40" onClick={() => setPersonaSelector(null)} />
          <div
            className="fixed z-50 w-64 bg-white border border-slate-200 rounded-lg shadow-xl overflow-hidden"
            style={{
              top: (() => {
                const rect = personaBtnRef.current?.getBoundingClientRect();
                return rect ? rect.bottom + 4 : 0;
              })(),
              left: (() => {
                const rect = personaBtnRef.current?.getBoundingClientRect();
                return rect ? rect.left : 0;
              })(),
            }}
          >
            {personaPresets.map((p) => {
              const currentAccount = accounts.find((a) => a.id === personaSelector);
              const isActive = currentAccount?.persona === p.key;
              return (
                <button
                  key={p.key}
                  onClick={() => handleSetPersona(personaSelector, p.key)}
                  className={`w-full text-left px-3 py-2.5 hover:bg-slate-50 transition-colors border-b border-slate-50 last:border-0 ${isActive ? 'bg-indigo-50' : ''}`}
                >
                  <div className="flex items-center justify-between">
                    <span className={`text-sm font-medium ${isActive ? 'text-indigo-700' : 'text-slate-700'}`}>{p.name}</span>
                    {isActive && <span className="text-indigo-500 text-xs">当前</span>}
                  </div>
                  <div className="text-xs text-slate-400 mt-0.5">{p.desc}</div>
                  <div className="text-xs text-slate-400">风格: {p.tone}</div>
                </button>
              );
            })}
          </div>
        </>,
        document.body,
      )}
    </div>
  );
}
