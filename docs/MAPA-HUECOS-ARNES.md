# Mapa de huecos del arnés: dónde puede ganar sanchopanza (2026-10-05)

Escrito por indagis-95 para Roman y las sesiones hermanas. Nació como documento local; se publica
desde el 2026-10-07 junto a `docs/PLAN-GANAR-H2H.md`, que lo cita.

Sale de cuatro análisis gratuitos de hoy:

- **Anatomía**: coste y tiempo de 141 sesiones reales de Roman (2026-09-21 a 10-05). Está en
  `scratchpad/anatomy/` de la sesión c338a0be.
- **Escaneo externo**: afirmaciones de ahorro de otras librerías y cómo funciona el clasificador del
  modo auto.
- **Inventario**: los 27 mecanismos de sanchopanza y por qué salieron nulos.
- **Huecos de la línea browse**: los aportó indagis-a1.

Los techos de la tabla suponen que la intervención funciona perfecta y sin efectos secundarios.
**Se solapan, no se suman.**

## 1. Lo que dicen las sesiones reales

En 141 sesiones principales (125 con Opus 5.5) y 863 subagentes hay 14.900 $ de lista.

- **El 91 % del coste de las sesiones principales viene de peticiones con más de 200k de contexto.**
  - La mediana de contexto es 370k y el p90, 641k.
  - Se compactó 3 veces en dos semanas.
  - Cada petición relee el contexto entero a 0,1x, así que el 74-81 % del coste es lectura de caché.
- **El 31 % del coste son resultados de herramientas que se releen.** Un resultado típico se relee
  más de 50 veces, así que cada 1.000 tokens de salida acaban costando unos 0,05 $. Por herramienta:
  - `cat` y similares en la shell: 1.456 $;
  - `Read` de fichero entero: 721 $;
  - `ls`, `find` y `grep` en la shell: 591 $.
- **Los subagentes son el 41 % del gasto.**
  - Arrancan con 46k de prefijo.
  - Usan un TTL de caché de 5 minutos y esperan una mediana de 10 minutos entre peticiones, así
    que reescriben la caché: **1.128 $**.
- **Hay pasos mecánicos.** El 55 % de las peticiones son cortas y solo de herramienta, y todas van
  a Opus.
- **Fallos**: el 2,9 % de las llamadas fallan (533 $), y 1.017 de esos fallos acaban en un
  reintento casi idéntico.
- **Tiempo**:
  - El hook PostToolUse de code-review-graph se lleva **22,6 h**, a 2,5 s por llamada y con un 17 %
    de errores.
  - El guardián de Bash de la configuración de Roman, 15,5 h.
  - El modo auto denegó 100 veces, con una mediana de 24 s por denegación.

## 2. Lo que no era

