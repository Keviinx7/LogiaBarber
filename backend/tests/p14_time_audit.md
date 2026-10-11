# Auditoría temporal P1.4

Búsqueda literal con `rg` en archivos del proyecto, incluidos tests y reportes históricos.
Cada fila identifica una coincidencia por archivo, línea y columna. Se conservaron
las fechas y horas legítimas de las pruebas y de la evidencia histórica.

Se excluyeron secretos `.env*`, dependencias instaladas, binarios/cachés, metadatos
de compilación, `dist` (artefacto generado) y este propio informe.
Las reglas productivas se expresan como `time(...)` en `business_rules.py`;
el seed no tiene años ni bloques diarios. La portada consume el contrato público.

| Archivo | Línea | Columna | Coincidencia | Clasificación |
|---|---:|---:|---|---|
| `backend/tests/test_p12_business_config.py` | 32 | 25 | `14:00` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `backend/tests/test_p12_business_config.py` | 32 | 47 | `15:00` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `backend/tests/P1.4.md` | 4 | 59 | `14:00` | Documentación de reglas oficiales o evidencia; no genera registros fechados. |
| `backend/tests/P1.4.md` | 4 | 66 | `15:00` | Documentación de reglas oficiales o evidencia; no genera registros fechados. |
| `backend/tests/p0_validation_results.historical.json` | 6 | 21 | `2026` | Evidencia histórica de ejecuciones; fechas/horas observadas, no reglas actuales. |
| `backend/tests/p0_preflight_results.json` | 5 | 21 | `2026` | Evidencia histórica de ejecuciones; fechas/horas observadas, no reglas actuales. |
| `backend/tests/test_p14_business_rules.py` | 27 | 29 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `backend/tests/test_p14_business_rules.py` | 119 | 39 | `2027` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `backend/tests/test_p14_business_rules.py` | 119 | 57 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `backend/tests/test_p14_business_rules.py` | 119 | 77 | `2027` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.4.test.tsx` | 9 | 17 | `14:00` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.4.test.tsx` | 9 | 37 | `15:00` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.4.test.tsx` | 34 | 34 | `14:00` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.4.test.tsx` | 34 | 42 | `15:00` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.4.test.tsx` | 37 | 52 | `09:00` | Aserción negativa: exige ausencia de horarios antiguos en la portada. |
| `frontend/src/tests/p1.4.test.tsx` | 37 | 58 | `18:00` | Aserción negativa: exige ausencia de horarios antiguos en la portada. |
| `frontend/src/tests/p1.4.test.tsx` | 37 | 64 | `19:00` | Aserción negativa: exige ausencia de horarios antiguos en la portada. |
| `frontend/src/tests/p1.4.test.tsx` | 55 | 42 | `14:00` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.4.test.tsx` | 65 | 42 | `14:00` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `backend/tests/p0_validation_results.json` | 8 | 21 | `2026` | Evidencia histórica de ejecuciones; fechas/horas observadas, no reglas actuales. |
| `backend/tests/test_p13_availability.py` | 14 | 12 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `backend/tests/test_p13_availability.py` | 75 | 18 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `backend/tests/test_p13_availability.py` | 99 | 43 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `backend/tests/test_p13_availability.py` | 100 | 72 | `19:00` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.3.test.tsx` | 7 | 180 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.3.test.tsx` | 7 | 216 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.3.test.tsx` | 8 | 16 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.3.test.tsx` | 9 | 97 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.3.test.tsx` | 19 | 30 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.3.test.tsx` | 19 | 41 | `14:00` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.3.test.tsx` | 19 | 57 | `09:00` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.3.test.tsx` | 62 | 83 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.3.test.tsx` | 68 | 35 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.3.test.tsx` | 95 | 107 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.3.test.tsx` | 103 | 57 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.3.test.tsx` | 103 | 72 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.3.test.tsx` | 119 | 38 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.3.test.tsx` | 159 | 85 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.3.test.tsx` | 164 | 13 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.3.test.tsx` | 164 | 41 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.3.test.tsx` | 175 | 38 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.3.test.tsx` | 181 | 69 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 10 | 161 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 10 | 197 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 11 | 16 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 18 | 30 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 19 | 42 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 29 | 78 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 29 | 111 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 56 | 16 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 56 | 40 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 57 | 7 | `19:00` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 57 | 16 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 57 | 40 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 58 | 16 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 58 | 40 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 59 | 16 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 59 | 40 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 69 | 33 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 71 | 26 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 75 | 32 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 79 | 35 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 84 | 20 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 84 | 44 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 84 | 73 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 100 | 43 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 101 | 43 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 118 | 32 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 120 | 35 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 124 | 36 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 129 | 35 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 130 | 37 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 135 | 55 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 136 | 32 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 138 | 35 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 139 | 37 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 145 | 32 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.2.test.tsx` | 148 | 37 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.1.test.tsx` | 12 | 143 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.1.test.tsx` | 12 | 179 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.1.test.tsx` | 13 | 124 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.1.test.tsx` | 13 | 160 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.1.test.tsx` | 14 | 143 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.1.test.tsx` | 14 | 179 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.1.test.tsx` | 24 | 155 | `14:00` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.1.test.tsx` | 24 | 175 | `15:00` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.1.test.tsx` | 27 | 83 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.1.test.tsx` | 27 | 121 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.1.test.tsx` | 28 | 165 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.1.test.tsx` | 192 | 43 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.1.test.tsx` | 193 | 42 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
| `frontend/src/tests/p1.1.test.tsx` | 194 | 110 | `2026` | Fixture o aserción de prueba; reloj, límites temporales, contrato público o regresión. No configura producción. |
