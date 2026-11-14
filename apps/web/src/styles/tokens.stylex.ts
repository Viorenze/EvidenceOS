import * as stylex from "@stylexjs/stylex";

export const colors = stylex.defineVars({
  primary: "#2563eb",
  primaryHover: "#1d4ed8",
  primaryLight: "#dbeafe",
  primaryText: "#1d4ed8",

  bgPage: "#f8fafc",
  bgCard: "#ffffff",
  bgSubtle: "#f1f5f9",
  bgMuted: "#e2e8f0",

  textMain: "#0f172a",
  textMuted: "#64748b",
  textLight: "#94a3b8",

  borderSubtle: "#e2e8f0",
  borderLight: "#cbd5e1",

  successBg: "#ecfdf5",
  successText: "#065f46",
  successBorder: "#a7f3d0",

  errorBg: "#fff1f2",
  errorText: "#9f1239",
  errorBorder: "#fecdd3",

  warningBg: "#fffbeb",
  warningText: "#92400e",
  warningBorder: "#fde68a",
});

export const spacing = stylex.defineVars({
  xs: "4px",
  sm: "8px",
  md: "16px",
  lg: "24px",
  xl: "32px",
  xxl: "48px",
});

export const radii = stylex.defineVars({
  sm: "4px",
  md: "8px",
  lg: "12px",
  xl: "16px",
  full: "9999px",
});
