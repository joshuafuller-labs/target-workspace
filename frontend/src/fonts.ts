// Self-hosted fonts for theme-driven typography. Imported once at app boot
// so every palette can switch via `var(--tw-font-display/body)` without a
// network round-trip. Offline-friendly per the air-gap consideration.

// Public Sans — US government typeface (USDS / login.gov). Used by `federal`
// and `ics` themes.
import "@fontsource/public-sans/400.css";
import "@fontsource/public-sans/500.css";
import "@fontsource/public-sans/600.css";
import "@fontsource/public-sans/700.css";

// Geist Mono — refined neutral mono. Used by `neutral` theme.
import "@fontsource/geist-mono/400.css";
import "@fontsource/geist-mono/500.css";
import "@fontsource/geist-mono/600.css";

// JetBrains Mono — tight technical mono. Used by `tactical` theme.
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "@fontsource/jetbrains-mono/700.css";

// Barlow Condensed — narrow utility face used sparingly for SAR headers.
import "@fontsource/barlow-condensed/500.css";
import "@fontsource/barlow-condensed/600.css";
import "@fontsource/barlow-condensed/700.css";

// IBM Plex Serif — kept available for future editorial use; not currently
// applied (govtech federal direction uses Public Sans instead).
import "@fontsource/ibm-plex-serif/400.css";
import "@fontsource/ibm-plex-serif/600.css";
