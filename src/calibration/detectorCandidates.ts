import type { GridFixtureIdentity, GridFixtureLabel } from './fixtureLabels';
import { evaluateDetectedGridForAutoAlign } from './detectedGridProjection';
import {
  detectAggressiveHoughGridFromImage,
  detectBoundaryFirstGridFitFromImage,
  detectColorRegionBoundarySeedFromImage,
  detectGridFromImage,
  detectLooseAxisAlignedGridFromImage,
} from './gridDetection';
import type { DetectedGrid } from './types';

export type DetectorCandidateCategory =
  | 'passive'
  | 'active-calibration'
  | 'fiducial'
  | 'assisted'
  | 'hybrid'
  | 'evaluation-control';

export type DetectorCandidateStatus =
  | 'implemented'
  | 'planned'
  | 'research-only'
  | 'control';

export interface DetectorCandidateContext {
  image: HTMLImageElement;
  fixture: GridFixtureIdentity;
  label?: GridFixtureLabel;
}

export interface DetectorCandidate {
  id: string;
  name: string;
  category: DetectorCandidateCategory;
  status: DetectorCandidateStatus;
  runtime: string;
  summary: string;
  promotionRisk: string;
  usesGroundTruth?: boolean;
  run?: (context: DetectorCandidateContext) => Promise<DetectedGrid>;
}

export interface RunnableDetectorCandidate extends DetectorCandidate {
  run: (context: DetectorCandidateContext) => Promise<DetectedGrid>;
}

