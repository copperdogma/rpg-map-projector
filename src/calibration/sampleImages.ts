export interface SampleImage {
  label: string;
  url: string;
  note: string;
}

const LOCAL_FIXTURE_FILES = [
  '06252a1d-3270-48f0-88eb-b285c6018dd1.0b8b61361649f82647e4090193ac482f.avif',
  '81LnW7KU+xL._AC_SL1500_.jpg',
  '92736938-f725-453e-b67b-200931750869.5813fb5be2a47779690ef1feea123ce1.avif',
  'B087YZMB8V_-9.16.25_with_clips_1200x.webp',
  'Copy_of_6.02_-_1X1_-_Million_Dollar_Sellers_-_AAL_-_319730-new_1200x.webp',
  'il_1588xN.1728397306_gc90.webp',
  'il_1588xN.1762274533_i5t8.webp',
  'il_1588xN.1775855641_o5cj.webp',
  'il_1588xN.6951939360_g55b.webp',
  'il_1588xN.6951939366_jrtv.webp',
  's-l1600.webp',
];

export const sampleImages: SampleImage[] = [
  {
    label: 'Generated test mat',
    url: generatedTestMatUrl(),
    note: 'Synthetic in-app control image',
  },
  ...LOCAL_FIXTURE_FILES.map((filename, index) => ({
    label: `Local mat photo ${index + 1}`,
    url: `/input/map-pix/${encodeURI(filename)}`,
    note: filename,
  })),
];

function generatedTestMatUrl(): string {
  const gridLines = Array.from({ length: 13 }, (_, index) => {
    const x = 120 + index * 70;
    return `<line x1="${x}" y1="120" x2="${x}" y2="680" />`;
  }).join('');
  const rowLines = Array.from({ length: 9 }, (_, index) => {
    const y = 120 + index * 70;
    return `<line x1="120" y1="${y}" x2="960" y2="${y}" />`;
  }).join('');
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="1080" height="800" viewBox="0 0 1080 800">
      <rect width="1080" height="800" fill="#f3efe5"/>
      <rect x="120" y="120" width="840" height="560" fill="#f8f4ea" stroke="#6a6659" stroke-width="4"/>
      <g stroke="#8f9a8a" stroke-width="2">
        ${gridLines}
        ${rowLines}
      </g>
      <path d="M290 300h260v140h-260zM610 460h180v120h-180z" fill="#6b604c" opacity="0.12"/>
    </svg>
  `.trim();
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}
