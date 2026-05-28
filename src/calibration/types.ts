export interface Point {
  x: number;
  y: number;
}

export interface CalibrationAnchor {
  id: 'A' | 'B' | 'C' | 'D';
  physical: Point;
  projector: Point;
}

export type SourceSquareFeet = 5 | 10;

export interface EvidenceLog {
  setupStartedAt: string;
  setupMinutes: number;
  measuredErrorInches: number;
  placementNotes: string;
  failureModes: string;
}

export interface GridDetectionFamily {
  angleDegrees: number;
  lineCount: number;
  score: number;
}

export interface DetectedGrid {
  sourceName: string;
  sourceUrl: string;
  imageWidth: number;
  imageHeight: number;
  corners: [Point, Point, Point, Point];
  columns: number;
  rows: number;
  confidence: number;
  latticeScore?: number;
  families: [GridDetectionFamily, GridDetectionFamily];
  detectedAt: string;
  message: string;
}

export interface ProjectionAlignment {
  source: 'detected-grid';
  mode: 'simulated-image-fit';
  alignedAt: string;
  meanCornerDeltaPixels: number;
  message: string;
}

export interface CalibrationState {
  version: 1;
  projector: {
    width: number;
    height: number;
  };
  sourceSquareFeet: SourceSquareFeet;
  showCalibrationPoints: boolean;
  showPhysicalGrid: boolean;
  showSourceGrid: boolean;
  brightness: number;
  anchors: CalibrationAnchor[];
  detectedGrid: DetectedGrid | null;
  projectionAlignment: ProjectionAlignment | null;
  projectionAlignmentIssue: string | null;
  evidence: EvidenceLog;
}

export interface RenderOptions {
  background: 'synthetic-mat' | 'transparent' | 'projector';
  showLabels: boolean;
}
