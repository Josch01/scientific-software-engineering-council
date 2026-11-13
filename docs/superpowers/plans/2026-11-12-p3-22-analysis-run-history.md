# P3.22 — Historial de corridas SIR: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Implement tasks in order with focused tests and small commits.

**Goal:** Abrir resultados de corridas P3.21 desde el Centro de Control, etiquetados inequívocamente como históricos.

**Architecture:** Un módulo Python puro enumera y valida registros acotados; al abrir una fila, el loader seguro vuelve a validar el workspace y el SHA-256. Qt presenta el historial y actualiza resultados solo tras validación completa.

**Tech Stack:** Python 3.14, PySide6, unittest; sin dependencias nuevas.

**Spec:** docs/superpowers/specs/2026-11-12-p3-22-analysis-run-history-design.md

## Global Constraints

- Aceptar el run_id hexadecimal de 32 caracteres que genera P3.21; no ejecutar Python ni otro código del proyecto.
- No recalcular ni cambiar algoritmos científicos.
- Leer como máximo las 100 bitácoras recientes y 65 536 bytes por bitácora.
- FAILED, registro inválido, recurso ausente o digest discordante nunca carga vistas.
- La carga histórica no genera nueva bitácora ni marca una ejecución actual.
- Mantener NOT_RUN, NOT_CALCULATED y NOT_ASSESSED según corresponda.

## Review Focus

- Enlaces y reparse points no deben permitir lectura fuera de la raíz del proyecto.
- Una bitácora alterada después del listado debe fallar al abrirse.
- El rechazo/fallo de carga conserva intactas las vistas actualmente abiertas.
- Resultados históricos deben llevar etiqueta visible de fecha e ID.

## Files

- scripts/scientific_run_history.py: list_sir_analysis_runs(root) y read_sir_analysis_run(root, run_id), lectura acotada y selección de solo corridas exitosas.
- scripts/scientific_control_center_qt.py: diálogo/listado, selección y etiqueta histórica.
- scripts/scientific_workspace_qt.py: comparación de digest esperada antes de cambiar vistas.
- tests/test_scientific_run_history.py: registros válidos, fallidos, dañados, enlace y digest discordante.
- tests/test_scientific_control_center_qt.py: apertura histórica, estado visible y fallo sin reemplazo de vistas.
- docs/roadmap/FEATURE_MATRIX.md y docs/test-reports/: evidencia compacta.

## Tasks

- [x] Escribir pruebas unitarias rojas para enumerar registros, rechazar logs inseguros/dañados y abrir solo un resultado cuyo manifiesto conserve el digest registrado.
- [x] Implementar el lector con límites locales documentados y reutilizar load_scientific_workspace; ejecutar solo el módulo de pruebas nuevo y guardar salida en log con resumen corto.
- [x] Escribir prueba Qt roja para abrir una corrida anterior; implementar lista/acción, confirmar que una corrida FAILED o corrupta no se abre y que el resultado queda marcado como histórico.
- [x] Ejecutar módulos de historial, Qt y loader; guardar log completo fuera del contexto, escribir reporte breve PASS/NOT_RUN, actualizar matriz y ejecutar compileall + git diff --check.
- [x] Revisar el diff, solicitar una revisión independiente focalizada en lectura segura y estados históricos, corregir solo defectos reproducibles, y crear un PR borrador apilado sobre P3.21.
