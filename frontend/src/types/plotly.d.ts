/**
 * `plotly.js-dist-min` ships no type declarations. We use the distribution
 * bundle directly (rather than `react-plotly.js`, which has unresolved React 19
 * peer-dependency conflicts) and drive it through the imperative `react()` API,
 * so a narrow structural declaration is enough.
 */
declare module "plotly.js-dist-min" {
  export type PlotlyData = Record<string, unknown>;
  export type PlotlyLayout = Record<string, unknown>;
  export type PlotlyConfig = Record<string, unknown>;

  export function react(
    root: HTMLElement,
    data: PlotlyData[],
    layout?: PlotlyLayout,
    config?: PlotlyConfig,
  ): Promise<void>;

  export function purge(root: HTMLElement): void;
  export function Plots(): void;

  const Plotly: {
    react: typeof react;
    purge: typeof purge;
  };

  export default Plotly;
}
