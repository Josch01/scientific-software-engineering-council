# Control Center Page Override

Applies to `scripts/scientific_control_center_qt.py`, the embedded scientific
workspace, and chart renderers.

## Layout

- Keep the persistent left rail for Projects, Agents, Experiments, Audits, Code,
  and Results; give the active route a violet edge and filled selection.
- Use a compact top bar for SSEC identity and active project. Page title sits
  above the content stack with consistent left alignment.
- Render project details, analysis controls, status, tables, and plots as
  charcoal cards with visible borders. Retain the existing in-place workspace
  routing and empty states.
- Use one clear primary action per card. Human confirmation text must remain
  visible before any scientific run or local model invocation.

## Scientific chart style

- Put the chart title, axis labels, units, readable endpoint ticks, series
  legend, and provenance in or beside the plot.
- Palette: `#b89bff` violet, `#61d6c1` teal, `#ff9b81` coral, `#79c7ff` sky,
  `#f4c96d` amber, and `#ed94c6` pink. Use line style and labels in addition
  to hue where series overlap.
- Use a low-contrast grid, high-contrast axis labels, tabular tooltip values,
  and keyboard-operable legend toggles.
- Use the built-in SVG renderer in Qt WebEngine when available. It is local,
  has remote access disabled, and retains the existing native Qt fallback.
- Animate only view entry and line appearance; honor reduced motion.

## Scientific status

Theme and motion express interface state only. They must not imply that a
simulation, fit, audit, uncertainty analysis, or scientific validation passed.
Display source digests, units, metrics, and existing status values from the
versioned contracts. Preserve `NOT_ASSESSED` and `NOT_RUN` as written.
