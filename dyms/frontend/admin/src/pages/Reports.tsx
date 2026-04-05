import React, { useState, useEffect } from 'react';

export default function Reports() {
  const [tab, setTab] = useState<'utilization' | 'billing' | 'ranking'>('utilization');
  const [startDate, setStartDate] = useState(new Date(Date.now() - 30 * 86400000).toISOString().split('T')[0]);
  const [endDate, setEndDate] = useState(new Date().toISOString().split('T')[0]);
  const [data, setData] = useState<any[]>([]);
  const token = localStorage.getItem('dyms_token') || '';

  useEffect(() => { fetchReport(); }, [tab, startDate, endDate]);

  async function fetchReport() {
    let url = '';
    if (tab === 'utilization') url = `/api/reports/dock-utilization?facility_id=1&start_date=${startDate}&end_date=${endDate}`;
    else if (tab === 'billing') url = `/api/billing/summary?facility_id=1&period_start=${startDate}&period_end=${endDate}`;
    else url = `/api/reports/shipper-ranking?start_date=${startDate}&end_date=${endDate}`;

    const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
    const result = await res.json();
    setData(result.data || []);
  }

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">Reports</h1>

      <div className="flex items-center gap-4 mb-6">
        <div className="flex bg-white rounded-lg shadow-sm">
          {(['utilization', 'billing', 'ranking'] as const).map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-4 py-2 text-sm font-medium capitalize ${tab === t ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-50'} ${t === 'utilization' ? 'rounded-l-lg' : ''} ${t === 'ranking' ? 'rounded-r-lg' : ''}`}>
              {t === 'utilization' ? 'Dock Utilization' : t === 'billing' ? 'Billing Summary' : 'Shipper Ranking'}
            </button>
          ))}
        </div>
        <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="border rounded px-3 py-2 text-sm" />
        <span className="text-gray-400">to</span>
        <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="border rounded px-3 py-2 text-sm" />
      </div>

      <div className="bg-white rounded-xl shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              {data.length > 0 && Object.keys(data[0]).map((key) => (
                <th key={key} className="px-4 py-3 text-left font-semibold text-gray-600 capitalize">
                  {key.replace(/_/g, ' ')}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row, i) => (
              <tr key={i} className="border-t hover:bg-gray-50">
                {Object.values(row).map((val: any, j) => (
                  <td key={j} className="px-4 py-3">
                    {typeof val === 'number' ? val.toLocaleString() : String(val ?? '-')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {data.length === 0 && (
          <div className="p-8 text-center text-gray-400">No data for the selected period</div>
        )}
      </div>
    </div>
  );
}
