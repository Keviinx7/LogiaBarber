# Sistema de Gestión para Logia Barber

Sistema web de reservas de **Logia Barber**.

## Identidad del proyecto

- Empresa y texto visible: **Logia Barber**.
- Nombre completo: **Sistema de Gestión para Logia Barber**.
- Carpeta y repositorio: `LogiaBarber`.
- Slug: `logia-barber`.
- Identificadores Python/configuración: `logia_barber`.
- Base de desarrollo prevista en ejemplos: `logia_barber`.
- Única base PostgreSQL autorizable para P0: `logia_barber_p0_test`.

El nombre de la base en `.env` debe seguir correspondiendo a la base real hasta
que se autorice por separado su migración de nombre. Cambiar este documento o
`.env.example` no renombra una base existente. La validación PostgreSQL P0 queda
pendiente de autorización; véase `backend/tests/README.md`.

## Estructura

- `frontend/`: React 19, TypeScript, Vite y Tailwind CSS.
- `backend/`: FastAPI, SQLAlchemy y PostgreSQL.

## Fases

1. Estructura base y arranque local.
2. Modelo de datos, migraciones y configuración de PostgreSQL.
3. API pública de servicios, disponibilidad y reservas.
4. Autenticación y API administrativa.
5. Interfaz pública de reservas.
6. Panel administrativo.
7. Pruebas, endurecimiento de seguridad y despliegue.

## Arranque rápido

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
