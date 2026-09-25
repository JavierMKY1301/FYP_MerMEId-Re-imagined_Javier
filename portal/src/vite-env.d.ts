/// <reference types="vite/client" />

// Verovio ships no TypeScript declarations. declare the surface use.
declare module "verovio" {
  const anyExport: any;
  export default anyExport;
  export const toolkit: any;
  export const module: any;
}
