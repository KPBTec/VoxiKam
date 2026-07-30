# 9. Firewall y seguridad

VoxiKam incluye un módulo de **Seguridad** que te permite administrar la protección del servidor sin necesidad de abrir una consola SSH ni tocar comandos de sistema. Desde el panel web puedes controlar tres capas independientes:

1. El **firewall global** del servidor (reglas a nivel del kernel, aplicadas con `nftables`).
2. Las **IPs autorizadas** de cada cliente (una whitelist propia para cada trunk SIP).
3. **Fail2ban**, que muestra qué protecciones automáticas están activas y qué IPs están baneadas en este momento.

Estas tres capas son complementarias, no sustitutas entre sí: una IP puede estar permitida en el firewall global y aun así no poder cursar tráfico de un cliente si no está en la whitelist de ese cliente en particular. Más adelante en este capítulo se explica esa diferencia con un ejemplo real.

## 9.1 Firewall del servidor

La pantalla de **Firewall** te permite crear reglas que se aplican directamente sobre el firewall del servidor (`nftables`), es decir, a nivel del kernel, antes de que el tráfico llegue a cualquier aplicación. Cada regla se define sobre una IP o un rango CIDR, y puede tener una de tres acciones:

- **ALLOW (permitir)**: la IP o rango indicado tiene acceso permitido de forma explícita. Se usa típicamente para oficinas propias, IPs de administración o carriers de confianza que necesitas asegurarte de que nunca queden bloqueados por error.
- **DENY (bloquear)**: la IP o rango indicado queda bloqueado de forma permanente. Se usa cuando ya identificaste una IP maliciosa (por ejemplo, un scanner de vulnerabilidades) y quieres cerrarle el paso de forma definitiva.
- **JAIL (bloqueo automático)**: no es una regla que cargues manualmente sobre una IP puntual, sino que envía esa IP a la gestión de **fail2ban** (ver sección 9.3) por haber mostrado un comportamiento sospechoso, como intentos repetidos de autenticación fallida.

Cada regla puede llevar una **etiqueta** descriptiva, para que cualquier operador que revise el firewall más adelante entienda de un vistazo por qué se creó esa regla, sin tener que adivinar a partir de la sola dirección IP.

Referencia visual: `img/admin-firewall.png`.

En la captura de referencia se ven tres reglas activas, que ilustran los tres casos de uso típicos:

1. **ALLOW** para la IP **190.20.50.5**, etiquetada **"Oficina principal Comercial Andes"**. Es una IP conocida y de confianza (la oficina de un cliente), que se deja explícitamente permitida.
2. **JAIL** para la IP **185.220.101.5**, etiquetada **"Fuerza bruta SIP detectada"**. Esta IP intentó repetidamente autenticarse contra el sistema sin éxito, un patrón típico de ataque de fuerza bruta contra SIP, por lo que quedó bajo el control automático de fail2ban.
3. **DENY** para la IP **45.33.10.20**, etiquetada **"Scanner detectado (sqlmap) — bloqueado"**. En este caso se detectó una herramienta de escaneo de vulnerabilidades (sqlmap) intentando explorar el sistema, por lo que la IP fue bloqueada de forma directa y permanente.

Como operador, la lógica para elegir la acción correcta es sencilla:

- Si sabés que una IP es de confianza y necesitás garantizar que siempre tenga acceso → **ALLOW**.
- Si identificaste una IP claramente maliciosa y querés cerrarle el paso ya mismo → **DENY**.
- Si el sistema ya detectó comportamiento sospechoso (fuerza bruta, escaneo, intentos repetidos) → la IP normalmente termina en **JAIL** de forma automática, gestionada por fail2ban.

## 9.2 IPs autorizadas por cliente

Además del firewall global, cada cliente configurado en VoxiKam tiene su propia lista de **IPs autorizadas**. Esta es una capa de seguridad distinta y adicional: mientras el firewall (sección 9.1) protege al servidor completo, la lista de IPs autorizadas protege el tráfico de **cada cliente en particular**.