- **El clasificador del modo auto no cuesta dinero en Claude Code.**
  - Va sobre Sonnet 5 y, desde la 2.1.278, se calcula dentro de la propia petición, gratis en API
    directa y en suscripción.
  - Un `allow` de PreToolUse **no** se lo salta (issue #94740). Solo lo evita una regla
    `permissions.allow`.
  - En Claude Code solo podría ganarse latencia, y no está medida. En Codex el revisor sí se cobra.
- **"Hasta un 40 % con Jev en Codex"** cuenta tokens de entrada, no dólares, y el 80-96 % ya iba
  por caché. Se midió en dos tareas, y con Opus 5 en tareas de feature empeoró: +61 % de tokens y
  +83 % de tiempo.
- **Comprimir sin más la salida de comandos** (rtk y parecidos) **salió más caro** cuando se midió
  de forma independiente: +7,6 % (JetBrains, p=0,004). El agente vuelve a pedir lo que le falta.

## 3. Por qué casi todo lo nuestro salió nulo (inventario)

1. N no era limpio. Con la configuración de Roman, la memoria nativa guardaba 0 de 48; con un
   usuario limpio, 12 de 24.
2. Casi todo se confirmó en Haiku, y el veredicto cambia entre modelos en unos 5 de 14 mecanismos.
3. Las tareas no tenían el fallo: browse 32/32, ataques 0/105, la memoria de Opus con 1 rotura de
   24.
4. Medíamos el acierto, cuando el valor estaba en el coste y el tiempo.
5. Las reglas de aprobación castigaban el efecto. Crawl perdió por precio aun acertando 19 frente
   a 12, y fetch1 falló la barra de 0,80 por 0,008.
6. Hubo bugs silenciosos que apagaban el tratamiento: sin Jev, sin mcp, herramienta diferida,
   delegación rota.
7. Pocas muestras (n de 1 a 12) para el ruido del coste (log-sd 0,48).
8. S se puntuó como un paquete y nunca contamos qué componente actuaba.
9. **Ninguna de nuestras tareas medidas se parece a una sesión real.** Las reales tienen 370k de
   contexto y 257 peticiones. Nuestras tandas nunca pasaron de 200k, salvo una sesión.

## 4. Huecos y apuestas, ordenados por techo medido

Coste base: 14.900 $ en dos semanas. "Hoy" es lo que hace sanchopanza; "Jev" es dónde decide.

| # | Hueco | Techo | Hoy | Apuesta (cómo y dónde) | Jev |
|---|---|---|---|---|---|
| 1 | Contexto que crece sin compactar (91 % del coste por encima de 200k) | ~17 % al podar resultados viejos con su punto de equilibrio; más si se compacta antes | `--context-budget 160000` + guardia (keep 6/7 en Haiku; una sesión: 30/40 frente a 27/40 a 0,837x) | Compactar antes, a ~160-200k, con la guardia eligiendo qué se queda y que el trabajo siga intacto. Hacerlo cuando la caché vaya a reescribirse de todos modos (tras una pausa mayor que el TTL, o en la compactación). Nunca por petición | Escoge qué se queda (keep o drop), qué es pista viva y qué es ruido |
| 2 | Salidas grandes la primera vez que entran (cat, ficheros enteros, logs; 31 % del coste en relecturas) | 11 % al recortar la shell a 1k; techo 22 % | Nada en la shell; `read`/`select_passages` en la web | Selección de pasajes al entrar: un PreToolUse reescribe la orden (`updatedInput`) para que la salida entera vaya a un fichero y al contexto llegue lo pertinente, según la intención que el agente acaba de escribir. Es gratis para la caché, porque actúa antes de que entre. Medir las re-ejecuciones (lo que mató a rtk) | Elige los pasajes (torneo de párrafos, 96,5 % con el 3,1 % del texto) |
| 3 | Pasos mecánicos en Opus (55 % de las peticiones) | 28 % si fueran a Haiku; 10 % a Sonnet | `route_task` (17/20 offline; la delegación se rompía 13/13 y está arreglada en 7a39a1f) | Delegar tandas de pasos mecánicos (ejecutar tests, buscar, aplicar un patrón) a un trabajador barato con su propia caché, que devuelve un resumen. Nunca se cambia el modelo del hilo principal | Decide si una subtarea es mecánica y a qué modelo va |
| 4 | Exploración antes de la primera edición (p50 9 peticiones, p90 30) | 10 %, 28 h | find / find_auto (Acc@1 51 % frente a 14 %; uso 2 de 78) | find_auto ya cableado; medir en sesiones largas reales, no en sueltas | Ordena los candidatos |
| 5 | Caché de los subagentes con TTL de 5 min | 6 % neto (877 $) | Nada | Configuración: TTL de 1 h solo en la petición anterior a una espera larga, o mantener la caché caliente. No es de Jev, pero es dinero directo | - |
| 6 | Fallos y reintentos | 3,6 % (237 $ evitables, 10-23 h) | check_loop (AUC 0,999 offline, nunca habló en vivo) | Aviso en PostToolUse tras el segundo fallo casi idéntico (no reescribe nada) | Decide si es un bucle |
| 7 | Prefijo fijo (skills, agentes y MCP listados) | 3 % (444 $); techo 2.775 $ | Nada | Cargar los listados bajo demanda; medir el prefijo del N limpio (21,5k) frente a Roman (85k) | - |
| 8 | Hooks lentos de Roman (code-review-graph 22,6 h con 17 % de errores; guardián de Bash 15,5 h) | ~38 h de pared | - | Hacerlos asíncronos, arreglarlos o quitarlos. Es configuración de Roman, no producto | - |
| 9 | Web: lectores Haiku de WebSearch y WebFetch (a1) | −32 % por sesión en Sonnet, −68 % en Haiku | knowledge (`search` 70-73 % frente a 44-48 %; `read` 62/66 frente a 22/66) | Ya en main (5da2635), entra en S1 | Torneo, `pick` |
| 10 | Seguridad (inyección, citas, desvíos, informes falsos) | Calidad, no ahorro | Escaneo 101/124 con 0/149 falsos positivos; candor; verificar_cita 19/20 | Medir en tareas que tengan el ataque o el error, no en tareas limpias | Clasificadores tipados |

## 5. Cómo medirlo bien esta vez

- **Tareas que se parezcan a las sesiones reales**: largas (más de 200k de contexto y 100 o más
  peticiones). Por ejemplo, cadenas de issues de un mismo repo, la "long40" de antes o
  Terminal-Bench largo.
- **Métrica principal: dólares por tarea resuelta** con la caché bien precificada (1 h a 2x),
  además del tiempo de pared. Victoria por Pareto, por modelo.
- **N limpio**, carpeta fuera de `C:\Users\roman`, Claude Code fijado; Sonnet 5.5 y Opus 5.5.
- **Primero el replay gratis sobre lo grabado** para estimar el techo real de cada apuesta (por
  ejemplo, simular compactar a 160k o 200k sobre las 141 sesiones); después, una tanda de
  desarrollo pequeña y, al final, el sello.
- **Contar cuántas veces actúa cada componente**, para que un S inerte no pase por neutro.

## 6. Orden propuesto

1. Replay gratis de las apuestas 1, 2 y 3 sobre las 141 sesiones (techo realista con la caché).
2. Implementar la apuesta 2 (selección al entrar, Bash y Read) y la 1 (compactación temprana con
   guardia) en una rama. Prueba en seco y revisión.
3. Tanda de desarrollo en sesiones largas, N frente a S, en Sonnet 5.5 y Opus 5.5, con techo de
   gasto declarado antes.
4. Lo que gane entra en S2, en otro sello.
5. Configuración de Roman, inmediata y sin producto: hooks lentos (8) y TTL de los subagentes (5).
