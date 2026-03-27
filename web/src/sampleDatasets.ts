const GITHUB_RAW_BASE =
  "https://raw.githubusercontent.com/eresearchqut/RSstitcher/main/tests/data";

function range(start: number, end: number): number[] {
  return Array.from({ length: end - start }, (_, i) => start + i);
}

function pad(n: number, width: number): string {
  return String(n).padStart(width, "0");
}

export interface SampleDataset {
  id: string;
  name: string;
  format: string;
  sizeLabel: string;
  files: string[];
}

export const SAMPLE_DATASETS: SampleDataset[] = [
  {
    id: "bruker_gid",
    name: "Bruker GID",
    format: "Bruker (.gfrm)",
    sizeLabel: "7 MB",
    files: [
      ...range(0, 21).map(
        (i) =>
          `phi0/PEDOT_WR-RSM_SI-GID_Phi0_CoKa_Chi_optimised_HighCountRate_Kbeta-${pad(i, 3)}.gfrm`,
      ),
      ...range(0, 21).map(
        (i) =>
          `phi180/PEDOT_WR-RSM_SI-GID_Phi180_CoKa_Chi_optimised_HighCountRate_Kbeta-${pad(i, 3)}.gfrm`,
      ),
    ],
  },
  {
    id: "bruker_symmetric",
    name: "Bruker Symmetric",
    format: "Bruker (.gfrm)",
    sizeLabel: "22 MB",
    files: range(0, 100).map(
      (i) => `WR-RSM_2D_15-125-0.1-1100s_50Chi_2Phi-${pad(i, 3)}.gfrm`,
    ),
  },
  {
    id: "rigaku_gid",
    name: "Rigaku GID",
    format: "Rigaku (.img)",
    sizeLabel: "11 MB",
    files: range(1, 5).map((i) => `WRRSM-PEDOT-PET_${pad(i, 4)}.img`),
  },
  {
    id: "rigaku_symmetric",
    name: "Rigaku Symmetric",
    format: "Rigaku (.img)",
    sizeLabel: "88 MB",
    files: range(1, 11).map(
      (i) => `WRRSM-Satin-Spar_chi_optimised_${pad(i, 4)}.img`,
    ),
  },
  {
    id: "new_data",
    name: "Rigaku (New Data)",
    format: "Rigaku (.img)",
    sizeLabel: "28 MB",
    files: range(1, 6).map((i) => `image_${i}.img`),
  },
  {
    id: "cor_powder",
    name: "Corundum Powder",
    format: "Rigaku (.img)",
    sizeLabel: "71 MB",
    files: range(1, 9).map((i) => `WRRSM-Corundum_${pad(i, 4)}.img`),
  },
];

export function getSampleDatasetUrl(
  datasetId: string,
  filePath: string,
): string {
  return `${GITHUB_RAW_BASE}/${datasetId}/${filePath}`;
}
