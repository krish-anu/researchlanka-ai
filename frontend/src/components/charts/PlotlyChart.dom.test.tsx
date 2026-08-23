/**
 * @vitest-environment jsdom
 */

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const react = vi.fn(() => Promise.resolve());
const purge = vi.fn();

// Stands in for the real 4.7MB bundle, which neither loads nor draws in jsdom.
vi.mock("plotly.js-dist-min", () => ({ default: { react, purge } }));

import { PlotlyChart } from "@/components/charts/PlotlyChart";

/** Collects observed elements so a test can decide when they come into view. */
class FakeObserver {
  static instances: FakeObserver[] = [];
  elements: Element[] = [];

  constructor(private callback: IntersectionObserverCallback) {
    FakeObserver.instances.push(this);
  }

  observe(element: Element) {
    this.elements.push(element);
  }
  disconnect() {
    this.elements = [];
  }
  unobserve() {}
  takeRecords() {
    return [];
  }

  enter() {
    this.callback(
      this.elements.map((target) => ({ target, isIntersecting: true })) as
        IntersectionObserverEntry[],
      this as unknown as IntersectionObserver,
    );
  }
}

const build = () => ({ data: [{ type: "bar" }], layout: {} });

beforeEach(() => {
  FakeObserver.instances = [];
  react.mockClear();
  purge.mockClear();
  vi.stubGlobal("IntersectionObserver", FakeObserver);
  vi.stubGlobal("matchMedia", () => ({
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("PlotlyChart", () => {
  it("does not draw until the chart is near the viewport", async () => {
    render(<PlotlyChart build={build} ariaLabel="Test chart" />);

    // Mounted, observed, and deliberately idle.
    expect(screen.getByRole("img", { name: "Test chart" })).toBeTruthy();
    expect(FakeObserver.instances).toHaveLength(1);
    await Promise.resolve();
    expect(react).not.toHaveBeenCalled();

    await act(async () => FakeObserver.instances[0].enter());

    await waitFor(() => expect(react).toHaveBeenCalledTimes(1));
  });

  it("draws immediately where IntersectionObserver is unavailable", async () => {
    vi.stubGlobal("IntersectionObserver", undefined);

    render(<PlotlyChart build={build} ariaLabel="Fallback chart" />);

    await waitFor(() => expect(react).toHaveBeenCalledTimes(1));
  });

  it("purges the node on unmount, not between redraws", async () => {
    const { rerender, unmount } = render(
      <PlotlyChart build={build} ariaLabel="Test chart" />,
    );
    await act(async () => FakeObserver.instances[0].enter());
    await waitFor(() => expect(react).toHaveBeenCalledTimes(1));

    // A new `build` is new data: redrawn in place, never torn down.
    rerender(<PlotlyChart build={() => build()} ariaLabel="Test chart" />);
    await waitFor(() => expect(react).toHaveBeenCalledTimes(2));
    expect(purge).not.toHaveBeenCalled();

    unmount();
    await waitFor(() => expect(purge).toHaveBeenCalledTimes(1));
  });
});
