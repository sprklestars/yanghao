'use client';

import { useEffect, useState } from 'react';
import { fetchAPI, wsClient, type Task } from '@/lib/api';

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [form, setForm] = useState({
    name: '',
    platform: 'telegram',
    category: 'private_investigator',
    keywords: '',
    target_region: '',
  });

  // Connect WebSocket on mount
  useEffect(() => {
    wsClient.connect('global');

    // Listen for task updates
    wsClient.on('task_created', (data) => {
      console.log('New task created:', data.task_id);
      loadTasks();
    });

    wsClient.on('task_started', (data) => {
      console.log('Task started:', data.task_id);
      loadTasks();
    });

    return () => {
      wsClient.disconnect();
    };
  }, []);

  async function loadTasks() {
    const data = await fetchAPI('/tasks');
    setTasks(data);
    setLoaded(true);
  }

  async function createTask(e: React.FormEvent) {
    e.preventDefault();
    await fetchAPI('/tasks', {
      method: 'POST',
      body: JSON.stringify({
        ...form,
        keywords: form.keywords.split(',').map((k) => k.trim()).filter(Boolean),
      }),
    });
    setForm({ name: '', platform: 'telegram', category: 'private_investigator', keywords: '', target_region: '' });
    // No need to reload - WebSocket will trigger update
  }

  async function startTask(taskId: string) {
    await fetchAPI(`/tasks/${taskId}/start`, { method: 'POST' });
    // Status will update via WebSocket
  }

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">Tasks</h2>

      <form onSubmit={createTask} className="bg-white p-4 rounded shadow mb-6 max-w-xl space-y-3">
        <h3 className="font-semibold">Create Task</h3>
        <input
          className="w-full border px-3 py-2 rounded"
          placeholder="Task name"
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
          <option value="private_investigator">Private Investigator</option>
          <option value="currency_exchanger">Currency Exchanger</option>
          <option value="freelancer">Freelancer</option>
          <option value="data_seller">Data Seller</option>
        </select>
        <input
          className="w-full border px-3 py-2 rounded"
          placeholder="Keywords (comma separated)"
          value={form.keywords}
          onChange={(e) => setForm({ ...form, keywords: e.target.value })}
          required
        />
        <input
          className="w-full border px-3 py-2 rounded"
          placeholder="Target region (optional)"
          value={form.target_region}
          onChange={(e) => setForm({ ...form, target_region: e.target.value })}
        />
        <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
          Create
        </button>
      </form>

      <div className="flex items-center gap-3 mb-3">
        <h3 className="font-semibold">Task List</h3>
        <button onClick={loadTasks} className="text-sm text-blue-600 hover:underline">
          {loaded ? 'Refresh' : 'Load Tasks'}
        </button>
      </div>

      {loaded && tasks.length === 0 && <p className="text-gray-500">No tasks yet.</p>}

      <table className="w-full bg-white rounded shadow overflow-hidden">
        <thead className="bg-gray-100 text-left text-sm">
          <tr>
            <th className="px-4 py-2">Name</th>
            <th className="px-4 py-2">Platform</th>
            <th className="px-4 py-2">Category</th>
            <th className="px-4 py-2">Status</th>
            <th className="px-4 py-2">Actions</th>
            <th className="px-4 py-2">Created</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((t) => (
            <tr key={t.id} className="border-t text-sm">
              <td className="px-4 py-2">{t.name}</td>
              <td className="px-4 py-2 capitalize">{t.platform}</td>
              <td className="px-4 py-2">{t.category.replace(/_/g, ' ')}</td>
              <td className="px-4 py-2">
                <span className={`px-2 py-0.5 rounded text-xs ${
                  t.status === 'running' ? 'bg-green-100 text-green-800' :
                  t.status === 'completed' ? 'bg-blue-100 text-blue-800' :
                  t.status === 'failed' ? 'bg-red-100 text-red-800' :
                  'bg-gray-100 text-gray-800'
                }`}>
                  {t.status}
                </span>
              </td>
              <td className="px-4 py-2">
                {t.status === 'pending' && (
                  <button
                    onClick={() => startTask(t.id)}
                    className="bg-green-600 text-white px-3 py-1 rounded text-xs hover:bg-green-700"
                  >
                    Start
                  </button>
                )}
              </td>
              <td className="px-4 py-2">{new Date(t.created_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
