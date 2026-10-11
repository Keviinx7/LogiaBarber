# Instrucciones de repositorio — Logia Barber

## Identidad

- Empresa visible: **Logia Barber**.
- Sistema: **Sistema de Gestión para Logia Barber**.
- Repositorio/carpeta: `LogiaBarber`.
- Ruta: `/home/kevin7/Documentos/LogiaBarber`.
- Base principal: `logia_barber`.
- Única base de pruebas PostgreSQL: `logia_barber_p0_test`.
- Rol PostgreSQL: `logia_barber_app`.

## Fuente de verdad y alcance

- Para requisitos, el ERS, el Manual de Procesos y los Requerimientos oficiales
  tienen prioridad sobre README si hay contradicciones. Localizarlos antes de
  atribuirles requisitos; si no están disponibles, declarar esa limitación,
  sin inventar contenido o rutas.
- Fuentes oficiales localizadas, según la revisión aprobada:
  - `ERS_Logia_Barber_ISO_29148_Revisada_Ambiguedades.docx`.
  - `Software/Requerimientos_Logia_Barber.docx`.
  Estos identificadores no suponen una ruta absoluta verificada ni que los
  documentos estén incluidos en este repositorio. El Manual de Procesos no
  fue localizado en esa revisión; no atribuirle contenido no verificado.
- No inventar requisitos no documentados. Informar contradicciones que impidan
  decidir y pedir la aclaración necesaria, manteniendo el alcance autorizado.
- Las instrucciones explícitas del usuario delimitan la tarea actual. Una
  delegación no amplía ese alcance ni autoriza acciones sobre bases de datos.
- Antes de editar, revisar las instrucciones aplicables `AGENTS.md` y
  `AGENTS.override.md`; integrar instrucciones existentes sin descartarlas.

## Estado protegido

- P0: **APROBADO**.
- Infraestructura P0 con `--reuse-existing`: **APROBADA**.
- P1.1: **APROBADO**.
- P1.2: **APROBADO**.
- P1.3: **APROBADO**.
- P1.4: **APROBADO**.
- P1.5: **APROBADO**.
- P1.6: **APROBADO**.
- P1 COMPLETO: **APROBADO**.
- Última evidencia real aprobada, registrada como antecedente y no como una
  ejecución nueva de esta sincronización documental:
  - PostgreSQL preflight **PASS**.
  - **38/38 P0 PostgreSQL**.
  - **237/237 suite backend**.
  - Concurrencia mismo barbero: **201+409**.
  - Concurrencia barberos distintos: **201+201**.
- P2.1: **CONTRATO APROBADO**; fase cerrada con esta sincronización documental.
  La aprobación del contrato no implica que esté implementado.
- P2.2: **NO INICIADO**.
- **No avanzar a P2.2** ni a otra fase sin autorización explícita del usuario.

Preservar las siguientes garantías de P0 salvo tarea explícita de regresión/fix
que autorice cambiarlas; ejecutar una regresión no autoriza por sí mismo cambios:

- Migraciones aprobadas y constraint
  `ex_appointments_active_barber_time_overlap`.
- Concurrencia y agenda independientes por barbero.
- Bloqueo transaccional `FOR NO KEY UPDATE`.
- Tratamiento de SQLSTATE `23P01` para la constraint esperada y respuesta 409.
- Solicitudes concurrentes solapadas del mismo barbero: **201 + 409**.
- Solicitudes concurrentes de barberos distintos: **201 + 201**.

Conservar también las garantías aprobadas de P1.1–P1.3: catálogo e IDs reales
de la API, ausencia de mocks de catálogo en producción, zona oficial desde
`BUSINESS_TIMEZONE`, separación entre fechas de calendario e instantes,
timestamps completos hasta el POST, disponibilidad futura y selección asociada
a la consulta vigente. No reconstruir timestamps con offsets fijos ni usar
`HH:mm` como identidad de un slot.

### Evolución futura de P2 y protección de P0/P1

- Las futuras migraciones P2 **NO modifican las revisiones aprobadas 0001–0003**;
  cualquier evolución autorizada debe añadirse en revisiones posteriores.
- **NO debilitar los guards** de base de datos ni de preflight para aceptar P2.
  El runner actualmente verifica `0003_barbers_and_schedules`; su evolución
  debe comprobar explícitamente la revisión aprobada esperada y conservar las
  verificaciones estructurales P0. No aceptar cualquier revisión posterior.
- Preservar `appointments.barber_id NOT NULL`, la agenda independiente por
  barbero y la constraint `ex_appointments_active_barber_time_overlap`.
- Preservar `FOR NO KEY UPDATE`, SQLSTATE `23P01` de la constraint esperada
  **-> 409**, concurrencia mismo barbero **201+409** y barberos distintos
  **201+201**.
- La protección futura de `POST /api/appointments` debe conservar la lógica
  validada de P1. Esta sincronización no autoriza cambios funcionales.

## Contrato P2.1 aprobado

Este contrato define el comportamiento autorizado para la implementación futura.
Los permisos pendientes no se conceden por inferencia ni por jerarquía de roles.
`owner` no hereda automáticamente permisos de `admin` ni de otros roles.

