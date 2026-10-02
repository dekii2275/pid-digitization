const groups = [
  {
    prefix: 'PIP', category: 'Piping', source: '8474L-000-PID-0090-002-2.pdf',
    names: [
      'Main process line (arrow indicates direction of flow)', 'Secondary process line and service line', 'Future line', 'Underground line',
      'Lines crossing (unconnected)', 'Traced line', 'Jacketed line', 'Indication of point of change', 'Change in fall',
      'Change in piping class', 'Change in responsibility', 'End cap, butt welded', 'End flanged and bolted', 'Indication of fall',
      'No low point line', 'Free draining line', 'Grade', 'Above ground/underground',
      'Draining/venting indication for horizontally shown line', 'Draining/venting indication for vertically shown line',
      'Battery limit (BL)', 'Package limit', 'Vendor scope of supply boundary', 'Vendor supply/contractor supply',
    ],
  },
  {
    prefix: 'PGE', category: 'Piping general equipment', source: '8474L-000-PID-0090-002-2.pdf',
    names: [
      'Spectacle blind (closed)', 'Spectacle blind (open)', 'Spade blind', 'Ring spacer', 'Welded joint', 'Flanged connection',
      'Spool piece', 'Elbow type spool piece', 'Swing elbow', 'Steam trap-water trap', 'Drain cap', 'Concentric reducer (general)',
      'Top flat reducer', 'Bottom flat reducer', 'Ejector', 'Flexible hose (flanged)', 'Venturi', 'Corrosion coupon (XXX sequential number)',
      'Corrosion probe (XXX sequential number)', 'Special piping item (unit/block number and sequential number)',
      'Twin basket strainer/filter', 'Single basket strainer/filter/steam entrainer', 'Cartridge filter',
      'Y type strainer (up to 2 in)', 'T type strainer (3 to 24 in, horizontal position)',
      'T type strainer (3 to 24 in, vertical position)', 'Conical strainer', 'Vortex breaker', 'Expansion bellows',
    ],
  },
  {
    prefix: 'PCT', category: 'Piping general equipment (control)', source: '8474L-000-PID-0090-002-2.pdf',
    names: [
      'Open vent', 'Vent with screen', 'Vent with weather hood', 'Air vent', 'Open drain', 'Spray device', 'Safety shower',
      'Eyebath/face wash', 'In-line silencer', 'Vent silencer', 'Syphon drain (seal leg)', 'Bursting disc (set pressure)',
      'Flame arrestor', 'Hose connection', 'Air intake filter', 'Calibration pot', 'Quick release and closure',
      'Sampling connection', 'Sampling connection with cooler', 'Miscellaneous',
    ],
  },
  {
    prefix: 'VLV', category: 'Valves', source: '8474L-000-PID-0090-002-2.pdf',
    names: [
      'Twin seal valve (for slurry service)', 'Parallel slide valve', 'Soft seal', 'Bellows seal',
      'Valve open with tail pipe and open end', 'Three-way ball-valve', 'Four-way ball-valve', 'Angle valve',
      'Three way valve', 'Four way valve', 'Gauge valve', 'Check/non return valve', 'Check valve with recirculation',
      'Non return valve (screw down type)', 'Excess flow valve', 'Automatic recirculation control valve (Schroeder type check valve)',
      'Slide valve', 'Damper', 'Gate valve', 'Globe valve', 'Ball valve', 'Full bore ball valve', 'Needle valve',
      'Diaphragm valve', 'Butterfly valve', 'Plug valve', 'Screwed valve with plug', 'Rotary star valve (fall through)',
      'Orbit valve', 'Pilot operated relief valve', 'Y-globe valve', 'Intermittent blowdown (slow off) valve (UOP)',
      'Continuous blowdown valve (UOP)', 'Float valve', 'Angle blowdown valve', 'Pressure relief valve (angle)',
      'Pressure/vacuum valve', 'Diaphragm',
    ],
  },
  {
    prefix: 'LCO', category: 'Line connector', source: '8474L-000-PID-0090-002-2.pdf',
    names: [
      'Process/instrument signal line entering or leaving a drawing within a unit',
      'All lines entering or leaving a unit or battery limits',
      'Interconnecting P&ID for lines leaving or entering block 001',
      'Utility lines to/from UDD shown on process P&ID',
    ],
  },
  {
    prefix: 'ITR', category: 'Instrument tracing', source: '8474L-000-PID-0090-002-2.pdf',
    names: [
      'Field-mounted pressure gauge (PG)', 'Panel-mounted pressure indicator (PI)',
      'Field-mounted pressure indicating transmitter (PIT)', 'Control-room flow indicating controller (FIC)',
    ],
  },
  {
    prefix: 'HEX', category: 'Heat exchangers', source: '8474L-000-PID-0090-003-2.pdf',
    names: [
      'Heat exchanger/cooler/condenser shell/tube basic symbol', 'Air-cooled heat exchanger induced draught',
      'Air-cooled heat exchanger forced draught, with automatic louvre or variable pitch control', 'Fin tube air cooler',
      'Vertical heat exchanger/reboiler/tubular steam generator/cooler/condenser', 'Heat exchanger/U-tube',
      'Kettle-type reboiler, U-tube', 'Plate heat exchanger', 'Sample cooler', 'Equalising line', 'Line pressuring',
      'Barometric condenser', 'Fiber-film contactor',
    ],
  },
  {
    prefix: 'DRM', category: 'Drums & separators', source: '8474L-000-PID-0090-003-2.pdf',
    names: [
      'Vertical two phases drum with mesh', 'Vertical two phases drum with vane pack',
      'Horizontal drum or separator two or three phases', 'Horizontal drum or separator two or three phases with boot',
    ],
  },
  {
    prefix: 'COL', category: 'Columns', source: '8474L-000-PID-0090-003-2.pdf',
    names: ['Column with n trays', 'Column with packing', 'Column with two shell diameters'],
  },
  {
    prefix: 'TNK', category: 'Tanks', source: '8474L-000-PID-0090-003-2.pdf',
    names: [
      'Conical roof tank (CR)', 'Internal floating conical roof tank (IFR)', 'Internal floating dome roof tank', 'Chemical drum',
      'Mixed LPG bullet', 'Floating roof tank', 'Open top tank', 'Sphere', 'Sump pit', 'Neutralisation pit',
      'Cone bottom hopper or bin', 'Propeller blades', 'Paddle blades',
    ],
  },
  {
    prefix: 'HTR', category: 'Heaters', source: '8474L-000-PID-0090-003-2.pdf',
    names: ['Furnace/heater', 'Heat recovery steam generator', 'Electrical heater'],
  },
  {
    prefix: 'PMP', category: 'Compressors & pumps', source: '8474L-000-PID-0090-003-2.pdf',
    names: [
      'Reciprocating compressor single-stage', 'Rotary compressor centrifugal', 'Rotary or screw pump (motor driven type)',
      'Centrifugal blower', 'Reciprocating pump (steam driven)', 'Centrifugal pump (turbine driven)', 'Diaphragm pump',
      'Progressive cavity pump (motor driven)', 'Centrifugal pump (motor driven)', 'Barrel pump (LPG propane)', 'Vertical pump',
      'Oil skimmer pump', 'Vertical in-line pump', 'Centrifugal pump (vertical sump type, motor driven)',
      'Proportioning pump (motor driven)', 'Pulsation damper (pumps)', 'Pulsation damper (for compressors - internals prohibited)',
    ],
  },
  {
    prefix: 'DRV', category: 'Drivers', source: '8474L-000-PID-0090-003-2.pdf',
    names: ['Electric motor', 'Hydraulic motor', 'Diesel motor', 'Air motor', 'Turbine', 'Reciprocating engine'],
  },
  {
    prefix: 'MSC', category: 'Miscellaneous', source: '8474L-000-PID-0090-004-2.pdf',
    names: [
      'Clarifier/thickener', 'Aerator', 'Decanting centrifuge', 'Steam turbogenerator', 'Gas turbine generator', 'Percolating filter',
      'Ship loading arm with emergency release system', 'Truck loading arm', 'Air sparger (Merichem units)', 'Desuperheater',
      'Pig launcher/receiver', 'Plate pack', 'Fixed oil skimmer inside of tank', 'Floating oil skimmer', 'Gas cylinder',
      'Level instrument (ETP plant)', 'Charging bucket', 'Hopper', 'Screw feed conveyor', 'Seal pot',
    ],
  },
  {
    prefix: 'MIX', category: 'Mixers', source: '8474L-000-PID-0090-004-2.pdf',
    names: ['Mixer', 'Static mixer', 'Orifice mixer', 'Jet mixer in tank', 'Sparger'],
  },
];

export const symbolLabels = groups.flatMap(({ prefix, category, source, names }) =>
  names.map((name, index) => ({
    id: `${prefix}-${String(index + 1).padStart(3, '0')}`,
    name,
    category,
    source,
    preview: `/symbols/${prefix}-${String(index + 1).padStart(3, '0')}.png`,
  })),
);

export const symbolLabelCount = symbolLabels.length;
