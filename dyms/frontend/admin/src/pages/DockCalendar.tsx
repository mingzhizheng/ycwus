import React, { useState, useEffect, useRef } from 'react';

interface Dock {
  id: number;
  code: string;
  status: string;
}

interface CalendarAppointment {
  id: number;
  status: string;
  appointment_type: string;
  scheduled_start: string;
  scheduled_end: string;
  dock_id: number;
  truck_plate: string;
  shipper_name: string;
  cargo_type: string;
}

const STATUS_COLORS: Record<string, string> = {
  PENDING: 'bg-yellow-200 border-yellow-400',
  AUTO_CONFIRMED: 'bg-blue-200 border-blue-400',
  CHECKED_IN: 'bg-green-200 border-green-400',
  DOCK_ASSIGNED: 'bg-indigo-200 border-indigo-400',
  UNLOADING: 'bg-orange-200 border-orange-400',
  UNLOAD_COMPLETE: 'bg-teal-200 border-teal-400',
  YARD_MOVED: 'bg-purple-200 border-purple-400',
  NO_SHOW: 'bg-red-200 border-red-400',
  CANCELLED: 'bg-gray-200 border-gray-400',
};

const HOURS = Array.from({ length: 10 }, (_, i) => i + 8); // 08:00 - 17:00

