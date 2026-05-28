import type { CalibrationAnchor, CalibrationState, Point } from './types';

export const STORAGE_KEY = 'rpg-map-projector:story-001-calibration';
export const CHANNEL_NAME = 'rpg-map-projector:story-001-calibration';

export const defaultState: CalibrationState = {
  version: 1,
  projector: {
    width: 1280,
    height: 800,
  },
  sourceSquareFeet: 5,
  showCalibrationPoints: true,
  showPhysicalGrid: true,
  showSourceGrid: true,
  brightness: 1,
  anchors: [
    { id: 'A', physical: { x: 0, y: 0 }, projector: { x: 138, y: 118 } },
    { id: 'B', physical: { x: 12, y: 0 }, projector: { x: 1140, y: 96 } },
    { id: 'C', physical: { x: 12, y: 8 }, projector: { x: 1084, y: 680 } },
    { id: 'D', physical: { x: 0, y: 8 }, projector: { x: 170, y: 706 } },
  ],
  detectedGrid: null,
  projectionAlignment: null,
  projectionAlignmentIssue: null,
  evidence: {
    setupStartedAt: new Date().toISOString(),
    setupMinutes: 0,
    measuredErrorInches: 0,
    placementNotes: '',
    failureModes: '',
  },
};

export function readState(): CalibrationState {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return cloneState(defaultState);
    return normalizeState(JSON.parse(raw) as Partial<CalibrationState>);
  } catch {
    return cloneState(defaultState);
  }
}

export function writeState(state: CalibrationState): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

export function createStateChannel(onState: (state: CalibrationState) => void): {
  publish: (state: CalibrationState) => void;
  close: () => void;
} {
  let channel: BroadcastChannel | null = null;

  if ('BroadcastChannel' in window) {
    channel = new BroadcastChannel(CHANNEL_NAME);
    channel.onmessage = (event: MessageEvent<CalibrationState>) => {
      onState(normalizeState(event.data));
    };
  }

  const onStorage = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY && event.newValue) {
      onState(normalizeState(JSON.parse(event.newValue) as Partial<CalibrationState>));
    }
  };
  window.addEventListener('storage', onStorage);

  return {
    publish: (state) => {
      writeState(state);
      channel?.postMessage(state);
    },
    close: () => {
      window.removeEventListener('storage', onStorage);
      channel?.close();
    },
  };
}

export function cloneState(state: CalibrationState): CalibrationState {
  return JSON.parse(JSON.stringify(state)) as CalibrationState;
}

export function nudgeAnchors(anchors: CalibrationAnchor[], dx: number, dy: number): CalibrationAnchor[] {
  return anchors.map((anchor) => ({
    ...anchor,
    projector: {
      x: anchor.projector.x + dx,
      y: anchor.projector.y + dy,
    },
  }));
}

export function scaleAnchors(anchors: CalibrationAnchor[], factor: number): CalibrationAnchor[] {
  const center = centroid(anchors.map((anchor) => anchor.projector));
  return anchors.map((anchor) => ({
    ...anchor,
    projector: {
      x: center.x + (anchor.projector.x - center.x) * factor,
      y: center.y + (anchor.projector.y - center.y) * factor,
    },
  }));
}

export function rotateAnchors(anchors: CalibrationAnchor[], degrees: number): CalibrationAnchor[] {
  const center = centroid(anchors.map((anchor) => anchor.projector));
  const radians = (degrees * Math.PI) / 180;
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);

  return anchors.map((anchor) => {
    const x = anchor.projector.x - center.x;
    const y = anchor.projector.y - center.y;
    return {
      ...anchor,
      projector: {
        x: center.x + x * cos - y * sin,
        y: center.y + x * sin + y * cos,
      },
    };
  });
}

function normalizeState(input: Partial<CalibrationState>): CalibrationState {
  const merged = {
    ...cloneState(defaultState),
    ...input,
    projector: { ...defaultState.projector, ...input.projector },
    detectedGrid: input.detectedGrid ?? null,
    projectionAlignment: input.projectionAlignment ?? null,
    projectionAlignmentIssue: input.projectionAlignmentIssue ?? null,
    evidence: { ...defaultState.evidence, ...input.evidence },
  };

  if (!Array.isArray(input.anchors) || input.anchors.length !== 4) {
    merged.anchors = cloneState(defaultState).anchors;
  }

  return merged as CalibrationState;
}

function centroid(points: Point[]): Point {
  const sum = points.reduce(
    (acc, point) => ({ x: acc.x + point.x, y: acc.y + point.y }),
    { x: 0, y: 0 },
  );
  return { x: sum.x / points.length, y: sum.y / points.length };
}
