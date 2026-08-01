# HF61 — Beam Manual Build / Fast Deploy

## Flujo conservado

1. Exportar Runtime.
2. Build.
3. Deploy.

No hay decisiones automáticas entre Build y Deploy.

## Build de Beam

Cuando la configuración del Runtime Builder tiene `provider = beam`, el botón Build:

- calcula la huella del runtime exportado;
- construye únicamente la imagen exclusiva de Beam;
- reutiliza las capas Docker salvo que se seleccione "sin caché";
- etiqueta la imagen como `beam-<huella>`;
- publica automáticamente esa imagen en el registro configurado;
- guarda `fingerprint` e `image_ref` dentro del build.

El Build requiere una `Imagen del registro` real y una sesión Docker iniciada en ese registro. No existe un paso manual adicional de "Publicar" para Beam.

## Deploy de Beam

Deploy:

- utiliza exclusivamente la imagen guardada por Build;
- valida que la huella siga coincidiendo;
- sincroniza solo el Dockerfile de referencia y `tryon_beam_app.py`;
- nunca construye ni sincroniza `custom_nodes`;
- se detiene con un mensaje claro si falta Build o si cambió el runtime.

## Blindaje

No se modifican las ramas de Modal ni RunPod. Tampoco se modifica `beam_worker/app.py`, el runtime de generación, resultados, cancelación, SAM3, Execute Python, AppWeb ni BackOffice.

## Uso

- Cambio de GPU, inactividad, workers, checkpoint o timeout: guardar y Deploy.
- Cambio de nodos, ComfyUI, requisitos o scripts: Exportar, Build y Deploy.
