import './styles.css';
import { createStateChannel, readState } from './calibration/state';
import { renderCalibrationCanvas } from './calibration/render';
import type { CalibrationState } from './calibration/types';

let state: CalibrationState = readState();

const root = document.querySelector<HTMLDivElement>('#projector-root');
if (!root) throw new Error('Missing projector root');

root.innerHTML = `
  <main class="projector-shell">
    <canvas id="projector-canvas" aria-label="Projector calibration pattern"></canvas>
    <section class="projector-hud" aria-label="Projector status">
      <strong>Projector View</strong>
      <span id="projector-scale">5 ft source squares</span>
      <button class="button compact" id="fullscreen" type="button">Fullscreen</button>
    </section>
  </main>
`;

const canvas = document.querySelector<HTMLCanvasElement>('#projector-canvas')!;
if (!canvas) throw new Error('Missing projector canvas');

createStateChannel((nextState) => {
  state = nextState;
  render();
});

document.querySelector('#fullscreen')?.addEventListener('click', () => {
  void document.documentElement.requestFullscreen?.();
});

window.addEventListener('resize', render);
render();

function render(): void {
  const scale = document.querySelector<HTMLSpanElement>('#projector-scale');
  if (scale) scale.textContent = `${state.sourceSquareFeet} ft source squares`;

  renderCalibrationCanvas(canvas, state, {
    background: 'projector',
    showLabels: true,
  });
}
