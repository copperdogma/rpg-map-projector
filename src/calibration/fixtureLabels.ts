import type { Point } from './types';
import type { SampleImage } from './sampleImages';

export interface GridFixtureIdentity {
  sourceId: string;
  sourceName: string;
  sourceUrl: string;
  note: string;
}

export interface GridFixtureLabel extends GridFixtureIdentity {
  imageWidth: number;
  imageHeight: number;
  corners: [Point, Point, Point, Point];
  columns: number;
  rows: number;
  benchmark: boolean;
  labeledAt: string;
}

export interface GridFixtureLabelFile {
  version: 1;
  updatedAt: string | null;
  labels: GridFixtureLabel[];
}

export const EMPTY_LABEL_FILE: GridFixtureLabelFile = {
  version: 1,
  updatedAt: null,
  labels: [],
};

export function sampleToFixtureIdentity(sample: SampleImage): GridFixtureIdentity {
  const localPrefix = '/input/map-pix/';
  const sourceId = sample.url.startsWith(localPrefix)
    ? decodeURIComponent(sample.url.slice(localPrefix.length))
    : slugify(sample.label);

  return {
    sourceId,
    sourceName: sample.label,
    sourceUrl: sample.url,
    note: sample.note,
  };
}

export function findFixtureLabel(
  file: GridFixtureLabelFile,
  sourceId: string,
): GridFixtureLabel | null {
  return file.labels.find((label) => label.sourceId === sourceId) ?? null;
}

export function upsertFixtureLabel(
  file: GridFixtureLabelFile,
  label: GridFixtureLabel,
): GridFixtureLabelFile {
  const labels = file.labels.filter((item) => item.sourceId !== label.sourceId);
  labels.push(label);
  labels.sort((a, b) => a.sourceName.localeCompare(b.sourceName, undefined, { numeric: true }));
  return {
    version: 1,
    updatedAt: new Date().toISOString(),
    labels,
  };
}

function slugify(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '');
}
