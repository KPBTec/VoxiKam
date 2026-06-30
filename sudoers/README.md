# sudoers/

Permisos sudo para el usuario `voxikam`. install.sh copia el archivo a `/etc/sudoers.d/voxikam` y lo valida con `visudo -c`.

## Archivo

`voxikam` — permisos NOPASSWD mínimos:

```
voxikam ALL=(ALL) NOPASSWD: /usr/sbin/nft
voxikam ALL=(ALL) NOPASSWD: /usr/sbin/kamcmd
```

## Por qué solo estos dos comandos

- `nft`: necesario para que `gen_nftables.py` aplique cambios de firewall en tiempo real desde el panel web
- `kamcmd`: necesario para que `gen_dispatcher.py` recargue la lista de carriers en Kamailio sin reiniciarlo

**No se agrega nada más.** Si un proceso de la plataforma necesita acceso root a algo nuevo, revisar si hay otra forma (permisos de grupo, capabilities de Linux) antes de ampliar sudoers.

## Verificar que está correcto

```bash
visudo -c -f /etc/sudoers.d/voxikam
sudo -u voxikam sudo nft list ruleset
```

---

> © 2026 [KPBTec](https://github.com/KPBTec) · Ver [Licencia y Autoría](../AUTHORS.md)
