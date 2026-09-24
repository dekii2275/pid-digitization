import React from 'react';
import { Upload, Scan, Type, Share2, FileCode2 } from 'lucide-react';

export function Stepper({ activeStep, onStepChange, counts }) {
  const steps = [
    {
      id: 1,
      title: '1. Input: P&ID',
      subtitle: 'Ảnh / PDF bản vẽ',
      icon: Upload,
    },
    {
      id: 2,
      title: '2. Detect kết quả',
      subtitle: `${counts?.symbols || 0} Symbols (5 loại)`,
      icon: Scan,
    },
    {
      id: 3,
      title: '3. OCR kết quả',
      subtitle: `${counts?.ocr || 0} Text & Tags`,
      icon: Type,
    },
    {
      id: 4,
      title: '4. Hiểu quan hệ',
      subtitle: `${counts?.relationships || 0} Quan hệ kết nối`,
      icon: Share2,
    },
    {
      id: 5,
      title: '5. Sản phẩm đầu ra',
      subtitle: 'JSON, DEXPI & Tra cứu',
      icon: FileCode2,
    },
  ];

  return (
    <div style={{
      background: 'var(--bg-secondary)',
      borderBottom: '1px solid var(--border-color)',
      padding: '0.5rem 1.5rem',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: '0.75rem',
      overflowX: 'auto',
    }}>
      {steps.map((step) => {
        const Icon = step.icon;
        const isActive = activeStep === step.id;

        return (
          <button
            key={step.id}
            onClick={() => onStepChange(step.id)}
            style={{
              flex: 1,
              minWidth: '200px',
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
              padding: '0.65rem 1rem',
              borderRadius: '0.5rem',
              background: isActive ? 'var(--bg-card)' : 'transparent',
              border: `1px solid ${isActive ? 'var(--accent-cyan)' : 'transparent'}`,
              color: isActive ? '#fff' : 'var(--text-secondary)',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
              textAlign: 'left',
              boxShadow: isActive ? '0 4px 15px rgba(14, 165, 233, 0.15)' : 'none',
            }}
          >
            <div style={{
              width: '32px',
              height: '32px',
              borderRadius: '6px',
              background: isActive ? 'linear-gradient(135deg, var(--accent-cyan), var(--accent-blue))' : 'var(--bg-primary)',
              color: isActive ? '#fff' : 'var(--text-muted)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}>
              <Icon size={18} />
            </div>

            <div style={{ overflow: 'hidden' }}>
              <div style={{
                fontSize: '0.85rem',
                fontWeight: isActive ? '600' : '500',
                color: isActive ? '#fff' : 'var(--text-primary)',
                whiteSpace: 'nowrap',
                textOverflow: 'ellipsis',
                overflow: 'hidden',
              }}>
                {step.title}
              </div>
              <div style={{
                fontSize: '0.75rem',
                color: isActive ? 'var(--accent-cyan)' : 'var(--text-muted)',
                whiteSpace: 'nowrap',
                textOverflow: 'ellipsis',
                overflow: 'hidden',
              }}>
                {step.subtitle}
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}
