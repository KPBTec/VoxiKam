#!/usr/bin/env python3
# la plataforma anterior — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Valida el parsing de kamcmd dlg.briefing en el SBC.
Corre directamente en el servidor: python3 test_dlg_briefing.py
"""
import subprocess, re, time, sys


def parse_dlg_briefing(output: str) -> list:
    calls = []
    current = {}
    now = int(time.time())

    for line in output.splitlines():
        line = line.strip()
        if line == "{":
            current = {}
        elif line == "}":
            if current.get("state") == "4" and current.get("start_ts", 0) > 0:
                start    = int(current["start_ts"])
                dur      = max(now - start, 0)
                from_uri = current.get("from_uri", "")
                to_uri   = current.get("to_uri", "")

                m1 = re.match(r"sip:([^@]+)@([\d.]+)", from_uri)
                src_number = m1.group(1) if m1 else from_uri
                src_ip     = m1.group(2) if m1 else ""

                m2 = re.match(r"sip:([^@]+)@", to_uri)
                dst_raw    = m2.group(1) if m2 else to_uri
                dst_number = re.sub(r"^\d{2,6}(51\d{9,})", r"\1", dst_raw) or dst_raw

                m3 = re.match(r"^(\d{2,6})51", dst_raw)
                techprefix = m3.group(1) if m3 else "?"

                calls.append({
                    "call_id":    current.get("call-id", ""),
                    "src":        src_number,
                    "src_ip":     src_ip,
                    "dst":        dst_number,
                    "dst_raw":    dst_raw,
                    "dur_sec":    dur,
                    "dur_fmt":    f"{dur//3600:02d}:{(dur%3600)//60:02d}:{dur%60:02d}",
                    "techprefix": techprefix,
                })
            current = {}
        elif ":" in line:
            k, _, v = line.partition(":")
            current[k.strip()] = v.strip()

    return calls


# ── Ejecutar kamcmd ────────────────────────────────────────────────────────────
try:
    result = subprocess.run(
        ["kamcmd", "dlg.briefing", "ftcISs"],
        capture_output=True, text=True, timeout=5
    )
except FileNotFoundError:
    print("ERROR: kamcmd no encontrado — ejecuta en el servidor SBC")
    sys.exit(1)

if not result.stdout.strip():
    print("ERROR: kamcmd no retornó datos (¿Kamailio corriendo?)")
    print(result.stderr[:200])
    sys.exit(1)

calls = parse_dlg_briefing(result.stdout)

# ── Output ─────────────────────────────────────────────────────────────────────
print(f"\n=== dlg.briefing — {len(calls)} llamadas state=4 (CONFIRMED/CONTESTADAS) ===\n")
print(f"{'DURACION':<10} {'ORIGEN':<16} {'DESTINO':<15} {'TECHPFX':<8} {'IP ASTERISK':<16} {'CALL-ID[:24]'}")
print("─" * 95)

for c in sorted(calls, key=lambda x: -x["dur_sec"]):
    flag = " ⚠️ >1H" if c["dur_sec"] > 3600 else ""
    print(f"{c['dur_fmt']:<10} {c['src']:<16} {c['dst']:<15} {c['techprefix']:<8} {c['src_ip']:<16} {c['call_id'][:24]}{flag}")

# ── Resumen techprefixes ───────────────────────────────────────────────────────
prefixes: dict[str, int] = {}
for c in calls:
    prefixes[c["techprefix"]] = prefixes.get(c["techprefix"], 0) + 1

print(f"\n{'Techprefix':<12} {'Llamadas':>8}  → cliente (verificar en DB: SELECT name FROM customers WHERE techprefix='X')")
print("─" * 60)
for p, count in sorted(prefixes.items()):
    print(f"  {p:<10} {count:>6}")

# ── Resumen IPs Asterisk ───────────────────────────────────────────────────────
ips: dict[str, int] = {}
for c in calls:
    ips[c["src_ip"]] = ips.get(c["src_ip"], 0) + 1

print(f"\n{'IP Asterisk':<18} {'Llamadas':>8}  → (verificar: SELECT name FROM customers JOIN customer_ips ON ...)")
print("─" * 60)
for ip, count in sorted(ips.items()):
    print(f"  {ip:<16} {count:>6}")

# ── Alertas ────────────────────────────────────────────────────────────────────
long_calls = [c for c in calls if c["dur_sec"] > 3600]
if long_calls:
    print(f"\n⚠️  LLAMADAS > 1 HORA: {len(long_calls)}")
    for c in long_calls:
        print(f"   {c['src']} → {c['dst']}  {c['dur_fmt']}  call_id={c['call_id'][:32]}")
else:
    print(f"\n✓  Sin llamadas > 1 hora")

bad_prefix = [c for c in calls if c["techprefix"] == "?"]
if bad_prefix:
    print(f"\n⚠️  {len(bad_prefix)} llamadas sin techprefix reconocido — revisar to_uri:")
    for c in bad_prefix[:5]:
        print(f"   dst_raw={c['dst_raw']}")
else:
    print(f"✓  Todos los techprefixes detectados correctamente")

print(f"\nTotal state=4: {len(calls)}")
