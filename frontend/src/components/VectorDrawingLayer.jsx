import { cadKind } from '../services/cad';

export default function VectorDrawingLayer({ drawing, results, width, height }) {
  return (
    <svg
      className="review-vector-layer"
      width={width}
      height={height}
      viewBox={`0 0 ${drawing.width} ${drawing.height}`}
      aria-label="Bản vẽ vector có thể chỉnh sửa"
    >
      {(results?.symbols || []).map((symbol) => {
        const w = Number(symbol.width),
          h = Number(symbol.height),
          r = Math.min(w, h) * 0.42;
        const kind = cadKind(symbol);
        const fontSize = Math.max(4, Math.min(24, h * 0.18));
        return (
          <g
            key={symbol.id}
            transform={`translate(${Number(symbol.x) + w / 2} ${Number(symbol.y) + h / 2}) rotate(${Number(symbol.rotation) || 0})`}
          >
            <g fill="none" stroke="#173c4b" strokeWidth={1.5}>
              {kind === 'pump' || kind === 'instrument' ? (
                <>
                  <circle r={r} />
                  <line x1={-r} x2={r} y1={0} y2={0} />
                  {kind === 'pump' && (
                    <polyline
                      points={`${r * 0.35},${-r * 0.35} ${r * 0.8},0 ${r * 0.35},${r * 0.35}`}
                    />
                  )}
                </>
              ) : kind === 'valve' || kind === 'globe_valve' ? (
                <>
                  <polygon
                    points={`${-w / 2},${h / 2} ${w / 2},${-h / 2} ${w / 2},${h / 2} ${-w / 2},${-h / 2}`}
                  />
                  {kind === 'globe_valve' && <circle r={Math.min(w, h) * 0.14} fill="#173c4b" />}
                </>
              ) : kind === 'check_valve' ? (
                <>
                  <polygon points={`${-w / 2},${h / 2} ${w / 2},0 ${-w / 2},${-h / 2}`} />
                  <line x1={w / 2} x2={w / 2} y1={-h / 2} y2={h / 2} />
                </>
              ) : kind === 'connector' ? (
                <polygon
                  points={`${-w / 2},${h / 2} ${w * 0.3},${h / 2} ${w / 2},0 ${w * 0.3},${-h / 2} ${-w / 2},${-h / 2}`}
                />
              ) : (
                <>
                  <rect x={-w / 2} y={-h / 2} width={w} height={h} />
                  {kind === 'vessel' && (
                    <>
                      <line x1={-w / 2} x2={w / 2} y1={-h / 4} y2={-h / 4} />
                      <line x1={-w / 2} x2={w / 2} y1={h / 4} y2={h / 4} />
                    </>
                  )}
                </>
              )}
            </g>
            {symbol.tag && (
              <text x={-w / 2} y={h / 2 + fontSize * 1.5} fontSize={fontSize} fill="#173c4b">
                {symbol.tag}
              </text>
            )}
          </g>
        );
      })}
      {(results?.texts || []).map((text) => {
        const content = (text.text || '').replace(/\r\n?/g, '\n');
        const lines = content.split('\n');
        const multiline = lines.length > 1 || content.length > 240;
        const fontSize = multiline
          ? (Number(text.height) * 0.8) / (1 + ((lines.length - 1) * 5) / 3)
          : Math.max(1, Number(text.height) * 0.8);
        const anchorY = Number(text.y) + (multiline ? 0 : Number(text.height));
        const baseline = anchorY + (multiline ? fontSize : 0);
        return (
          <text
            key={text.id}
            x={Number(text.x)}
            y={baseline}
            transform={`rotate(${Number(text.rotation) || 0},${Number(text.x)},${anchorY})`}
            fontSize={fontSize}
            fill="#173c4b"
          >
            {lines.map((line, index) => (
              <tspan key={index} x={Number(text.x)} dy={index ? (fontSize * 5) / 3 : 0}>
                {line || '\u00a0'}
              </tspan>
            ))}
          </text>
        );
      })}
    </svg>
  );
}
