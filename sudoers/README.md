# sudoers/

Permisos sudo para el usuario `kaplabilling`. install.sh copia el archivo a `/etc/sudoers.d/kaplabilling` y lo valida con `visudo -c`.

## Archivo

`kaplabilling` — permisos NOPASSWD mínimos:

```
kaplabilling ALL=(ALL) NOPASSWD: /usr/sbin/nft
kaplabilling ALL=(ALL) NOPASSWD: /usr/sbin/kamcmd
```

## Por qué solo estos dos comandos

- `nft`: necesario para que `gen_nftables.py` aplique cambios de firewall en tiempo real desde el panel web
- `kamcmd`: necesario para que `gen_dispatcher.py` recargue la lista de carriers en Kamailio sin reiniciarlo

**No se agrega nada más.** Si un proceso de la plataforma necesita acceso root a algo nuevo, revisar si hay otra forma (permisos de grupo, capabilities de Linux) antes de ampliar sudoers.

## Verificar que está correcto

```bash
visudo -c -f /etc/sudoers.d/kaplabilling
sudo -u kaplabilling sudo nft list ruleset
```

---

> © 2026 [KPBTec](https://github.com/KPBTec) · Ver [Licencia y Autoría](../AUTHORS.md)
