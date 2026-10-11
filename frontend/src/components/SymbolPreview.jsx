export default function SymbolPreview({ symbol, compact = false, expanded = false, onError }) {
  if (!symbol?.preview) return <span aria-hidden="true">—</span>;
  if (!symbol.preview_width)
    return (
      <img
        className={compact ? 'symbol-preview-small' : 'symbol-preview'}
        src={symbol.preview}
        alt=""
        onError={onError}
      />
    );

  const scale = expanded
    ? Math.min(2, 460 / symbol.preview_width, 280 / symbol.preview_height)
    : compact
      ? 0.22
      : 0.4;
  return (
    <span
      className="symbol-preview-sheet"
      aria-hidden="true"
      style={{
        width: symbol.preview_width * scale,
        height: symbol.preview_height * scale,
        backgroundImage: `url(${symbol.preview})`,
        backgroundSize: `${298 * scale}px ${421 * scale}px`,
        backgroundPosition: `${-symbol.preview_left * scale}px ${-symbol.preview_top * scale}px`,
      }}
    />
  );
}
