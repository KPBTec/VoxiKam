# rtpengine/

Configuración de RTPEngine — relay de media para el SBC.

## Archivo

`rtpengine.conf` — config con `__PLACEHOLDER__`. `apply_conf()` lo copia a `/etc/rtpengine/rtpengine.conf`.

## Placeholders

| Placeholder | Valor |
|---|---|
| `__PUBLIC_IP__` | IP pública (WAN, hacia carriers e internet) |
| `__PRIVATE_IP__` | IP privada (LAN, hacia Asterisks clientes) |

## Configuración relevante

```ini
# Interfaz dual: privada para LAN, pública para WAN
interface = priv/__PRIVATE_IP__;pub/__PUBLIC_IP__

# Rango de puertos UDP para RTP/RTCP
port-min = 20000
port-max = 40000

# Puerto de control (Kamailio habla con RTPEngine aquí)
listen-ng = 127.0.0.1:2223
```

## Por qué interfaz dual

Los clientes (Asterisks) están en la LAN privada y conectan vía `__PRIVATE_IP__`. Los carriers están en internet y conectan vía `__PUBLIC_IP__`. RTPEngine hace el relay entre ambos lados sin que el tráfico de media tenga que salir a internet y volver.

## Verificar que corre

```bash
systemctl status rtpengine
# RTPEngine no tiene un health check HTTP, verificar que escucha el puerto ng:
ss -ulnp | grep 2223
```

## Logs

```bash
journalctl -u rtpengine -n 50 -f
```

---

## 📜 Licencia

Este proyecto está licenciado bajo los términos de la [Licencia AGPL v3](../LICENSE), que requiere que cualquier modificación distribuida o usada como servicio de red sea publicada bajo los mismos términos.

> **Autoría**: Este software fue creado y es mantenido por [KPBTec](https://github.com/KPBTec).  
> Aunque es de código abierto, se agradece el reconocimiento correspondiente en derivados o menciones públicas.

---

## 👤 Autor

Desarrollado por [KPBTec](https://github.com/KPBTec) · Knowledge, Protection & Business Technology  
© 2026 – Todos los derechos reservados.
