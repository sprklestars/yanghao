'use client';

import { useState } from 'react';
import { type Account, DEMO_ACCOUNTS } from '@/lib/api';

// 演示模式 - 使用模拟数据
const DEMO_MODE = true;

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>(DEMO_MODE ? DEMO_ACCOUNTS : []);
  const [loaded, setLoaded] = useState(DEMO_MODE);

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
    const days = Math.floor((Date.now() - new Date(createdAt).getTime()) / (1000 * 60 * 60 * 24));
    if (days < 7) return `${days}天 (新号期)`;
    if (days < 30) return `${days}天 (温号期)`;
    if (days < 90) return `${days}天 (稳定期)`;
    return `${days}天 (成熟期)`;
  };

  return (
    <div className="flex flex-col h-[calc(100vh-3rem)]">
      {/* Demo mode banner */}
      {DEMO_MODE && (
        <div className="bg-yellow-50 border-b border-yellow-200 px-4 py-2 text-sm text-yellow-800 mb-4 rounded">
          💡 <strong>演示模式:</strong> 当前使用模拟数据,无需后端服务。刷新页面数据会重置。
        </div>
      )}

      <div className="flex items-center justify-between mb-4">
        <h2 className="text-2xl font-bold">账号管理</h2>
        <button
          onClick={() => setLoaded(true)}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm"
        >
          刷新
        </button>
      </div>

      {!loaded ? (
        <p className="text-gray-500">点击刷新加载账号列表...</p>
      ) : (
        <div className="grid gap-4">
          {accounts.map((account) => (
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
                    {(() => {
                      const days = Math.floor((Date.now() - new Date(account.created_at).getTime()) / (1000 * 60 * 60 * 24));
                      if (days < 7) return '🟡 新号期';
                      if (days < 30) return ' 温号期';
                      if (days < 90) return ' 稳定期';
                      return '🟢 成熟期';
                    })()}
                  </div>
                </div>
              </div>

              <div className="mt-4 pt-4 border-t text-xs text-gray-500">
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <strong>每日限额:</strong><br/>
                    {(() => {
                      const days = Math.floor((Date.now() - new Date(account.created_at).getTime()) / (1000 * 60 * 60 * 24));
                      if (days < 7) return '加群: 2个 | 消息: 20条';
                      if (days < 30) return '加群: 5个 | 消息: 50条';
                      if (days < 90) return '加群: 8个 | 消息: 100条';
                      return '加群: 15个 | 消息: 200条';
                    })()}
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
          ))}

          {accounts.length === 0 && (
            <p className="text-gray-500 text-center py-8">暂无账号数据</p>
          )}
        </div>
      )}
    </div>
  );
}
