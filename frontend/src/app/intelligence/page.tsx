'use client';

import { useState } from 'react';
import { fetchAPI, type IntelligenceRecord } from '@/lib/api';

export default function IntelligencePage() {
  const [records, setRecords] = useState<IntelligenceRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loaded, setLoaded] = useState(false);
  // 只有真的连不上后端才设置；没有情报记录是正常状态
  const [backendError, setBackendError] = useState('');
  const [filters, setFilters] = useState({ category: '', platform: '' });

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

  return (
    <div className="flex flex-col h-[calc(100vh-3rem)]">
      {backendError && (
        <div className="bg-rose-50 border-b border-rose-200 px-4 py-2 text-sm text-rose-800 mb-4 rounded">
          ⚠️ <strong>后端不可达:</strong> {backendError}
        </div>
      )}

      <h2 className="text-2xl font-bold mb-4">Intelligence Records</h2>

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
            <th className="px-4 py-2">Collected</th>
          </tr>
        </thead>
        <tbody>
          {records.map((r) => (
            <tr key={r.id} className="border-t">
              <td className="px-4 py-2">{r.display_name || r.target_user_id}</td>
              <td className="px-4 py-2 capitalize">{r.platform}</td>
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
              <td className="px-4 py-2 capitalize">{r.review_status}</td>
              <td className="px-4 py-2">{new Date(r.collected_at).toLocaleString()}</td>
            </tr>
          ))}
          {loaded && records.length === 0 && (
            <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-500">No records found</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
