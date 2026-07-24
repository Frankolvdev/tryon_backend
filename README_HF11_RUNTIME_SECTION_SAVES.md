# MegaZIP 3B HF11 — Guardado por sección y guardado global

Este Hotfix modifica únicamente el BackOffice.

## Qué cambia

En `RuntimeMega3Panel` quedan tres acciones independientes:

1. **Guardar exportación**
   - Guarda únicamente `models-volume/settings`.
   - Actualiza el estado de la sección con la respuesta persistida.

2. **Guardar Runtime Configuration**
   - Guarda únicamente `runtime-launch/settings`.
   - Actualiza `build_name`, `image_name`, `container_name`, puertos, GPU y volúmenes
     con la respuesta realmente persistida.

3. **Guardar toda la configuración**
   - Guarda ambas secciones mediante `Promise.all`.
   - Solo muestra éxito cuando las dos operaciones terminaron.
   - Si alguna falla, no presenta el resultado como guardado completo.

Al iniciar una exportación, primero se ejecuta el guardado global sin mostrar un
toast duplicado.

## Aplicación

Descomprime el ZIP directamente sobre la raíz de `tryon_backoffice`.

No contiene carpeta raíz adicional.

Ejecuta:

```powershell
python apply_hf11_runtime_section_saves.py
Remove-Item -Recurse -Force .next -ErrorAction SilentlyContinue
npm run build
npm run dev
```

## Prueba

1. Cambia solamente un campo de Runtime Configuration.
2. Pulsa **Guardar Runtime Configuration**.
3. Recarga y comprueba que permanece.
4. Cambia un campo de exportación.
5. Pulsa **Guardar exportación**.
6. Modifica campos en ambas secciones.
7. Pulsa **Guardar toda la configuración**.
8. Recarga y confirma ambos cambios.

## Git

Después de comprobar el funcionamiento, elimina el respaldo generado:

```powershell
Get-ChildItem -Recurse -Filter "*.hf11.bak" | Remove-Item
```

Luego:

```bash
git add .
git commit -m "fix: add runtime section and global save actions"
git push
```
