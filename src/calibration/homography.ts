import type { Point } from './types';

export type Homography = [
  number, number, number,
  number, number, number,
  number, number, number,
];

const EPSILON = 1e-10;

export function applyHomography(matrix: Homography, point: Point): Point {
  const [h11, h12, h13, h21, h22, h23, h31, h32, h33] = matrix;
  const denominator = h31 * point.x + h32 * point.y + h33;
  if (Math.abs(denominator) < EPSILON) {
    throw new Error('Point maps to infinity under homography');
  }

  return {
    x: (h11 * point.x + h12 * point.y + h13) / denominator,
    y: (h21 * point.x + h22 * point.y + h23) / denominator,
  };
}

export function solveHomography(from: Point[], to: Point[]): Homography {
  if (from.length !== 4 || to.length !== 4) {
    throw new Error('Homography solve requires exactly four point pairs');
  }

  const a: number[][] = [];
  const b: number[] = [];

  for (let i = 0; i < 4; i += 1) {
    const source = from[i];
    const target = to[i];

    a.push([
      source.x,
      source.y,
      1,
      0,
      0,
      0,
      -source.x * target.x,
      -source.y * target.x,
    ]);
    b.push(target.x);

    a.push([
      0,
      0,
      0,
      source.x,
      source.y,
      1,
      -source.x * target.y,
      -source.y * target.y,
    ]);
    b.push(target.y);
  }

  const solution = solveLinearSystem(a, b);
  return [
    solution[0], solution[1], solution[2],
    solution[3], solution[4], solution[5],
    solution[6], solution[7], 1,
  ];
}

function solveLinearSystem(a: number[][], b: number[]): number[] {
  const n = b.length;
  const matrix = a.map((row, index) => [...row, b[index]]);

  for (let column = 0; column < n; column += 1) {
    let pivotRow = column;
    for (let row = column + 1; row < n; row += 1) {
      if (Math.abs(matrix[row][column]) > Math.abs(matrix[pivotRow][column])) {
        pivotRow = row;
      }
    }

    if (Math.abs(matrix[pivotRow][column]) < EPSILON) {
      throw new Error('Cannot solve homography from degenerate point pairs');
    }

    if (pivotRow !== column) {
      [matrix[column], matrix[pivotRow]] = [matrix[pivotRow], matrix[column]];
    }

    const pivot = matrix[column][column];
    for (let cell = column; cell <= n; cell += 1) {
      matrix[column][cell] /= pivot;
    }

    for (let row = 0; row < n; row += 1) {
      if (row === column) continue;
      const factor = matrix[row][column];
      for (let cell = column; cell <= n; cell += 1) {
        matrix[row][cell] -= factor * matrix[column][cell];
      }
    }
  }

  return matrix.map((row) => row[n]);
}