export const DETECTOR_CANDIDATES: DetectorCandidate[] = [
  {
    id: 'passive-browser-lattice-v1',
    name: 'Current Passive Browser Lattice',
    category: 'passive',
    status: 'implemented',
    runtime: 'Browser TypeScript/canvas',
    summary: 'Current Story 001/002 detector using edge evidence, line-family regularity, and lattice-support gates.',
    promotionRisk: 'Can remain useful only if it improves recall without creating wrong-confident auto-alignments.',
    run: ({ image, fixture }) => detectGridFromImage(image, fixture.sourceName, fixture.sourceUrl),
  },
  {
    id: 'aggressive-hough-line-family-v1',
    name: 'Aggressive Hough Line-Family Candidate',
    category: 'passive',
    status: 'implemented',
    runtime: 'Browser TypeScript/canvas',
    summary: 'A discovery-only variant that relaxes Hough thresholds and allows out-of-frame corners to see whether weak line-family geometry can become useful manual seeds.',
    promotionRisk: 'Never auto-promote as-is; reject if added recall is mostly wrong geometry, packaging, or tiny partial grids.',
    run: ({ image, fixture }) => detectAggressiveHoughGridFromImage(image, fixture.sourceName, fixture.sourceUrl),
  },
  {
    id: 'loose-axis-aligned-line-run-v1',
    name: 'Loose Axis-Aligned Line-Run Candidate',
    category: 'passive',
    status: 'implemented',
    runtime: 'Browser TypeScript/canvas',
    summary: 'A discovery-only detector for straight-on or nearly straight product images, using lower-threshold horizontal and vertical line-spacing runs.',
    promotionRisk: 'Reject if it only works on pristine product shots or inflates partial/inset grids.',
    run: ({ image, fixture }) => detectLooseAxisAlignedGridFromImage(image, fixture.sourceName, fixture.sourceUrl),
  },
  {
    id: 'color-region-boundary-seed-v1',
    name: 'Color Region Boundary Seed',
    category: 'assisted',
    status: 'implemented',
    runtime: 'Browser TypeScript/canvas',
    summary: 'Finds the largest low-saturation mat-like color component and returns a rough candidate-only quadrilateral as a manual correction seed.',
    promotionRisk: 'Never auto-promote; reject if props, scrolls, paper, or table surfaces dominate the color component.',
    run: ({ image, fixture }) => detectColorRegionBoundarySeedFromImage(image, fixture.sourceName, fixture.sourceUrl),
  },
  {
    id: 'boundary-first-grid-fit-v1',
    name: 'Boundary-First Rectified Grid Fit',
    category: 'passive',
    status: 'implemented',
    runtime: 'Browser TypeScript/canvas',
    summary: 'Finds a mat-like color boundary, rectifies that region, then searches the rectified image for regular horizontal and vertical grid-line runs.',
    promotionRisk: 'Reject if boundary rectification locks onto packaging/mat borders or if line runs infer partial grids instead of the full playable extent.',
    run: ({ image, fixture }) => detectBoundaryFirstGridFitFromImage(image, fixture.sourceName, fixture.sourceUrl),
  },
  {
    id: 'hybrid-passive-boundary-seed-v1',
    name: 'Hybrid Passive Then Boundary Seed',
    category: 'hybrid',
    status: 'implemented',
    runtime: 'Browser TypeScript/canvas',
    summary: 'Uses the current passive lattice only when auto-align gates pass; otherwise falls back to the color-region boundary seed as a manual correction starting point.',
    promotionRisk: 'Promote only as an assisted seed path unless real-camera evidence shows the fallback is accurate enough to auto-apply.',
    run: async ({ image, fixture }) => {
      try {
        const passive = await detectGridFromImage(image, fixture.sourceName, fixture.sourceUrl);
        const quality = evaluateDetectedGridForAutoAlign(passive);
        if (quality.ok) {
          return {
            ...passive,
            message: `Hybrid accepted passive lattice: ${passive.message}`,
          };
        }
      } catch {
        // Fall through to the boundary seed.
      }

      const boundary = await detectColorRegionBoundarySeedFromImage(image, fixture.sourceName, fixture.sourceUrl);
      return {
        ...boundary,
        message: `Hybrid used boundary correction seed: ${boundary.message}`,
      };
    },
  },
  {
    id: 'label-truth-control',
    name: 'Label Truth Control',
    category: 'evaluation-control',
    status: 'control',
    runtime: 'Benchmark harness only',
    summary: 'Returns the saved label as a perfect detection to verify scorecard plumbing. It is not a real detector.',
    promotionRisk: 'Never promote; this uses benchmark ground truth.',
    usesGroundTruth: true,
    run: async ({ label }) => {
      if (!label) throw new Error('Label truth control requires benchmark ground truth.');
      return {
      sourceName: label.sourceName,
      sourceUrl: label.sourceUrl,
      imageWidth: label.imageWidth,
      imageHeight: label.imageHeight,
      corners: label.corners,
      columns: label.columns,
      rows: label.rows,
      confidence: 1,
      latticeScore: 1,
      families: [
        { angleDegrees: 0, lineCount: label.rows + 1, score: 1000 },
        { angleDegrees: 90, lineCount: label.columns + 1, score: 1000 },
      ],
      detectedAt: new Date().toISOString(),
      message: 'Evaluation control copied saved fixture truth.',
      };
    },
  },
  {
    id: 'robust-passive-lattice-ensemble',
    name: 'Robust Passive Lattice Ensemble',
    category: 'passive',
    status: 'planned',
    runtime: 'Browser TypeScript, OpenCV.js, or Python/OpenCV gateway',
    summary: 'Combine multiple passive cues: line segments, orientation histograms, vanishing consistency, periodic spacing, and visible coverage.',
    promotionRisk: 'Reject if broader recall comes from locking onto props, borders, shadows, packaging, or partial subgrids.',
  },
  {
    id: 'grid-texture-frequency-search',
    name: 'Grid-As-Texture Frequency Search',
    category: 'passive',
    status: 'planned',
    runtime: 'Browser WASM or Python numeric/OpenCV gateway',
    summary: 'Estimate pitch and orientation from repeating texture with autocorrelation, Fourier peaks, or phase correlation, then fit a projective lattice.',
    promotionRisk: 'Reject if mat weave, compression, lighting bands, or paper texture look like stronger periodic signals than the 1-inch grid.',
  },
  {
    id: 'boundary-first-grid-fit',
    name: 'Boundary-First Interior Grid Fit',
    category: 'passive',
    status: 'planned',
    runtime: 'Browser TypeScript/canvas, OpenCV.js, or Python/OpenCV gateway',
    summary: 'Find mat or image-region boundaries first, then fit/interpolate interior grid lines and off-image corners.',
    promotionRisk: 'Reject if it overfits sales-photo borders, page edges, table edges, product packaging, or visible props.',
  },
  {
    id: 'user-seeded-snap-solver',
    name: 'User-Seeded Snap Solver',
    category: 'assisted',
    status: 'planned',
    runtime: 'Browser TypeScript/canvas',
    summary: 'Use one or two rough user gestures to seed a homography, then snap to the nearest coherent grid lattice.',
    promotionRisk: 'Reject if it requires precise clicking or becomes full manual fixture labeling during live play.',
  },
  {
    id: 'opencv-line-cluster',
    name: 'OpenCV Line Clustering',
    category: 'passive',
    status: 'research-only',
    runtime: 'Gateway Python/OpenCV preferred; browser OpenCV.js rejected for this benchmark pass',
    summary: 'Use mature Canny/Hough/LSD primitives and cluster orthogonal line families into grid intersections.',
    promotionRisk: 'Browser OpenCV.js froze the benchmark and produced a huge bundle; retry only through a gateway-side or worker-isolated runtime.',
  },
  {
    id: 'contour-quadrilateral-rectification',
    name: 'Contour / Quadrilateral Rectification',
    category: 'passive',
    status: 'planned',
    runtime: 'Browser TypeScript/canvas, OpenCV.js, or Python/OpenCV gateway',
    summary: 'Find a strong mat, paper, or projected-region quadrilateral and rectify it before grid fitting.',
    promotionRisk: 'Reject if the strongest quadrilateral is usually the wrong object.',
  },
  {
    id: 'aruco-charuco-assisted',
    name: 'ArUco / ChArUco Assisted Calibration',
    category: 'fiducial',
    status: 'planned',
    runtime: 'Python/OpenCV gateway first; browser only if OpenCV.js support is proven',
    summary: 'Use explicit marker IDs and corners, optionally with ChArUco corner refinement, to solve known mat/projector geometry.',
    promotionRisk: 'Reject if printed marker setup is too slow, intrusive, or brittle under table lighting.',
  },
  {
    id: 'apriltag-assisted',
    name: 'AprilTag Assisted Calibration',
    category: 'fiducial',
    status: 'planned',
    runtime: 'Native/C or Python gateway',
    summary: 'Use robotics fiducials on cards, corners, or a mat-edge strip to make grid ownership explicit.',
    promotionRisk: 'Reject if dependency and setup burden outweigh accuracy gain.',
  },
  {
    id: 'active-projector-camera-structured-light',
    name: 'Active Projector-Camera Structured Light',
    category: 'active-calibration',
    status: 'planned',
    runtime: 'Python/OpenCV gateway first',
    summary: 'Project known points, Gray-code patterns, or calibration boards and capture them to solve projector-pixel to camera-pixel mapping.',
    promotionRisk: 'Reject if it takes too many frames or still needs a separate slow step to identify physical mat coordinates.',
  },
  {
    id: 'temporal-video-lock-on',
    name: 'Temporal Video Lock-On',
    category: 'hybrid',
    status: 'planned',
    runtime: 'Browser camera stream or Python/OpenCV gateway',
    summary: 'Aggregate evidence over several stationary camera frames to reject transient hands, shadows, glare, and one-frame noise.',
    promotionRisk: 'Reject if convergence takes too long or the solution jitters between plausible grids.',
  },
];

export function runnableDetectorCandidates(options: {
  includeControls?: boolean;
} = {}): RunnableDetectorCandidate[] {
  return DETECTOR_CANDIDATES.filter((candidate): candidate is RunnableDetectorCandidate => (
    typeof candidate.run === 'function'
    && (options.includeControls === true || candidate.usesGroundTruth !== true)
  ));
}
