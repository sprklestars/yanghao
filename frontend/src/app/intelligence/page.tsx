'use client';

import { useState } from 'react';
import { downloadExport, fetchAPI, type IntelligenceRecord } from '@/lib/api';

export default function IntelligencePage() {
  const [records, setRecords] = useState<IntelligenceRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loaded, setLoaded] = useState(false);
  // 只有真的连不上后端才设置；没有情报记录是正常状态
  const [backendError, setBackendError] = useState('');
  const [filters, setFilters] = useState({ category: '', platform: '' });
  // 审核：状态下拉即时保存；备注用行内编辑
  const [savingId, setSavingId] = useState<string | null>(null);
  const [noteEditId, setNoteEditId] = useState<string | null>(null);
  const [noteDraft, setNoteDraft] = useState('');

  async function loadRecords() {
    try {
      const params = new URLSearchParams();
      if (filters.category) params.set('category', filters.category);
      if (filters.platform) params.set('platform', filters.platform);
      const data = await fetchAPI(`/intelligence?${params}`);
      setRecords(data.items);
      setTotal(data.total);
      setLoaded(true);
      setBackendError('');
    } catch (error: any) {
      console.error('Failed to load intelligence:', error);
      setRecords([]);
      setTotal(0);
      setLoaded(true);
      setBackendError(error?.message || '后端不可达');
    }
  }

  async function exportRecords(fmt: string) {
    const params = new URLSearchParams({ format: fmt });
    if (filters.category) params.set('category', filters.category);
    if (filters.platform) params.set('platform', filters.platform);
    try {
      await downloadExport(`/export/intelligence?${params}`);
    } catch (e: any) {
      alert(`导出失败：${e?.message || '请检查后端服务'}`);
    }
  }

  async function updateReview(id: string, patch: Record<string, unknown>) {
    setSavingId(id);
    try {
      await fetchAPI(`/intelligence/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(patch),
      });
      await loadRecords();
    } catch (e: any) {
      alert(`更新审核状态失败：${e?.message || '请检查后端服务'}`);
    } finally {
      setSavingId(null);
    }
  }

  async function saveNotes(id: string) {
    await updateReview(id, { operator_notes: noteDraft });
    setNoteEditId(null);
  }

  return (
    <div className="flex flex-col h-[calc(100vh-3rem)]">
      {backendError && (
        <div className="bg-rose-50 border-b border-rose-200 px-4 py-2 text-sm text-rose-800 mb-4 rounded">
          ⚠️ <strong>后端不可达:</strong> {backendError}
        </div>
      )}

      <div className="flex items-center justify-between mb-4">
        <h2 className="text-2xl font-bold">Intelligence Records</h2>
        <div className="flex gap-2">
          {(['csv', 'json', 'xlsx'] as const).map((fmt) => (
            <button
              key={fmt}
              onClick={() => exportRecords(fmt)}
              className="px-3 py-1.5 rounded text-xs font-medium bg-slate-900 text-white hover:bg-slate-800"
            >
              导出 {fmt.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      <div className="flex gap-3 mb-4 items-end">
        <select
          className="border px-3 py-2 rounded text-sm"
          value={filters.category}
          onChange={(e) => setFilters({ ...filters, category: e.target.value })}
        >
          <option value="">All Categories</option>
          <option value="private_investigator">Private Investigator</option>
          <option value="currency_exchanger">Currency Exchanger</option>
          <option value="freelancer">Freelancer</option>
          <option value="data_seller">Data Seller</option>
        </select>
        <select
          className="border px-3 py-2 rounded text-sm"
          value={filters.platform}
          onChange={(e) => setFilters({ ...filters, platform: e.target.value })}
        >
          <option value="">All Platforms</option>
          <option value="telegram">Telegram</option>
          <option value="facebook">Facebook</option>
          <option value="zalo">Zalo</option>
        </select>
        <button onClick={loadRecords} className="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700">
          {loaded ? 'Refresh' : 'Load'}
        </button>
        {loaded && <span className="text-sm text-gray-500">{total} records</span>}
      </div>

      <table className="w-full bg-white rounded shadow overflow-hidden text-sm">
        <thead className="bg-gray-100 text-left">
          <tr>
            <th className="px-4 py-2">Name</th>
            <th className="px-4 py-2">Platform</th>
            <th className="px-4 py-2">Category</th>
            <th className="px-4 py-2">Confidence</th>
            <th className="px-4 py-2">Activity</th>
            <th className="px-4 py-2">Status</th>
            <th className="px-4 py-2">操作</th>
            <th className="px-4 py-2">Collected</th>
          </tr>
        </thead>
        <tbody>
          {records.map((r) => (
            <tr key={r.id} className="border-t">
              <td className="px-4 py-2">{r.display_name || r.target_user_id}</td>
              <td className="px-4 py-2">
                <span className="capitalize">{r.platform}</span>
                {r.platforms && r.platforms.length > 1 && (
                  <span className="ml-1 text-xs text-amber-600" title={`跨平台命中：${r.platforms.join(', ')}`}>
                    🔗{r.platforms.length}
                  </span>
                )}
              </td>
              <td className="px-4 py-2">{r.category.replace(/_/g, ' ')}</td>
              <td className="px-4 py-2">{(r.confidence * 100).toFixed(0)}%</td>
              <td className="px-4 py-2">
                <span className={`px-2 py-0.5 rounded text-xs ${
                  r.activity_status === 'active' ? 'bg-green-100 text-green-800' :
                  r.activity_status === 'dormant' ? 'bg-yellow-100 text-yellow-800' :
                  'bg-gray-100 text-gray-800'
                }`}>
                  {r.activity_status}
                </span>
              </td>
              <td className="px-4 py-2">
                <select
                  value={r.review_status}
                  disabled={savingId === r.id}
                  onChange={(e) => updateReview(r.id, { review_status: e.target.value })}
                  className="border rounded px-2 py-1 text-xs disabled:opacity-50"
                >
                  <option value="pending">待审核</option>
                  <option value="reviewed">已审核</option>
                  <option value="approved">已通过</option>
                  <option value="rejected">已拒绝</option>
                </select>
                {r.operator_notes && (
                  <div
                    className="text-xs text-slate-500 mt-0.5 max-w-[180px] truncate"
                    title={r.operator_notes}
                  >
                    📝 {r.operator_notes}
                  </div>
                )}
              </td>
              <td className="px-4 py-2 align-top">
                {noteEditId === r.id ? (
                  <div className="flex flex-col gap-1">
                    <textarea
                      rows={2}
                      value={noteDraft}
                      onChange={(e) => setNoteDraft(e.target.value)}
                      placeholder="审核备注"
                      className="border rounded px-2 py-1 text-xs w-48"
                    />
                    <div className="flex gap-2">
                      <button
                        onClick={() => saveNotes(r.id)}
                        disabled={savingId === r.id}
                        className="text-xs text-blue-600 hover:underline disabled:opacity-50"
                      >
                        保存
                      </button>
                      <button
                        onClick={() => setNoteEditId(null)}
                        className="text-xs text-slate-500 hover:underline"
                      >
                        取消
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    onClick={() => {
                      setNoteEditId(r.id);
                      setNoteDraft(r.operator_notes || '');
                    }}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    📝 备注
                  </button>
                )}
              </td>
              <td className="px-4 py-2">{new Date(r.collected_at).toLocaleString()}</td>
            </tr>
          ))}
          {loaded && records.length === 0 && (
            <tr><td colSpan={8} className="px-4 py-8 text-center text-gray-500">No records found</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
