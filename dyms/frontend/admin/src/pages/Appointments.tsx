import React, { useState, useEffect } from 'react';

interface Appointment {
  id: number;
  status: string;
  appointment_type: string;
  scheduled_start: string;
  shipper_name: string;
  dock_code: string;
  truck_plate: string;
}

const STATUS_BADGE: Record<string, string> = {
  PENDING: 'bg-yellow-100 text-yellow-800',
  AUTO_CONFIRMED: 'bg-blue-100 text-blue-800',
  CHECKED_IN: 'bg-green-100 text-green-800',
  DOCK_ASSIGNED: 'bg-indigo-100 text-indigo-800',
  UNLOADING: 'bg-orange-100 text-orange-800',
  UNLOAD_COMPLETE: 'bg-teal-100 text-teal-800',
  NO_SHOW: 'bg-red-100 text-red-800',
  CLOSED: 'bg-gray-100 text-gray-800',
  CANCELLED: 'bg-gray-100 text-gray-500',
};

export default function Appointments() {
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState('');
  const token = localStorage.getItem('dyms_token') || '';

  useEffect(() => { fetchData(); }, [page, statusFilter]);

  async function fetchData() {
    const params = new URLSearchParams({ page: String(page), page_size: '20' });
    if (statusFilter) params.set('status', statusFilter);
    const res = await fetch(`/api/appointments?${params}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    setAppointments(data.data || []);
    setTotal(data.total || 0);
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Appointments</h1>
        <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
          className="border rounded-lg px-3 py-2 text-sm">
          <option value="">All Statuses</option>
          {Object.keys(STATUS_BADGE).map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      <div className="bg-white rounded-xl shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left font-semibold text-gray-600">ID</th>
              <th className="px-4 py-3 text-left font-semibold text-gray-600">Status</th>
              <th className="px-4 py-3 text-left font-semibold text-gray-600">Type</th>
              <th className="px-4 py-3 text-left font-semibold text-gray-600">Shipper</th>
              <th className="px-4 py-3 text-left font-semibold text-gray-600">Dock</th>
              <th className="px-4 py-3 text-left font-semibold text-gray-600">Truck</th>
              <th className="px-4 py-3 text-left font-semibold text-gray-600">Scheduled</th>
            </tr>
          </thead>
          <tbody>
            {appointments.map((a) => (
              <tr key={a.id} className="border-t hover:bg-gray-50 cursor-pointer">
                <td className="px-4 py-3 font-mono">#{a.id}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-1 rounded-full text-xs font-medium ${STATUS_BADGE[a.status] || ''}`}>
                    {a.status}
                  </span>
                </td>
                <td className="px-4 py-3">{a.appointment_type}</td>
                <td className="px-4 py-3">{a.shipper_name}</td>
                <td className="px-4 py-3 font-mono">{a.dock_code || '-'}</td>
                <td className="px-4 py-3">{a.truck_plate || '-'}</td>
                <td className="px-4 py-3 text-gray-500">{new Date(a.scheduled_start).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex justify-between items-center mt-4 text-sm text-gray-600">
        <span>Total: {total}</span>
        <div className="flex gap-2">
          <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page === 1}
            className="px-3 py-1 border rounded disabled:opacity-50">Prev</button>
          <span className="px-3 py-1">Page {page}</span>
          <button onClick={() => setPage(page + 1)} disabled={appointments.length < 20}
            className="px-3 py-1 border rounded disabled:opacity-50">Next</button>
        </div>
      </div>
    </div>
  );
}
