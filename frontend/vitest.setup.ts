import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Testing Library only cleans up automatically when vitest globals are on; they aren't.
afterEach(() => cleanup());

// jsdom doesn't implement scrolling; browsers do. A no-op keeps components that
// scroll (claim cards, the review form) testable.
if (typeof Element !== "undefined" && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function scrollIntoView() {};
}
