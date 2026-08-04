# Fix: visibilidad inmediata al eliminar planes

Los planes con historial no se borran físicamente. Ahora reciben un estado
explícito `archived_at` y dejan de aparecer en el catálogo administrativo desde
la primera eliminación. Las suscripciones históricas conservan su referencia.

La migración también identifica los planes que el hotfix anterior ya había
desactivado y ocultado, siempre que estén referenciados por una suscripción.
