#!/bin/bash
# la plataforma anterior — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

# Desactiva firewalls competidores — el sistema usa solo nftables

source "$(dirname "$0")/../_colors.sh"

hdr "Desactivando firewalls competidores (solo nftables)"

systemctl is-active --quiet ufw 2>/dev/null && {
    ufw disable 2>/dev/null; systemctl disable ufw 2>/dev/null
    ok "UFW desactivado"
}

systemctl is-active --quiet firewalld 2>/dev/null && {
    systemctl stop firewalld; systemctl disable firewalld; systemctl mask firewalld
    ok "firewalld desactivado y enmascarado"
}

command -v iptables &>/dev/null && {
    IPT=$(iptables -L INPUT --line-numbers 2>/dev/null | wc -l)
    [[ "$IPT" -gt 3 ]] && {
        iptables -F; iptables -X; iptables -Z
        iptables -P INPUT ACCEPT; iptables -P FORWARD ACCEPT; iptables -P OUTPUT ACCEPT
        ip6tables -F 2>/dev/null; ip6tables -X 2>/dev/null || true
        systemctl stop iptables 2>/dev/null; systemctl disable iptables 2>/dev/null
        ok "iptables limpiado"
    }
}

ok "nftables será el único firewall del sistema"
