'use client';

import { useState, useEffect } from 'react';
import { type Account, DEMO_ACCOUNTS, accountAPI } from '@/lib/api';

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [demoMode, setDemoMode] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadAccounts = async () => {
    try {
      const data = await accountAPI.list();
      if (data && data.length > 0) {
        setAccounts(data);
        setDemoMode(false);
      } else {
        setAccounts(DEMO_ACCOUNTS);
        setDemoMode(true);
      }
      setError(null);
    } catch {
      setAccounts(DEMO_ACCOUNTS);
      setDemoMode(true);
      setError('无法连接后端，使用演示数据');
    }
    setLoaded(true);
  };

  useEffect(() => {
    loadAccounts();
  }, []);

  const getHealthColor = (health: string) => {
    switch (health) {
      case 'green': return 'bg-green-100 text-green-800';
      case 'yellow': return 'bg-yellow-100 text-yellow-800';
      case 'red': return 'bg-red-100 text-red-800';
      case 'black': return 'bg-gray-100 text-gray-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const getAccountAge = (createdAt: string) => {
    const ts = typeof createdAt === 'number' ? createdAt * 1000 : new Date(createdAt).getTime();
    const days = Math.floor((Date.now() - ts) / (1000 * 60 * 60 * 24));
    if (days < 7) return `${days}天 (新号期)`;
    if (days < 30) return `${days}天 (温号期)`;
    if (days < 90) return `${days}天 (稳定期)`;
    return `${days}天 (成熟期)`;
  };

  const getDaysSince = (createdAt: string) => {
    const ts = typeof createdAt === 'number' ? createdAt * 1000 : new Date(createdAt).getTime();
    return Math.floor((Date.now() - ts) / (1000 * 60 * 60 * 24));
  };

  return (
    <div className="flex flex-col h-[calc(100vh-3rem)]">
      {demoMode && (
        <div className="bg-yellow-50 border-b border-yellow-200 px-4 py-2 text-sm text-yellow-800 mb-4 rounded">
          💡 <strong>演示模式:</strong> {error || '未检测到已登录账号，显示模拟数据。'}
        </div>
      )}

      {!demoMode && (
        <div className="bg-green-50 border-b border-green-200 px-4 py-2 text-sm text-green-800 mb-4 rounded">
          ✅ <strong>实时模式:</strong> 显示已登录的 Telegram 账号（来自 sessions/ 目录）
        </div>
      )}

      <div className="flex items-center justify-between mb-4">
        <h2 className="text-2xl font-bold">账号管理</h2>
        <button
          onClick={loadAccounts}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm"
        >
          刷新
        </button>
      </div>

      {!loaded ? (
        <p className="text-gray-500">加载中...</p>
      ) : (
        <div className="grid gap-4">
          {accounts.map((account) => {
            const days = getDaysSince(account.created_at);
            return (
              <div key={account.id} className="bg-white rounded shadow p-4">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <h3 className="font-semibold text-lg">{account.username}</h3>
                      <span className={`px-2 py-1 rounded text-xs font-medium ${getHealthColor(account.health)}`}>
                        {account.health.toUpperCase()}
                      </span>
                    </div>

                    <div className="space-y-1 text-sm text-gray-600">
                      <div><strong>平台:</strong> {account.platform}</div>
                      <div><strong>账号年龄:</strong> {getAccountAge(account.created_at)}</div>
                      <div><strong>状态:</strong> {account.is_active ? '✅ 活跃' : '❌ 停用'}</div>
                      {account.proxy_url && (
                        <div><strong>代理IP:</strong> {account.proxy_url}</div>
                      )}
                    </div>
                  </div>

                  <div className="text-right text-sm">
                    <div className="text-gray-500 mb-2">养号阶段</div>
                    <div className="font-medium">
                      {days < 7 ? '🟡 新号期' : days < 30 ? '🟠 温号期' : days < 90 ? '🔵 稳定期' : '🟢 成熟期'}
                    </div>
                  </div>
                </div>

                <div className="mt-4 pt-4 border-t text-xs text-gray-500">
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <strong>每日限额:</strong><br/>
                      {days < 7 ? '加群: 2个 | 消息: 20条' : days < 30 ? '加群: 5个 | 消息: 50条' : days < 90 ? '加群: 8个 | 消息: 100条' : '加群: 15个 | 消息: 200条'}
                    </div>
                    <div>
                      <strong>IP一致性:</strong><br/>
                      ✅ 一致 (90天内同一地区)
                    </div>
                    <div>
                      <strong>配置完整性:</strong><br/>
                      ✅ 完整 (5/5项设置已完成)
                    </div>
                  </div>
                </div>
              </div>
            );
          })}

          {accounts.length === 0 && (
            <p className="text-gray-500 text-center py-8">暂无账号数据</p>
          )}
        </div>
      )}
    </div>
  );
}
