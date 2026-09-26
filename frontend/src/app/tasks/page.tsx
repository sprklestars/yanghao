'use client';

import { useEffect, useState } from 'react';
import {
  accountAPI,
  fetchAPI,
  serviceAPI,
  wsClient,
  type Account,
  type ServiceStatus,
  type Task,
} from '@/lib/api';

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loaded, setLoaded] = useState(false);
  // 只有真的连不上后端才设置；没有任务是正常状态
  const [backendError, setBackendError] = useState('');
  const [services, setServices] = useState<ServiceStatus[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  // 启动/停止的反馈走横幅，不再用 alert 阻塞页面（alert 会挡住列表刷新）
  const [notice, setNotice] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
  const [form, setForm] = useState({
    name: '',
    platform: 'telegram',
    category: 'private_investigator',
    keywords: '',
    target_region: '',
  });
  // 建任务时显式选账号（以前是后端自己挑，界面上只显示一句"将使用账号"）
  const [taskAccount, setTaskAccount] = useState('');

  // Connect WebSocket on mount
  useEffect(() => {
    loadTasks(); // 进页面先拉一次，不然列表/调度器状态要手动点刷新才出现
    wsClient.connect();

    wsClient.on('task_created', () => loadTasks());
    wsClient.on('task_started', () => loadTasks());

    // 任务和服务的状态会自己变（worker 起停、任务跑完），定时兜底刷新
    const timer = setInterval(loadTasks, 5000);
    return () => {
      clearInterval(timer);
      wsClient.disconnect();
    };
  }, []);

  const platformAccounts = accounts.filter((a) => a.platform === form.platform);

  // 切换平台时，把账号选择重置为该平台下的第一个
  useEffect(() => {
    setTaskAccount((current) =>
      platformAccounts.some((a) => a.id === current) ? current : platformAccounts[0]?.id || '',
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.platform, accounts]);

  async function loadTasks() {
    try {
      const [data, svc, accs] = await Promise.all([
        fetchAPI('/tasks'),
        serviceAPI.status(),
        accountAPI.list(),
      ]);
      setTasks(data || []);
      setServices(svc || []);
      setAccounts(accs || []);
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
          config: taskAccount ? { account: taskAccount } : {},
        }),
      });
      setForm({ name: '', platform: 'telegram', category: 'private_investigator', keywords: '', target_region: '' });
      loadTasks();
    } catch (error) {
      console.error('Failed to create task:', error);
      setNotice({ kind: 'error', text: '创建任务失败，请检查后端服务' });
    }
  }

  async function startTask(taskId: string) {
    try {
      const res = await fetchAPI<{ mode?: string }>(`/tasks/${taskId}/start`, { method: 'POST' });
      await loadTasks();
      setNotice({
        kind: 'ok',
        text:
          res?.mode === 'celery'
            ? '任务已提交给 Celery 调度器执行。'
            : '任务已在后端进程内直接执行（本机未启用 Celery 调度器，属于正常回退）。',
      });
    } catch (error: any) {
      console.error('Failed to start task:', error);
      setNotice({ kind: 'error', text: `启动任务失败：${error?.message || '请检查后端服务'}` });
    }
  }

  async function deleteTask(taskId: string) {
    if (!confirm('确定删除这个任务吗？相关的会话、消息和情报记录会一起删除，且不可恢复。')) return;
    try {
      await fetchAPI(`/tasks/${taskId}`, { method: 'DELETE' });
      loadTasks();
      setNotice({ kind: 'ok', text: '任务已删除。' });
    } catch (error: any) {
      console.error('Failed to delete task:', error);
      setNotice({ kind: 'error', text: `删除任务失败：${error?.message || '请检查后端服务'}` });
    }
  }

  async function startWorker() {
    try {
      await serviceAPI.start('worker');
      await loadTasks();
      setNotice({ kind: 'ok', text: '任务调度器（Celery Worker）已启动。' });
    } catch (error: any) {
      console.error('Failed to start worker:', error);
      setNotice({ kind: 'error', text: `启动调度器失败：${error?.message || '请检查后端服务'}` });
    }
  }

  async function cancelTask(taskId: string) {
    if (!confirm('确定取消这个正在运行的任务吗？它会停在下一个检查点。')) return;
    try {
      await fetchAPI(`/tasks/${taskId}/cancel`, { method: 'POST' });
      await loadTasks();
      setNotice({ kind: 'ok', text: '已请求取消，任务会在下个检查点停止。' });
    } catch (error: any) {
      console.error('Failed to cancel task:', error);
      setNotice({ kind: 'error', text: `取消失败：${error?.message || '请检查后端服务'}` });
    }
  }

  const workerService = services.find((s) => s.platform === 'worker');
  const telegramService = services.find((s) => s.platform === 'telegram');
  const telegramBusy = !!telegramService?.running;

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

      {notice && (
        <div
          className={`border-l-4 p-3 mb-4 rounded flex items-start justify-between gap-3 ${
            notice.kind === 'error'
              ? 'bg-rose-50 border-rose-500 text-rose-700'
              : 'bg-emerald-50 border-emerald-500 text-emerald-700'
          }`}
        >
          <p className="text-sm whitespace-pre-wrap">
            {notice.kind === 'error' ? '⚠️ ' : '✅ '}
            {notice.text}
          </p>
          <button onClick={() => setNotice(null)} className="text-xs underline shrink-0">
            关闭
          </button>
        </div>
      )}

      {/* 调度器状态：没有它任务也能跑（后端进程内直跑），但跑起来的模式不一样 */}
      <div className="bg-white border border-slate-200 rounded p-3 mb-4 flex items-center justify-between gap-4">
        <div className="text-sm text-slate-600">
          <span className="font-medium text-slate-800">任务调度器（Celery Worker）：</span>
          {workerService?.running ? (
            <span className="text-emerald-700">运行中（PID {workerService.pid}）</span>
          ) : (
            <span className="text-amber-700">未运行</span>
          )}
          {!workerService?.running && (
            <span className="text-slate-500">
              {' '}
              —— 不启动也能跑任务：后端会在 API 进程内直接执行；启动后任务统一排队、互不阻塞。
            </span>
          )}
        </div>
        {!workerService?.running && (
          <button
            onClick={startWorker}
            className="bg-slate-900 text-white px-3 py-1.5 rounded text-xs hover:bg-slate-800 shrink-0"
          >
            ▶ 启动调度器
          </button>
        )}
      </div>

      {telegramBusy && (
        <div className="bg-amber-50 border-l-4 border-amber-500 p-3 mb-4 rounded">
          <p className="text-sm text-amber-800">
            ⚠️ Telegram 常驻在线服务正在运行，占用账号
            {telegramService?.session ? ` @${telegramService.session}` : ''}
            （监听私聊并自动回复）。<strong>外呼任务和它是互斥的</strong>：同一个账号同一时刻只能有一个
            Telegram 客户端。想跑任务请先到「账号管理」页点「停止」。
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
        <select
          className="w-full border px-3 py-2 rounded"
          value={taskAccount}
          onChange={(e) => setTaskAccount(e.target.value)}
          disabled={platformAccounts.length === 0}
        >
          {platformAccounts.length === 0 && <option value="">（该平台暂无账号）</option>}
          {platformAccounts.map((a) => (
            <option key={a.id} value={a.id}>
              使用账号：{a.display_name || a.username || a.id}
              {a.paused ? '（已暂停）' : ''}
            </option>
          ))}
        </select>
        {form.platform !== 'telegram' ? (
          <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2 leading-relaxed">
            提示：Facebook / Zalo 的外呼流水线尚未接入，这类任务可以创建但<strong>无法启动</strong>
            （目前只有 Telegram 支持搜群、加群、私聊）。
          </p>
        ) : (
          <p className="text-xs text-slate-500 leading-relaxed">
            外呼会真的搜群、加群，并私聊群里的活跃用户；Telegram 不允许普通账号拉成员列表，
            所以程序会扫描群内最近发言来找带用户名的目标。任务运行时该账号会被独占，
            请先停止它的「常驻在线服务」。
          </p>
        )}
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
              <td className="px-4 py-2 font-medium">
                {t.name}
                {t.status === 'running' && t.config?.progress ? (
                  <div className="text-xs text-amber-600 font-normal mt-0.5">
                    {t.config.progress.stage || '执行中'}
                    {t.config.progress.keyword ? ` · ${t.config.progress.keyword}` : ''}
                    {t.config.progress.group ? ` · ${t.config.progress.group}` : ''}
                    {t.config.progress.target ? ` · ${t.config.progress.target}` : ''}
                  </div>
                ) : t.config?.last_run ? (
                  <div className="text-xs text-slate-500 font-normal mt-0.5">
                    上次运行：账号 {t.config.last_run.account ?? '-'} · 搜索{' '}
                    {t.config.last_run.searched_keywords ?? 0} 个关键词 · 找到{' '}
                    {t.config.last_run.found_groups ?? 0} 个群 · 加入{' '}
                    {t.config.last_run.joined_groups ?? 0} 个 · 取到{' '}
                    {t.config.last_run.members_found ?? 0} 个目标 · 发起{' '}
                    {t.config.last_run.conversations ?? 0} 个会话
                  </div>
                ) : null}
              </td>
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
              <td className="px-4 py-2 space-x-2">
                {(t.status === 'pending' || t.status === 'paused') && (
                  <button
                    onClick={() => startTask(t.id)}
                    disabled={(telegramBusy && t.platform === 'telegram') || t.platform !== 'telegram'}
                    title={
                      t.platform !== 'telegram'
                        ? '该平台的外呼流水线尚未接入，无法启动'
                        : telegramBusy
                          ? '常驻在线服务正在占用这个账号，请先停止服务'
                          : '启动任务：搜群 → 加群 → 取目标 → 主动私聊'
                    }
                    className="bg-green-600 text-white px-3 py-1 rounded text-xs hover:bg-green-700 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {t.status === 'paused' ? '▶️ 继续' : '▶️ 启动'}
                  </button>
                )}
                {t.status === 'running' && (
                  <button
                    onClick={() => cancelTask(t.id)}
                    className="bg-rose-600 text-white px-3 py-1 rounded text-xs hover:bg-rose-700"
                  >
                    ⏹ 取消
                  </button>
                )}
                <button
                  onClick={() => deleteTask(t.id)}
                  className="bg-white border border-rose-200 text-rose-600 px-3 py-1 rounded text-xs hover:bg-rose-50"
                >
                  🗑 删除
                </button>
              </td>
              <td className="px-4 py-2">{new Date(t.created_at).toLocaleString('zh-CN')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
