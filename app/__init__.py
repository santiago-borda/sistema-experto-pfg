"""app — Capa de presentación del SE-ITT (Fase 3).

Adaptador HTTP sobre el núcleo simbólico. La dependencia va SIEMPRE
`app/ -> seitt_core/`, nunca al revés: el motor clínico es utilizable como
biblioteca sin levantar un servidor, y eso lo verifica
`tests/test_architecture.py`.
"""
