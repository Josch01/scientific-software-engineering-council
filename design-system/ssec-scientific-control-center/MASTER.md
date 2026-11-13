# SSEC Scientific Control Center — Design System

Desktop scientific workspace built with PySide6 and local Qt WebEngine charts.
The Python scientific engine and versioned workspace contracts remain separate
from this presentation layer.

## Visual direction

- Charcoal surfaces: background `#202027`, sidebar `#24232b`, cards `#292830`,
  raised controls `#32313b`.
- Soft violet is the primary action and focus color: `#aa8bf2`; use `#5b487d`
  for selected navigation and `#bea5ff` for hover emphasis.
- Primary text `#f2eef7`; secondary text `#c2bdcc`. Keep text readable against
  every surface; use color and a written status together.
- Scientific series use violet, teal, coral, sky, amber, and pink. Keep series
  names and units visible; never encode scientific meaning by color alone.
- Use system UI fonts, 8 px spacing increments, 8–10 px card corners, and
  tabular numerals in result tables.

## Interaction

- Desktop navigation stays visible while project content changes in place.
- Human confirmation remains required for model/provider invocations and
  scientific execution. Visual styling must not imply approval or validity.
- Navigation and chart line entry use a short opacity transition only. Set
  `SSEC_REDUCED_MOTION=1` to disable native Qt transitions; local chart CSS
  follows `prefers-reduced-motion`.
- Charts remain self-contained and local. No CDN, remote fonts, or external
  services are loaded.
- Keep status, provenance, units, errors, and `NOT_ASSESSED` labels explicit.

## Scope

This system restyles the existing control center, workspace panels, and
scientific charts. It does not change model equations, solvers, data selection,
approval rules, or scientific conclusions. See `pages/control-center.md` for
the implementation-specific layout and state guidance.
