/**
 * The §57 palette, as React Native values.
 *
 * Duplicated from the web's tokens rather than shared, because RN has no CSS
 * custom properties. The hexes must stay in step with apps/web/app/globals.css
 * -- the confidence bands in particular were chosen to pass a colour-vision
 * check and must not be re-picked here by eye.
 */
export const colors = {
  navy: "#1E3A5F",
  navyDark: "#14273F",
  navyLight: "#D5DFEA",
  burnt: "#D2691E",
  warm: "#F4A460",
  cream: "#FDF6E3",
  offwhite: "#F7F5EF",
  ink: "#1A1A1A",
  sand50: "#FAF8F3",
  sand100: "#F0ECE1",
  sand200: "#E2DCCD",
  sand300: "#CDC5B2",
  sand500: "#8B8272",
  sand700: "#4F4A40",
  white: "#FFFFFF",
  high: "#14663D",
  highBg: "#E6F1EB",
  medium: "#C4841A",
  mediumBg: "#FBF1DD",
  low: "#A61D18",
  lowBg: "#FAEAE8",
} as const;

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 } as const;

export const radius = { chip: 3, card: 6 } as const;
