# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Setup común para toda la suite: agrega backend/ al sys.path (los módulos del
proyecto se importan como top-level — "import main", "from routers import
cdrs" — igual que corre uvicorn, no como paquete) y define variables de
entorno REQUERIDAS por auth.py/database.py al importar (JWT_SECRET,
DATABASE_URL) antes de que cualquier test importe esos módulos. Son valores
dummy — ningún test de este archivo abre una conexión real a MySQL.
"""
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("JWT_SECRET", "test-secret-not-real")
os.environ.setdefault("DATABASE_URL", "mysql+aiomysql://test:test@localhost/voxikam_test")
os.environ.setdefault("CDR_INGEST_SECRET", "test-ingest-secret")