El funcionamiento es estricto: cualquier llamada SIP que llegue desde una IP que no esté en la lista autorizada de ese cliente es **rechazada automáticamente** por Kamailio, sin que el servidor siquiera responda de forma que revele su existencia. En otras palabras, para un origen no autorizado, el servidor de VoxiKam es indistinguible de una IP que simplemente no responde.

Referencia visual: `img/admin-security-customer-ips.png`.

En la captura de referencia se observa el listado de IPs autorizadas por cliente:

- **Call Center Norte** → **190.20.2.10**
- **Comercial Andes SAC** → **190.20.1.10**
- **Distribuidora Milenio** → **190.20.3.10**
- **Grupo Reventa Perú** → **190.20.4.10**
- **Callao Voz SAC** → sin ninguna IP cargada todavía

Este último caso es importante de entender bien: **un cliente sin ninguna IP autorizada queda con su trunk efectivamente bloqueado**, ya que no existe ninguna IP desde la cual el sistema vaya a aceptar sus llamadas. No es un error ni una falla del sistema: es el comportamiento esperado hasta que un operador ingrese al menos una IP autorizada para ese cliente. Si el cliente **Callao Voz SAC** reporta que no puede originar llamadas, lo primero a revisar en esta pantalla es precisamente si ya tiene una IP autorizada cargada.

Para autorizar una IP a un cliente:

1. Entrá a la pantalla de **IPs autorizadas** dentro del módulo de Seguridad.
2. Ubicá al cliente correspondiente en el listado.
3. Agregá la IP (o rango) desde la cual ese cliente va a originar sus llamadas.
4. Guardá el cambio. A partir de ese momento, el cliente podrá cursar tráfico desde esa IP.

## 9.3 Fail2ban

La pantalla de **Fail2ban** te muestra el estado de las protecciones automáticas contra comportamiento malicioso reiterado, como intentos de acceso por fuerza bruta.

Fail2ban trabaja mediante **jails** (celdas): cada jail vigila un servicio específico del servidor y, cuando detecta un patrón de comportamiento sospechoso repetido desde una misma IP (por ejemplo, varios intentos de inicio de sesión fallidos en poco tiempo), banea automáticamente esa IP por un período determinado, sin necesidad de intervención manual.

Referencia visual: `img/admin-security-fail2ban.png`.

En la captura de referencia se observan dos jails configurados y activos:

- **sshd**: protege el acceso por SSH al servidor.
- **voxikam-security**: protege el panel web de VoxiKam.

En el momento de la captura, la pantalla indica **"Sin IPs baneadas"**, es decir, ningún jail tiene actualmente ninguna IP bloqueada porque no se ha detectado ningún ataque activo. Cuando sí existan IPs baneadas, esta misma pantalla las lista junto al jail que las bloqueó.

Si una IP fue baneada por error (por ejemplo, un usuario legítimo que escribió mal su contraseña varias veces seguidas), esta pantalla ofrece la opción de **desbanearla manualmente**, sin tener que esperar a que expire el bloqueo automático ni entrar por SSH al servidor. Para hacerlo:

1. Entrá a la pantalla de **Fail2ban**.
2. Ubicá la IP baneada en el listado correspondiente al jail afectado.
3. Usá la opción de **desbanear** sobre esa IP.
4. La IP recupera el acceso normal de inmediato.

## 9.4 Resumen de las tres capas

Para tener siempre claro qué capa revisar según el problema:

| Situación | Dónde revisar |
|---|---|
| Quiero bloquear o permitir una IP a nivel de todo el servidor | **Firewall** (sección 9.1) |
| Un cliente no puede originar llamadas y no hay ninguna regla de firewall que lo explique | **IPs autorizadas** del cliente (sección 9.2) |
| Un usuario legítimo quedó bloqueado por intentos fallidos repetidos | **Fail2ban** (sección 9.3), para desbanearlo manualmente |
| Se detectó un ataque de fuerza bruta o un scanner | **Firewall**, para ver si ya quedó en JAIL o si conviene pasarlo a DENY |
