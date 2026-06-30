#!/usr/bin/env python3
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Genera SOLO los archivos .env (backend + frontend) desde templates Jinja2.
Los configs estáticos (nginx, nftables, rtpengine) son aplicados por install.sh
directamente con sed desde sus carpetas: nginx/, nftables/, rtpengine/
"""
import argparse
import os
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

BASE_DIR = Path(__file__).parent.parent
TMPL_DIR = BASE_DIR / "templates"
j2       = Environment(loader=FileSystemLoader(str(TMPL_DIR)))


def render(tmpl: str, **ctx) -> str:
    return j2.get_template(tmpl).render(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        **ctx
    )


def write(path: str | Path, content: str, mode: int = 0o644):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    os.chmod(p, mode)
    print(f"  ✓ {p}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--public-ip");   ap.add_argument("--private-ip")
    ap.add_argument("--private-net"); ap.add_argument("--mgmt-ip")
    ap.add_argument("--web-port");    ap.add_argument("--domain")
    ap.add_argument("--db-host");     ap.add_argument("--db-port")
    ap.add_argument("--db-name");     ap.add_argument("--db-user")
    ap.add_argument("--db-pass");     ap.add_argument("--jwt-secret")
    ap.add_argument("--install-dir", default=str(BASE_DIR))
    args = ap.parse_args()

    ctx = dict(
        public_ip   = args.public_ip,
        private_ip  = args.private_ip,
        private_net = args.private_net,
        mgmt_ip     = args.mgmt_ip,
        web_port    = args.web_port,
        domain      = args.domain,
        db_host     = args.db_host,
        db_port     = args.db_port,
        db_name     = args.db_name,
        db_user     = args.db_user,
        db_pass     = args.db_pass,
        jwt_secret  = args.jwt_secret,
        install_dir = args.install_dir,
    )

    print("Generando .env files...")

    write(f"{args.install_dir}/backend/.env",        render("backend.env.j2",  **ctx), mode=0o600)
    write(f"{args.install_dir}/frontend/.env.local", render("frontend.env.j2", **ctx))

    Path(f"{args.install_dir}/invoices").mkdir(parents=True, exist_ok=True)
    print("  ✓ directorio invoices/")

    print("Listo.")


if __name__ == "__main__":
    main()
