# P2.5 — Modelo SIR armónico de la tesis

## Objetivo

Representar el SIR de la tesis y su observación de conteos semanales como un contrato versionado, ejecutable con el RK4 fijo existente y sin evaluar expresiones arbitrarias.

## Contrato científico

Fuente primaria: `tesis.pdf`, cap. 3, §§3.1–3.3, ecuaciones (3.1)–(3.8), pp. impresas 9–11; identificación y SHA-256 constan en el [ingreso de fuentes](../../test-reports/sir-thesis-validation-target-2026-11-13.md).

- Estados en personas: S, I, R >= 0; N = 129,960,600 fijo y S + I + R = N.
- Flujo de infección: `lambda(t)=beta(t)*S*I/N`; `dS/dt=-lambda`, `dI/dt=lambda-gamma*I`, `dR/dt=gamma*I`.
- Transmisión: `beta(t)=exp(d0 + sum[k=1..K](c_k*cos(omega_k*t)+s_k*sin(omega_k*t)))`; `K` es 1, 2 o 3. `d0,c_k,s_k ∈ [-2,2]`, `omega_k ∈ [0.05,2.20] rad/week`, `gamma ∈ [0.05,0.70] week^-1`.
- Iniciales al inicio de integración: `I0=10^ell_I person`, `S0=N*f_S`, `R0=N-S0-I0>=0`; `ell_I ∈ [0,log10(N/person)]`, `f_S ∈ [0,1]`.
- Observación semanal: `mu_j=q*integral[t_(j-1)-delta/7, t_j-delta/7](beta(u)*S(u)*I(u)/N du)`. `q ∈ [sum(Y)/N,1]` es constante. `delta` se declara en días, con escenario central 4.3 y alternativas 0, 3.5 y 6.5; no se interpreta como distribución de incubación.
- `t_j=j` semanas para `j=0..56`. El acumulador de infecciones se integra con la misma RHS/RK4; no se usa interpolación ni un integrador nuevo.

## Entrada de observaciones

El adaptador de `reconstruccion_DGE_56_semanas.json` consume exclusivamente `week_by_week_comparison[].DGE_monday_sunday_candidate`, preserva el SHA-256 del JSON y el identificador de serie, y valida 56 etiquetas ordenadas y conteos enteros no negativos. No usa `local`, `DGE_sunday_saturday`, diferencias ni resúmenes como observaciones.

## Límites

No incluye optimización/calibración, estimaciones de parámetros ni conclusiones de identificabilidad; esta entrega permite evaluar trayectorias y medias semanales para parámetros proporcionados explícitamente. La interfaz Qt y la ejecución con los datos del usuario quedan para incrementos posteriores. Ninguna prueba sintética se reportará como ejecución o validación científica del caso real.

## Verificación

Pruebas focalizadas: valores de beta y RHS contra cálculos directos; cotas y estados inviables; conservación poblacional; desplazamiento temporal y acumulación semanal; convergencia RK4; importación estricta del esquema usando fixtures sintéticos. Caso SIR/datos del usuario: `NOT_RUN` hasta terminar y recibir aprobación humana.