### Roles internos y acceso público

- Roles internos: `owner`, `admin`, `barber`, `client`.
- Visitante y todos los roles pueden consultar:
  - `GET /api/business-config`.
  - `GET /api/services`.
  - `GET /api/barbers`.
  - `GET /api/availability`.

### Reservas, agenda y servicios

- Solo `client` autenticado puede crear una reserva para sí mismo mediante
  `POST /api/appointments`; `client_user_id` se deriva server-side de la sesión.
- Cliente consulta y cancela únicamente sus propias reservas; no reprograma.
- `admin` puede reprogramar. La reprogramación por `barber` sigue pendiente;
  `owner` no hereda este permiso automáticamente.
- `barber` consulta y modifica únicamente su propia agenda y bloqueos. La
  identidad se resuelve server-side mediante `User ↔ Barber`; nunca confiar
  en un `barber_id` enviado por el navegador como prueba de identidad.
- `admin` crea, modifica y desactiva servicios, y gestiona precios y duración.
- Solo `owner` consulta ventas e ingresos. Registrar este permiso no autoriza
  implementar esos módulos.

### Registro y cuenta Propietario inicial

- El registro público crea exclusivamente cuentas `client`; nunca acepta
  `role` desde el navegador. No existe registro público de `admin`, `barber`
  ni `owner`.
- La cuenta Propietario inicial no tendrá endpoint público. El provisionamiento
  mediante comando administrativo controlado es la propuesta para P2.2;
  su procedimiento operativo queda por concretar en esa fase, si se autoriza.

### Sesión y contraseñas

- Cookie `HttpOnly` y sesión server-side.
- `Secure` en producción, `SameSite` explícito y CSRF en operaciones mutantes.
- `401` sin identidad válida; `403` con identidad válida sin permiso.
- Contraseñas mediante Argon2id, sin `trim` automático y nunca en texto plano
  en almacenamiento, logs o informes.
- No inventar políticas empresariales de longitud, símbolos obligatorios,
  expiración o cambio periódico de contraseñas.

### Modelo conceptual aprobado

- `Barber.user_id -> User.id`, con FK y `UNIQUE`.
- `Appointment.client_user_id -> User.id`, con FK.
- `client_user_id` será nullable inicialmente para conservar reservas P1
  históricas. Las nuevas reservas creadas tras activar P2 deben asociarlo
  obligatoriamente al Cliente autenticado, derivándolo de la sesión.
- Esta definición es conceptual: no confirma cambios ya aplicados al modelo
  ni autoriza crear o ejecutar migraciones.

### Decisiones pendientes

Mantener expresamente como **DECISIÓN PENDIENTE**, sin conceder permisos:

- Barbero reprogramando reservas.
- Administrador/Propietario gestionando agendas ajenas.
- Gestión de usuarios internos y roles: creación, asignación, cambio y
  desactivación de usuarios.
- Cambio de contraseña propia.
- Recuperación de contraseña y su canal; no asumir email, SMS ni WhatsApp.
- Reglas detalladas de cancelación y reprogramación.
- Transición y tratamiento de reservas históricas sin `client_user_id`, además
  de la nulabilidad inicial ya aprobada.
- Fuente de `client_name` y `client_phone`: perfil o snapshot editable.

Estas decisiones pendientes delimitan funcionalidades futuras; no reabren el
contrato P2.1 aprobado ni autorizan implementarlas. Pagos, ventas,
clientes/historial, notificaciones, inventario y panel administrativo requieren
autorización separada y no quedan habilitados por este contrato.

## Seguridad de bases de datos

- Nunca usar `logia_barber` para pruebas destructivas. Las pruebas PostgreSQL
  deben dirigirse exclusivamente a `logia_barber_p0_test`.
- Conservar los guards que comprueban el nombre exacto tanto en la URL como
  mediante `SELECT current_database()`. No aceptar nombres parecidos ni reglas
  del tipo «contiene test». No desactivar protecciones para conseguir un PASS.
- Nunca exportar manualmente `P0_TEST_PREPARED=1`. Solo el runner lo pasa a sus
  subprocess después de superar el preflight completo.
- Para regresiones reales sobre la base existente, usar desde `backend/`:

  ```sh
  .venv/bin/python -B -m tests.run_p0_validation --reuse-existing
  ```

  `P0_TEST_DATABASE_URL` debe estar configurada de forma privada y apuntar
  exclusivamente a `logia_barber_p0_test`. No usar el modo de creación inicial
  para reutilizarla. En reuse no realizar `normal_snapshot` ni operaciones
  sobre la base principal.
- `logia_barber_app` permanece sin `CREATEDB`; no concederlo salvo tarea
  explícitamente autorizada. No borrar ni recrear bases automáticamente.
- No ejecutar seed contra la base principal sin autorización explícita.
  Los bloques de almuerzo históricos no se eliminan automáticamente; una
  limpieza sería una operación separada y auditada.
- No mostrar ni registrar contraseñas, URLs con credenciales o contenido secreto
  de `.env`. Los informes deben contener evidencia sin secretos.
