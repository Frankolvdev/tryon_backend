# Hotfix Modal: serialización JSON de fechas

Corrige el error `Object of type datetime is not JSON serializable` al enviar el pipeline completo al runtime Modal.

El payload se normaliza mediante `fastapi.encoders.jsonable_encoder`, conservando intactos el pipeline, los ejecutores existentes, Redis, tokens, estados y salidas.
