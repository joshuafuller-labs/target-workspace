/// <reference types="vite/client" />

declare module "*.css" {
  const _: unknown;
  export default _;
}

declare const __BUILD_ID__: string;
