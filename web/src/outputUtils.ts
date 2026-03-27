export const OUTPUT_SUFFIXES: Record<string, string> = {
  pixels_tiff: "_pixels.tiff",
  grid_tiff: "_grid.tiff",
  experiment_json: "_experiment.json",
  azimuthal_csv: "_1D.csv",
  radial_csv: "_debeye_ring_profile.csv",
};

/**
 * Expand Python-style `{variable}` templates using experiment summary values.
 * Unknown variables are left as-is.
 */
export function expandTemplate(
  template: string,
  vars: Record<string, unknown>,
): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) => {
    const val = vars[key];
    return val !== undefined ? String(val) : match;
  });
}
