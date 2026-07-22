# Hotfix 34 - Sincronizacion del esquema de analisis Python

Restaura PythonSourceAnalysisRequest y PythonSourceAnalysisResponse en el esquema de authoring.
El ZIP 30 habia sobrescrito el archivo con una version que conservaba las conexiones de nodos,
pero omitio estas clases que seguian siendo importadas por el endpoint administrativo.
