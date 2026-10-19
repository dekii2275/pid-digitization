export function cadKind(symbol) {
  if (symbol.cad_kind) return symbol.cad_kind;
  const name = `${symbol.type || ''} ${symbol.category || ''}`.toLowerCase();
  const code = String(symbol.label_id || '').toUpperCase();
  if (code === 'LC-001' || /off.page|line connection|signal line within a unit/.test(name))
    return 'connector';
  if (code === 'VALVES-012' || (/valve/.test(name) && /check|non.return/.test(name)))
    return 'check_valve';
  if (code === 'VALVES-020' || /globe valve/.test(name)) return 'globe_valve';
  if (/valve/.test(name)) return 'valve';
  if (/pump|compressor|blower/.test(name)) return 'pump';
  if (/instrument|indicator|transmitter|gauge/.test(name)) return 'instrument';
  if (/vessel|tank|drum|column|separator|exchanger/.test(name)) return 'vessel';
  return 'other';
}
