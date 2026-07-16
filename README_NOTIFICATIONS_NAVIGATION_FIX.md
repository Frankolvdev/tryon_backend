# 10E — Notifications Navigation Fix

## Problema corregido

El módulo de Notificaciones tenía cuatro pantallas funcionales, pero solo el Centro estaba enlazado desde la navegación principal. Las demás rutas existían, aunque quedaban ocultas para el administrador.

## Solución

Se agrega un layout compartido para todo el módulo:

`src/app/dashboard/notifications/layout.tsx`

Este layout aparece automáticamente en:

- `/dashboard/notifications`
- `/dashboard/notifications/preferences`
- `/dashboard/notifications/deliveries`
- `/dashboard/notifications/announcements`

## Incluye

- Barra superior con las cuatro secciones.
- Estado visual de la pestaña activa.
- Breadcrumb:
  - Dashboard
  - Notificaciones
  - Sección actual
- Tarjetas de acceso rápido dentro del Centro.
- Diseño responsive.
- Navegación horizontal desplazable en pantallas pequeñas.
- Sin cambios al backend.
- Sin dependencias nuevas.
- Sin duplicar ni reemplazar las cuatro páginas existentes.

## Instalación

Extrae directamente sobre:

`F:\PROYECTOS PERSONALES\TRYON\backoffice`

El ZIP no contiene una carpeta raíz adicional.

Después ejecuta:

```powershell
Remove-Item -Recurse -Force .next -ErrorAction SilentlyContinue
npm run build
npm run dev
```

## Pruebas

1. Abre `/dashboard/notifications`.
2. Comprueba las cuatro tarjetas.
3. Abre Preferencias y canales.
4. Cambia a Entregas desde la barra superior.
5. Cambia a Anuncios.
6. Regresa al Centro.
7. Comprueba la navegación en móvil.

## Git

```powershell
git add .
git commit -m "Notifications - Add complete module navigation"
git push
```
