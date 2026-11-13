# Objetivo SIR real — ingreso de fuentes

- Ingreso de fuentes: **PASS**. Se inspeccionaron únicamente el modelo de la tesis y el JSON indicado; no se ejecutó simulación ni ajuste.
- Modelo: `tesis.pdf`, cap. 3, §§3.1–3.3, pp. impresas 9–11; SHA-256 `aa8ecad90a2d52942081b40fd78849d2dc4b280bbcb4b5bd828e4812dfec5486`.
- EDO: N=129960600; lambda=beta(t) S I/N; dS/dt=-lambda, dI/dt=lambda-gamma I, dR/dt=gamma I. beta(t)=exp(d0 + sum[k=1..K](c_k cos(omega_k t)+s_k sin(omega_k t))); K=1,2,3. t se mide en semanas desde el primer límite; beta y gamma en semana^-1, omega en radianes/semana.
- Cotas: d0,c_k,s_k en [-2,2]; omega_k en [0.05,2.20]; gamma en [0.05,0.70]; ell_I en [0,log10(N/persona)]; f_S en [0,1]; q en [sum(Y)/N,1].
- Iniciales/observación: I0=10^ell_I, S0=N f_S, R0=N-S0-I0>=0; mu_j=q integral[t_(j-1)-delta/7, t_j-delta/7] beta(u)S(u)I(u)/N du. q es constante; delta central 4.3 días y escenarios 0, 3.5 y 6.5 días.
- Datos: `reconstruccion_DGE_56_semanas.json`, SHA-256 `c010ea2ecd7286fde9684a485d135d06d30440c516d61e3fb162b29fb5072a94`.
- Serie elegida: `week_by_week_comparison[].DGE_monday_sunday_candidate`; 56 semanas, 2021-11-01 a 2022-11-27, sin faltantes; suma 3,293,014, igual al total descrito en la tesis. SHA-256 canónico UTF-8 de líneas `semana,valor\n`: `9b4e8b9c08d2efa27acfe98fb54f08267b7a84d8bef2477e51ecefb81cf3ddf0`.
- No usar como entrada las series `local` o `DGE_sunday_saturday`, diferencias ni resúmenes comparativos. La serie seleccionada es la agrupación candidata lunes-domingo del JSON, no la semana oficial DGE domingo-sábado.
- Importación de solo lectura en el Centro de Control Qt: **PASS** (Windows, 2026-11-13). `ThesisSIRPage.load_data_file` dejó `READY`, 56 observaciones, suma 3,293,014 y SHA-256 de origen coincidente; las etiquetas del parser son `2021-SE44`–`2022-SE47`. `result_payload=None`, ejecución habilitada para confirmación explícita y auditoría deshabilitada hasta producir resultados. No se inició solver ni ajuste.
- Simulación/ajuste con los datos reales y compatibilidad end-to-end de modelo/observaciones: **NOT_RUN** hasta terminar y aprobar el sistema. Validez numérica/científica e identificabilidad: **NOT_ASSESSED**. No se reutilizarán estimaciones ni resultados de ajuste publicados en la tesis.
