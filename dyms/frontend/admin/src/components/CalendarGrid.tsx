import React from 'react';

interface CalendarGridProps {
  hours: number[];
  children: React.ReactNode;
}

export default function CalendarGrid({ hours, children }: CalendarGridProps) {
  return (
    <div className="relative">
      {/* Hour markers */}
      <div className="flex border-b">
        <div className="w-24 flex-shrink-0" />
        {hours.map((h) => (
          <div key={h} className="flex-1 text-center text-xs text-gray-400 py-1 border-l border-gray-100">
            {String(h).padStart(2, '0')}:00
          </div>
        ))}
      </div>
      {children}
    </div>
  );
}