- Un fallo del sandbox o de conexión no equivale a una regresión funcional ni
  a una prueba aprobada. Informar qué no se pudo ejecutar, sin eludir permisos.

## Roles de trabajo y delegación

Estos roles definen responsabilidades para las tareas que delegue COORDINATOR;
no requieren que todos los agentes trabajen simultáneamente. Cada encargo debe
indicar objetivo, alcance, archivos asignados, restricciones y evidencia esperada.

### COORDINATOR

- Coordinar, dividir trabajo y asignar propietarios de archivos antes de editar.
- Evitar ediciones simultáneas conflictivas e integrar resultados coherentes.
- Recoger evidencia de código, comandos, resultados, omisiones y limitaciones.
- Decidir qué debe ejecutar el usuario fuera del sandbox cuando el entorno
  impida una validación; proporcionar el comando y explicar la limitación.
- No declarar una fase aprobada si falta evidencia obligatoria. Emitir el
  informe consolidado y respetar la autorización antes de cambiar de fase.

### BACKEND

- Trabajar solo en backend salvo autorización explícita para ampliar el ámbito.
- Atender FastAPI, services, schemas y reglas de negocio dentro de la tarea.
- No crear ni ejecutar migraciones automáticamente. Preservar P0.

### FRONTEND

- Trabajar solo en frontend salvo autorización explícita para ampliar el ámbito.
- Atender React, TypeScript y el cliente API.
- No duplicar reglas de negocio cuya fuente corresponde al backend; consumir
  los contratos públicos y conservar las garantías temporales aprobadas.

### QA

- Priorizar pruebas y regresiones del alcance asignado.
- No arreglar funcionalidad silenciosamente. Si encuentra un fallo, comunicarlo
  a COORDINATOR con reproducción y evidencia; no ampliar su encargo por cuenta propia.
- Nunca usar `logia_barber` como base de pruebas.
- Registrar comandos, entorno no secreto, códigos de salida y cantidades de
  casos aprobados, fallidos y omitidos. Distinguir mocks de PostgreSQL real.

### AUDITOR

- Trabajar en lectura; no implementar cambios.
- Comparar código, pruebas y requisitos; buscar regresiones, mocks en producción,
  hardcodes, uso incorrecto de zonas horarias y cambios fuera de alcance.
- Distinguir un análisis de código de una comprobación realmente ejecutada.
- Emitir dictamen **APROBABLE**, **PARCIAL** o **BLOQUEADO**, con evidencia y
  pendientes. Un dictamen APROBABLE no autoriza avanzar a otra fase.

## Propiedad de archivos y paralelismo

- Dos subagentes no deben editar simultáneamente el mismo archivo.
- COORDINATOR registra en los encargos el propietario de cada archivo o conjunto
  de archivos y coordina cualquier transferencia de propiedad.
- Paralelizar tareas independientes; usar worktrees separados cuando corresponda
  y el entorno Git lo permita, integrando después los cambios de forma controlada.
- QA y AUDITOR pueden leer archivos mientras otro agente trabaja, pero no
  editarlos simultáneamente. La validación final debe identificar la versión
  revisada; cambios posteriores invalidan la evidencia afectada.
- Coordinar las ejecuciones que comparten base de pruebas o informes para evitar
  interferencias y sobrescrituras de evidencia entre agentes.

## Flujo de cada fase

1. COORDINATOR define alcance, límites y propiedad de archivos.
2. Los agentes asignados analizan sus tareas.
3. Se implementa únicamente lo autorizado.
4. QA ejecuta las pruebas y regresiones correspondientes.
5. AUDITOR revisa requisitos, cambios y evidencia.
6. COORDINATOR emite el informe consolidado.
7. No se avanza a la siguiente fase sin autorización.

## Formato de informe

Todo informe de fase comienza exactamente con:

`ORIGEN Y ALCANCE DEL INFORME`

Debe identificar proyecto y fase, y distinguir expresamente:

- **HECHO VERIFICADO EN CÓDIGO**.
- **HECHO VERIFICADO EN PRUEBAS**: comandos, resultados y tipo de entorno.
- **NO VERIFICADO**: pendientes, omisiones y limitaciones.
- **REGRESIONES**: fases protegidas y resultado observado.
- **ARCHIVOS MODIFICADOS**: rutas y propósito de los cambios.

No confundir planes, lectura de código, mocks, resultados históricos o evidencia
informada por el usuario con pruebas ejecutadas en la tarea actual. Conservar
los formatos adicionales que pida el usuario para cada fase.

## Cierre documental y siguiente fase

- P0 y P1 completo permanecen aprobados con la evidencia de referencia indicada.
- P2.1 queda cerrado como contrato aprobado después de esta sincronización.
- P2.2 permanece **NO INICIADO** y requiere autorización explícita para comenzar.
- Una sincronización exclusivamente documental no requiere pruebas funcionales
  ni ejecución PostgreSQL. Verificar el diff y el alcance de archivos modificados;
  no presentar evidencia histórica como una ejecución nueva.
