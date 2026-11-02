"""index.py — Punto de entrada para Vercel (demo del prototipo).

Vercel detecta una aplicación FastAPI buscando un objeto `app` en archivos
como `index.py`. Este módulo solo lo reexporta: el adaptador HTTP real sigue
siendo `app.api.main`, que además monta el frontend estático desde
`app/web/`. No hay lógica acá; el despliegue serverless y el contenedor
Docker sirven exactamente la misma aplicación.
"""

from app.api.main import app

__all__ = ["app"]
