import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(cleanup);

// jsdom implements no layout, so it ships no `scrollIntoView`. Agent mode calls
// it to follow a streaming answer; without this a page test fails on scrolling
// rather than on anything it meant to check.
Element.prototype.scrollIntoView = () => {};
