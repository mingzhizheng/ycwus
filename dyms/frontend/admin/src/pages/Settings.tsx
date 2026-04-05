import React, { useState, useEffect } from 'react';

export default function Settings() {
  const [locations, setLocations] = useState<any[]>([]);
  const [users, setUsers] = useState<any[]>([]);
  const [activeTab, setActiveTab] = useState<'locations' | 'users'>('locations');
  const token = localStorage.getItem('dyms_token') || '';

  useEffect(() => {
    fetchLocations();
    fetchUsers();
  }, []);

  async function fetchLocations() {
    const res = await fetch('/api/dock/locations?facility_id=1', {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    setLocations(data.data || []);
  }

  async function fetchUsers() {
    const res = await fetch('/api/auth/users', {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    setUsers(data.data || []);
  }

  async function toggleLocationStatus(id: number, currentStatus: string) {
    const newStatus = currentStatus === 'AVAILABLE' ? 'MAINTENANCE' : 'AVAILABLE';
    await fetch(`/api/dock/locations/${id}/status?status=${newStatus}`, {
      method: 'PATCH',
      headers: { Authorization: `Bearer ${token}` },
    });
    fetchLocations();
  }

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">Settings</h1>

      <div className="flex gap-2 mb-6">
        <button onClick={() => setActiveTab('locations')}
          className={`px-4 py-2 rounded-lg text-sm font-medium ${activeTab === 'locations' ? 'bg-blue-600 text-white' : 'bg-white text-gray-600'}`}>
          Dock & Yard Locations
        </button>
        <button onClick={() => setActiveTab('users')}
          className={`px-4 py-2 rounded-lg text-sm font-medium ${activeTab === 'users' ? 'bg-blue-600 text-white' : 'bg-white text-gray-600'}`}>
          Users
        </button>
      </div>

      {activeTab === 'locations' && (
        <div className="bg-white rounded-xl shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left font-semibold text-gray-600">Code</th>
                <th className="px-4 py-3 text-left font-semibold text-gray-600">Type</th>
                <th className="px-4 py-3 text-left font-semibold text-gray-600">Status</th>
                <th className="px-4 py-3 text-left font-semibold text-gray-600">Leveler</th>
                <th className="px-4 py-3 text-left font-semibold text-gray-600">Action</th>
              </tr>
            </thead>
            <tbody>
              {locations.map((loc: any) => (
                <tr key={loc.id} className="border-t">
                  <td className="px-4 py-3 font-mono font-semibold">{loc.code}</td>
                  <td className="px-4 py-3">{loc.location_type}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                      loc.status === 'AVAILABLE' ? 'bg-green-100 text-green-800' :
                      loc.status === 'OCCUPIED' ? 'bg-red-100 text-red-800' : 'bg-yellow-100 text-yellow-800'
                    }`}>{loc.status}</span>
                  </td>
                  <td className="px-4 py-3">{loc.has_leveler ? 'Yes' : 'No'}</td>
                  <td className="px-4 py-3">
                    <button onClick={() => toggleLocationStatus(loc.id, loc.status)}
                      className="text-blue-600 hover:underline text-xs">
                      {loc.status === 'AVAILABLE' ? 'Set Maintenance' : 'Set Available'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {activeTab === 'users' && (
        <div className="bg-white rounded-xl shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left font-semibold text-gray-600">ID</th>
                <th className="px-4 py-3 text-left font-semibold text-gray-600">Username</th>
                <th className="px-4 py-3 text-left font-semibold text-gray-600">Display Name</th>
                <th className="px-4 py-3 text-left font-semibold text-gray-600">Role</th>
                <th className="px-4 py-3 text-left font-semibold text-gray-600">Active</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u: any) => (
                <tr key={u.id} className="border-t">
                  <td className="px-4 py-3">{u.id}</td>
                  <td className="px-4 py-3 font-mono">{u.username}</td>
                  <td className="px-4 py-3">{u.display_name}</td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-1 bg-gray-100 rounded text-xs">{u.role}</span>
                  </td>
                  <td className="px-4 py-3">{u.is_active ? 'Yes' : 'No'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
