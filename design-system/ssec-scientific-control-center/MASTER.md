# SSEC Scientific Control Center — Design System

Desktop scientific workspace built with PySide6 and local Qt WebEngine charts.
The Python scientific engine and versioned workspace contracts remain separate
from this presentation layer.

## Visual direction

- Charcoal surfaces: background `#27262e`, sidebar `#2d2b35`, cards `#34323d`,
  raised controls `#3d3b47`, hover surface `#484550`, and border `#585561`.
- Soft violet is the primary action and focus color: `#b99aff`; use `#69558f`
  for selected navigation and `#d0baff` for hover emphasis.
- Primary text `#f5f2fa`; secondary text `#cdc8d5`. Keep text readable against
  every surface; use color and a written status together.
- Scientific series use `#c6a7ff` violet, `#66dec6` teal, `#ffa48e` coral,
  `#7dd3fc` sky, `#ffd166` amber, and `#f29bcb` pink. Keep series
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
