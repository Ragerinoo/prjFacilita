import "vitest";

// Tipos do matcher `toHaveNoViolations` do jest-axe para o Vitest.
declare module "vitest" {
  interface Assertion {
    toHaveNoViolations(): void;
  }
  interface AsymmetricMatchersContaining {
    toHaveNoViolations(): void;
  }
}
