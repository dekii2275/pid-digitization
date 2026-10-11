const tabs = [
  { id: 'manage', label: 'Quản lý nhãn' },
  { id: 'create', label: 'Tạo nhãn mới' },
];

export default function SymbolLabelTabs({ activeTab, onChange }) {
  const navigate = (event) => {
    const index = tabs.findIndex((tab) => tab.id === activeTab);
    const next = {
      ArrowRight: (index + 1) % tabs.length,
      ArrowLeft: (index + tabs.length - 1) % tabs.length,
      Home: 0,
      End: tabs.length - 1,
    }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    onChange(tabs[next].id);
    event.currentTarget.parentElement.querySelectorAll('[role="tab"]')[next].focus();
  };

  return (
    <div className="symbol-label-tabs" role="tablist" aria-label="Nhãn symbol">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          id={`symbol-label-tab-${tab.id}`}
          aria-controls={`symbol-label-panel-${tab.id}`}
          aria-selected={activeTab === tab.id}
          tabIndex={activeTab === tab.id ? 0 : -1}
          onClick={() => onChange(tab.id)}
          onKeyDown={navigate}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
