import React, { useRef, useState } from 'react';

interface DragBlockProps {
  id: number;
  label: string;
  sublabel?: string;
  color: string;
  style: React.CSSProperties;
  onClick?: () => void;
  onDragEnd?: (newLeft: number) => void;
}

export default function DragBlock({ id, label, sublabel, color, style, onClick, onDragEnd }: DragBlockProps) {
  const [isDragging, setIsDragging] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  return (
    <div
      ref={ref}
      className={`absolute top-1 bottom-1 rounded border-l-4 px-1 cursor-pointer text-xs overflow-hidden transition-opacity ${color} ${isDragging ? 'opacity-50' : ''}`}
      style={style}
      draggable
      onClick={onClick}
      onDragStart={() => setIsDragging(true)}
      onDragEnd={(e) => {
        setIsDragging(false);
        if (onDragEnd && ref.current) {
          const rect = ref.current.parentElement?.getBoundingClientRect();
          if (rect) {
            const newLeft = (e.clientX - rect.left) / rect.width;
            onDragEnd(newLeft);
          }
        }
      }}
    >
      <div className="font-semibold truncate">{label}</div>
      {sublabel && <div className="truncate text-gray-600">{sublabel}</div>}
    </div>
  );
}
