'use client';

import { useEffect, useState } from 'react';
import { fetchAPI, wsClient, type Task } from '@/lib/api';

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loaded, setLoaded] = useState(false);
  // 只有真的连不上后端才设置；没有任务是正常状态
  const [backendError, setBackendError] = useState('');
  const [form, setForm] = useState({
    name: '',
    platform: 'telegram',
    category: 'private_investigator',
    keywords: '',
    target_region: '',
  });

  // Connect WebSocket on mount
  useEffect(() => {
    wsClient.connect();

    wsClient.on('task_created', () => loadTasks());
    wsClient.on('task_started', () => loadTasks());

    return () => {
      wsClient.disconnect();
    };
  }, []);

  async function loadTasks() {
    try {
      const data = await fetchAPI('/tasks');
      setTasks(data || []);
      setLoaded(true);
      setBackendError('');
    } catch (error: any) {
      console.error('Failed to load tasks:', error);
      setTasks([]);
      setLoaded(true);
      setBackendError(error?.message || '后端不可达');
    }
  }

  async function createTask(e: React.FormEvent) {
    e.preventDefault();

    try {
      await fetchAPI('/tasks', {
        method: 'POST',
        body: JSON.stringify({
          ...form,
          keywords: form.keywords.split(',').map((k) => k.trim()).filter(Boolean),
        }),
      });
      setForm({ name: '', platform: 'telegram', category: 'private_investigator', keywords: '', target_region: '' });
      loadTasks();
    } catch (error) {
      console.error('Failed to create task:', error);
      alert('创建任务失败,请检查后端服务');
    }
  }

  async function startTask(taskId: string) {
    try {
      await fetchAPI(`/tasks/${taskId}/start`, { method: 'POST' });
      loadTasks();
    } catch (error) {
      console.error('Failed to start task:', error);
      alert('启动任务失败,请检查后端服务');
    }
  }

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">📋 任务管理</h2>

      {backendError && (
        <div className="bg-rose-50 border-l-4 border-rose-500 p-3 mb-4 rounded">
          <p className="text-sm text-rose-700">
            ⚠️ <strong>后端不可达:</strong> {backendError}
          </p>
        </div>
      )}

      <form onSubmit={createTask} className="bg-white p-4 rounded shadow mb-6 max-w-xl space-y-3">
        <h3 className="font-semibold">➕ 创建新任务</h3>
        <input
          className="w-full border px-3 py-2 rounded"
          placeholder="任务名称"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          required
        />
        <select
          className="w-full border px-3 py-2 rounded"
          value={form.platform}
          onChange={(e) => setForm({ ...form, platform: e.target.value })}
        >
          <option value="telegram">Telegram</option>
          <option value="facebook">Facebook</option>
          <option value="zalo">Zalo</option>
        </select>
        <select
          className="w-full border px-3 py-2 rounded"
          value={form.category}
          onChange={(e) => setForm({ ...form, category: e.target.value })}
        >
          <option value="private_investigator">🔍 私人侦探</option>
          <option value="currency_exchanger">💱 换汇服务</option>
          <option value="freelancer">💼 自由职业者</option>
          <option value="data_seller">📊 数据贩卖者</option>
        </select>
        <input
          className="w-full border px-3 py-2 rounded"
          placeholder="关键词(逗号分隔)"
          value={form.keywords}
          onChange={(e) => setForm({ ...form, keywords: e.target.value })}
          required
        />
        <input
          className="w-full border px-3 py-2 rounded"
          placeholder="目标地区(可选)"
          value={form.target_region}
          onChange={(e) => setForm({ ...form, target_region: e.target.value })}
        />
        <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
          创建任务
        </button>
      </form>

      <div className="flex items-center gap-3 mb-3">
        <h3 className="font-semibold">📝 任务列表</h3>
        <button onClick={loadTasks} className="text-sm text-blue-600 hover:underline">
          {loaded ? '刷新' : '加载任务'}
        </button>
      </div>

      {loaded && tasks.length === 0 && <p className="text-gray-500">暂无任务,创建一个吧!</p>}

      <table className="w-full bg-white rounded shadow overflow-hidden">
        <thead className="bg-gray-100 text-left text-sm">
          <tr>
            <th className="px-4 py-2">任务名称</th>
            <th className="px-4 py-2">平台</th>
            <th className="px-4 py-2">类别</th>
            <th className="px-4 py-2">状态</th>
            <th className="px-4 py-2">操作</th>
            <th className="px-4 py-2">创建时间</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((t) => (
            <tr key={t.id} className="border-t text-sm">
              <td className="px-4 py-2 font-medium">{t.name}</td>
              <td className="px-4 py-2 capitalize">{t.platform === 'telegram' ? '✈️ Telegram' : t.platform}</td>
              <td className="px-4 py-2">
                {t.category === 'private_investigator' ? '🔍 私人侦探' :
                 t.category === 'currency_exchanger' ? '💱 换汇服务' :
                 t.category === 'freelancer' ? '💼 自由职业者' :
                 '📊 数据贩卖者'}
              </td>
              <td className="px-4 py-2">
                <span className={`px-2 py-0.5 rounded text-xs ${
                  t.status === 'running' ? 'bg-green-100 text-green-800' :
                  t.status === 'completed' ? 'bg-blue-100 text-blue-800' :
                  t.status === 'failed' ? 'bg-red-100 text-red-800' :
                  'bg-gray-100 text-gray-800'
                }`}>
                  {t.status === 'running' ? '🟢 运行中' :
                   t.status === 'completed' ? '🔵 已完成' :
                   t.status === 'failed' ? '🔴 失败' :
                   '⚪ 等待中'}
                </span>
              </td>
              <td className="px-4 py-2">
                {t.status === 'pending' && (
                  <button
                    onClick={() => startTask(t.id)}
                    className="bg-green-600 text-white px-3 py-1 rounded text-xs hover:bg-green-700"
                  >
                    ▶️ 启动
                  </button>
                )}
                {t.status === 'running' && (
                  <span className="text-xs text-gray-500">执行中...</span>
                )}
              </td>
              <td className="px-4 py-2">{new Date(t.created_at).toLocaleString('zh-CN')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