export default function DockCalendar() {
  const [date, setDate] = useState(new Date().toISOString().split('T')[0]);
  const [docks, setDocks] = useState<Dock[]>([]);
  const [appointments, setAppointments] = useState<CalendarAppointment[]>([]);
  const [selectedAppt, setSelectedAppt] = useState<CalendarAppointment | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const token = localStorage.getItem('dyms_token') || '';

  useEffect(() => {
    fetchCalendar();
    connectWebSocket();
    return () => { wsRef.current?.close(); };
  }, [date]);

  async function fetchCalendar() {
    try {
      const res = await fetch(`/api/calendar?facility_id=1&date=${date}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      setDocks(data.data.docks || []);
      setAppointments(data.data.appointments || []);
    } catch (e) {
      console.error('Failed to fetch calendar', e);
    }
  }

  function connectWebSocket() {
    if (wsRef.current) wsRef.current.close();
    const ws = new WebSocket(`ws://${location.host}/ws/calendar?facility_id=1&token=${token}`);
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === 'APPOINTMENT_STATUS_CHANGED' || msg.type === 'SLOT_LOCKED') {
        fetchCalendar(); // Refresh on any change
      }
    };
    wsRef.current = ws;
  }

  function getApptPosition(appt: CalendarAppointment) {
    const start = new Date(appt.scheduled_start);
    const end = new Date(appt.scheduled_end);
    const startHour = start.getUTCHours() + start.getUTCMinutes() / 60;
    const endHour = end.getUTCHours() + end.getUTCMinutes() / 60;
    const left = ((startHour - 8) / 9) * 100;
    const width = ((endHour - startHour) / 9) * 100;
    return { left: `${Math.max(0, left)}%`, width: `${Math.min(100 - left, width)}%` };
  }

  async function transitionStatus(apptId: number, toStatus: string, dockId?: number) {
    await fetch(`/api/appointments/${apptId}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ to_status: toStatus, dock_id: dockId }),
    });
    fetchCalendar();
    setSelectedAppt(null);
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-800">Dock Calendar</h1>
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="border rounded-lg px-4 py-2"
        />
      </div>

      {/* Gantt-style Calendar */}
      <div className="bg-white rounded-xl shadow-sm overflow-hidden">
        {/* Time header */}
        <div className="flex border-b">
          <div className="w-24 flex-shrink-0 p-3 bg-gray-50 font-semibold text-sm text-gray-600">Dock</div>
          <div className="flex-1 flex">
            {HOURS.map((h) => (
              <div key={h} className="flex-1 p-2 text-center text-xs text-gray-500 border-l">
                {String(h).padStart(2, '0')}:00
              </div>
            ))}
          </div>
        </div>

        {/* Dock rows */}
        {docks.map((dock) => (
          <div key={dock.id} className="flex border-b hover:bg-gray-50">
            <div className="w-24 flex-shrink-0 p-3 bg-gray-50 font-mono text-sm font-semibold">
              {dock.code}
              <span className={`ml-1 w-2 h-2 inline-block rounded-full ${
                dock.status === 'AVAILABLE' ? 'bg-green-400' :
                dock.status === 'OCCUPIED' ? 'bg-red-400' : 'bg-yellow-400'
              }`} />
            </div>
            <div className="flex-1 relative h-14">
              {/* Hour gridlines */}
              {HOURS.map((h) => (
                <div key={h} className="absolute top-0 bottom-0 border-l border-gray-100"
                  style={{ left: `${((h - 8) / 9) * 100}%` }} />
              ))}
              {/* Appointment blocks */}
              {appointments
                .filter((a) => a.dock_id === dock.id)
                .map((appt) => {
                  const pos = getApptPosition(appt);
                  return (
                    <div
                      key={appt.id}
                      className={`absolute top-1 bottom-1 rounded border-l-4 px-1 cursor-pointer text-xs overflow-hidden ${
                        STATUS_COLORS[appt.status] || 'bg-gray-100 border-gray-300'
                      }`}
                      style={{ left: pos.left, width: pos.width }}
                      onClick={() => setSelectedAppt(appt)}
                      title={`#${appt.id} ${appt.shipper_name} (${appt.status})`}
                    >
                      <div className="font-semibold truncate">{appt.shipper_name}</div>
                      <div className="truncate text-gray-600">{appt.truck_plate || appt.appointment_type}</div>
                    </div>
                  );
                })}
            </div>
          </div>
        ))}
      </div>

      {/* Detail panel */}
      {selectedAppt && (
        <div className="fixed inset-y-0 right-0 w-96 bg-white shadow-2xl p-6 overflow-y-auto z-50">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-bold">Appointment #{selectedAppt.id}</h2>
            <button onClick={() => setSelectedAppt(null)} className="text-gray-400 hover:text-gray-600 text-xl">&times;</button>
          </div>
          <div className="space-y-3 text-sm">
            <div><span className="text-gray-500">Status:</span> <span className="font-semibold">{selectedAppt.status}</span></div>
            <div><span className="text-gray-500">Type:</span> {selectedAppt.appointment_type}</div>
            <div><span className="text-gray-500">Shipper:</span> {selectedAppt.shipper_name}</div>
            <div><span className="text-gray-500">Truck:</span> {selectedAppt.truck_plate || 'N/A'}</div>
            <div><span className="text-gray-500">Cargo:</span> {selectedAppt.cargo_type}</div>
            <div><span className="text-gray-500">Start:</span> {new Date(selectedAppt.scheduled_start).toLocaleTimeString()}</div>
            <div><span className="text-gray-500">End:</span> {new Date(selectedAppt.scheduled_end).toLocaleTimeString()}</div>
          </div>

          {/* Action buttons based on status */}
          <div className="mt-6 space-y-2">
            {selectedAppt.status === 'PENDING' && (
              <button onClick={() => transitionStatus(selectedAppt.id, 'AUTO_CONFIRMED')}
                className="w-full bg-blue-600 text-white rounded-lg py-2 hover:bg-blue-700">
                Confirm Appointment
              </button>
            )}
            {selectedAppt.status === 'CHECKED_IN' && (
              <button onClick={() => transitionStatus(selectedAppt.id, 'DOCK_ASSIGNED', selectedAppt.dock_id)}
                className="w-full bg-indigo-600 text-white rounded-lg py-2 hover:bg-indigo-700">
                Assign Dock
              </button>
            )}
            {selectedAppt.status === 'DOCK_ASSIGNED' && (
              <button onClick={() => transitionStatus(selectedAppt.id, 'UNLOADING')}
                className="w-full bg-orange-600 text-white rounded-lg py-2 hover:bg-orange-700">
                Start Unloading
              </button>
            )}
            {selectedAppt.status === 'UNLOADING' && (
              <button onClick={() => transitionStatus(selectedAppt.id, 'UNLOAD_COMPLETE')}
                className="w-full bg-teal-600 text-white rounded-lg py-2 hover:bg-teal-700">
                Mark Unload Complete
              </button>
            )}
            {['PENDING', 'AUTO_CONFIRMED'].includes(selectedAppt.status) && (
              <button onClick={() => transitionStatus(selectedAppt.id, 'CANCELLED')}
                className="w-full bg-red-100 text-red-700 rounded-lg py-2 hover:bg-red-200">
                Cancel
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
