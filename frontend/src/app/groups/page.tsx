'use client';

import { useState } from 'react';
import { fetchAPI, accountAPI } from '@/lib/api';

interface GroupResult {
  group_id: string;
  name: string;
  member_count: number;
  description: string;
}

export default function GroupsPage() {
  const [query, setQuery] = useState('');
  const [useAI, setUseAI] = useState(true);
  const [account, setAccount] = useState('printer');
  const [results, setResults] = useState<GroupResult[]>([]);
  const [keywordsUsed, setKeywordsUsed] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [joinStatus, setJoinStatus] = useState<Record<string, string>>({});
  const [linkInput, setLinkInput] = useState('');
  const [linkLoading, setLinkLoading] = useState(false);

  async function handleSearch() {
    if (!query.trim()) return;
    setLoading(true);
    setError('');
    setResults([]);
    try {
      const data = await fetchAPI('/groups/search', {
        method: 'POST',
        body: JSON.stringify({ query, account, use_ai: useAI }),
        timeout: 60000,
      });
      setResults(data.results || []);
      setKeywordsUsed(data.keywords_used || []);
    } catch (e: any) {
      setError(e?.message || '搜索失败');
    }
    setLoading(false);
  }

  async function handleJoin(group: GroupResult) {
    setJoinStatus((prev) => ({ ...prev, [group.group_id]: 'joining' }));
    try {
      const data = await fetchAPI('/groups/join', {
        method: 'POST',
        body: JSON.stringify({ group_id: group.group_id, account }),
        timeout: 60000,
      });
      setJoinStatus((prev) => ({ ...prev, [group.group_id]: data.status === 'joined' ? 'joined' : 'failed' }));
    } catch {
      setJoinStatus((prev) => ({ ...prev, [group.group_id]: 'failed' }));
    }
  }

  async function handleAddByLink() {
    if (!linkInput.trim()) return;
    setLinkLoading(true);
    setError('');
    try {
      const data = await fetchAPI('/groups/add-by-link', {
        method: 'POST',
        body: JSON.stringify({ link: linkInput, account }),
        timeout: 60000,
      });
      if (data.status === 'joined') {
        setLinkInput('');
        alert(`已加入: ${data.name}`);
      } else {
        setError(data.message || '加入失败');
      }
    } catch (e: any) {
      setError(e?.message || '加入失败');
    }
    setLinkLoading(false);
  }

  return (
    <div className="max-w-4xl mx-auto">
      <h2 className="text-2xl font-bold mb-6">📢 群组管理</h2>

      {/* Add by link */}
      <div className="bg-white p-4 rounded shadow mb-6">
        <h3 className="font-semibold mb-3">➕ 通过链接/用户名添加群组</h3>
        <div className="flex gap-2">
          <input
            className="flex-1 border px-3 py-2 rounded"
            placeholder="t.me/groupname 或 @username 或邀请链接"
            value={linkInput}
            onChange={(e) => setLinkInput(e.target.value)}
          />
          <select
            className="border px-3 py-2 rounded"
            value={account}
            onChange={(e) => setAccount(e.target.value)}
          >
            <option value="printer">printer</option>
            <option value="user3">user3</option>
            <option value="user4">user4</option>
          </select>
          <button
            onClick={handleAddByLink}
            disabled={linkLoading}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {linkLoading ? '加入中...' : '加入'}
          </button>
        </div>
      </div>

      {/* AI Search */}
      <div className="bg-white p-4 rounded shadow mb-6">
        <h3 className="font-semibold mb-3">🔍 搜索群组</h3>
        <div className="flex gap-2 mb-3">
          <input
            className="flex-1 border px-3 py-2 rounded"
            placeholder="描述你想找的群组，例如：虚拟币交易、换汇服务..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          />
          <button
            onClick={handleSearch}
            disabled={loading}
            className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
          >
            {loading ? '搜索中...' : '搜索'}
          </button>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={useAI}
              onChange={(e) => setUseAI(e.target.checked)}
              className="rounded"
            />
            🤖 AI 智能搜索（自动优化关键词）
          </label>
          <select
            className="border px-2 py-1 rounded text-sm"
            value={account}
            onChange={(e) => setAccount(e.target.value)}
          >
            <option value="printer">printer</option>
            <option value="user3">user3</option>
            <option value="user4">user4</option>
          </select>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 p-3 rounded mb-4 text-sm">{error}</div>
      )}

      {/* Keywords used */}
      {keywordsUsed.length > 1 && (
        <div className="mb-4 text-sm text-gray-500">
          AI 生成的搜索词: {keywordsUsed.map((k) => (
            <span key={k} className="inline-block bg-gray-100 px-2 py-0.5 rounded mr-1">{k}</span>
          ))}
        </div>
      )}

      {/* Results */}
      {results.length > 0 && (
        <div className="space-y-3">
          <h3 className="font-semibold">搜索结果 ({results.length})</h3>
          {results.map((group) => (
            <div key={group.group_id} className="bg-white p-4 rounded shadow flex items-start justify-between">
              <div className="flex-1">
                <div className="font-medium text-lg">{group.name}</div>
                {group.description && (
                  <p className="text-sm text-gray-600 mt-1 line-clamp-2">{group.description}</p>
                )}
                <div className="text-xs text-gray-400 mt-2">
                  👥 {group.member_count?.toLocaleString() || '?'} 成员 · ID: {group.group_id}
                </div>
              </div>
              <button
                onClick={() => handleJoin(group)}
                disabled={joinStatus[group.group_id] === 'joining' || joinStatus[group.group_id] === 'joined'}
                className={`ml-4 px-4 py-2 rounded text-sm whitespace-nowrap ${
                  joinStatus[group.group_id] === 'joined'
                    ? 'bg-green-100 text-green-800'
                    : joinStatus[group.group_id] === 'failed'
                    ? 'bg-red-100 text-red-800'
                    : 'bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50'
                }`}
              >
                {joinStatus[group.group_id] === 'joined'
                  ? '✅ 已加入'
                  : joinStatus[group.group_id] === 'failed'
                  ? '❌ 失败'
                  : joinStatus[group.group_id] === 'joining'
                  ? '加入中...'
                  : '加入群组'}
              </button>
            </div>
          ))}
        </div>
      )}

      {!loading && results.length === 0 && !error && (
        <div className="text-center text-gray-400 py-12">
          <p className="text-lg">输入描述，AI 帮你找到相关群组</p>
          <p className="text-sm mt-2">例如："越南换汇群"、"crypto trading"、"freelancer Vietnam"</p>
        </div>
      )}
    </div>
  );
}
