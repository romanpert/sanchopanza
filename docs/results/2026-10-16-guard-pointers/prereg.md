# Prerregistro: la guarda con punteros (P) frente a la guarda entera (F) en el banco largo (2026-10-16)

Escrito antes de cualquier corrida de esta tanda. Diseño A aprobado por el dueño el 2026-10-16
(cinco cadenas, margen −5, 250 $ duros más un humo de 8 $ duros, brazos sin clave). Lo revisó
contra el código un `revisor-prereg` independiente en dos pasadas; todo lo que pidió se aplicó
antes del sello (sección 16). Se sella como dice la sección 15 y
la tanda corre desde un `git worktree add --detach` en el commit de sello. `<SEAL>` es el commit
del instrumento, padre del de sello, y se nombra en el mensaje del commit de sello, no aquí.

## 1. Pregunta

Desde w17-lean (merge da005a9, en main c3313a3), la guarda de compactación de `sanchopanza install`
adjunta tras cada compactación las peticiones literales, los ficheros cambiados y **punteros** a
las salidas anteriores (las que no se pueden repetir, archivadas y enmascaradas junto al proyecto
para leerlas con `Read`), en vez de reinyectar los resultados enteros (bloque `struct` de 6 partes,
mediana de 49.473 caracteres; `install --guard-full` lo devuelve).

- **Lo que ya se sabe, gratis** (replay de las 10 sesiones long60 de Claude Code limpio, 98
  compactaciones, commit bc2a0ac): el coste de arrastrar el bloque baja de 1,17 a 0,18 $ por sesión
  Ne y de 1,97 a 0,36 por sesión Nl (tarifas de Sonnet 5.5); el agente volvió a pedir algo que el
  bloque entero habría tenido en 13 de 100 compactaciones, ~0,002 $ por compactación frente a los
  0,16 del bloque. Sobre una sesión Ne de ~17-19 $, el cociente esperado P/F es ~0,94.
- **Lo que no se sabe y decide esta tanda: la calidad.** ¿Resuelve el agente menos bugs cuando los
  cuerpos de las salidas solo se apuntan?

Si P es no inferior, el valor por defecto se queda (pointers). Si P resuelve menos ("peor"), el
dueño decide si el defecto vuelve a `struct`. El coste no decide aquí (sección 8).

## 2. Brazos

Los dos son la instalación que un usuario hace en su proyecto, `sanchopanza install --scope project
--write`, desde la copia congelada del commit sellado (`freeze.py <SEAL>`), con hooks y servidor por
`hook_env.py` (estado por sesión en la carpeta de evidencia). Solo cambia la guarda:

| Brazo | Código | Flags de `install` | Guarda tras compactar |
|---|---|---|---|
| **P** (el defecto) | `long_run.arm_spec("P")` | ninguno | `pointers`: peticiones, ficheros cambiados, punteros; lo irrepetible archivado en `<proyecto>/.sanchopanza/archive/<sesión>/guard-*.txt` |
| **F** (guarda entera) | `long_run.arm_spec("F")` | `--guard-full` | `struct`: los resultados enteros, con un presupuesto de 44.000 caracteres para ellos (`structural.STRUCT_CHARS`; el bloque entero tuvo una mediana de 49.473 en el replay) en 6 partes (`SANCHOPANZA_GUARD_CHOOSER=struct`) |

- Lo demás es el defecto en los dos (comprobado en seco, sección 14): el guardia de shell (perfil
  `coding`), memoria (registra y devuelve por código), `find_in_repo` diferido tras la búsqueda de
  herramientas de Claude Code, la skill `sanchopanza-code`, y `--context-budget` 160.000 (ventana
  193.000: compacta cerca de 160k, como Ne en el cierre).
- **Sin clave de decisor en ningún brazo** (`Profile.keyless`): el runner escribe un fichero de
  clave vacío, sin leer ninguna clave; los hooks construyen el decisor nulo (`NullDecider`,
  comprobado antes de la primera llamada), no hay `jev-preflight` ni gasto de Jev. Motivo: la
  guarda, en sus dos variantes, no pregunta a ningún modelo; Jev solo añadiría gasto, el riesgo de
  402 y ruido igual en los dos brazos. **Límite declarado** (aprobado por el dueño): lo que tiene un
  usuario con clave (memoria con decisor) queda fuera (sección 13). Las decisiones que los hooks
  anotan sin preguntar a ningún modelo (proveedores `code`, el guardia de shell, y `budget`) no
  cuentan como pagadas.
- **El archivo de P va donde lo pone la instalación**, dentro de la copia de trabajo del agente: el
  runner no lo desvía a la evidencia (`hook_env`, `ADOPT_GUARD_LOT=1`), porque la guarda le dice al
  agente que lo lea en esa ruta. `.sanchopanza/` se ignora a sí misma y queda fuera del diff
  (`docker_env.agent_diff`).
- La memoria guarda su almacén por brazo y sesión (`SANCHOPANZA_MEMORY_STORE` en la evidencia): no
  hay arrastre entre brazos.
- **Comprobaciones en vivo que paran la tanda** (fichero `STOP`, en cada llamada de P o F):
  - **la guarda de su brazo**: cada compactación tiene su bloque construido en el PreCompact, con
    el elegido del brazo (`pointers` en P, `struct` en F), leído del propio log de la guarda
    (`<evidencia>/guard.jsonl`, `long_pointers.guard_breaks`). Una compactación sin bloque, o con
    el elegido del otro brazo, para;
  - **la ventana**: una compactación con `pre` fuera de 120.000-185.000 o una llamada con más de
    203.000 de contexto (`long_pointers.window_breaks`). Ne compactó en el cierre entre 159.643 y
    162.755;
  - **sin pagos**: cualquier decisión respondida por un proveedor que no sea el nulo, `code` o
    `budget` (`long_pointers.keyless_breaks`);
  - **el mismo prefijo**: la primera petición de P y la de F, a ±50 tokens (`prefix_breaks`),
    comprobado en la PRIMERA llamada del segundo brazo de cada cadena (`long_run.first_call_breaks`),
    no al acabar los dos;
  - lo de siempre: init (versión 2.1.287, modelo, modo de permisos, sin clave de API), el servidor
    `sanchopanza` conectado o, por estar diferido, `pending` en el init (`Expect.deferred`); un
    `failed` o ausente para; diff que desaparece; errores de hooks por encima del 5 %.
- **Llamada cortada a media tanda (se carga y se sigue).** Una llamada que el runner corta
  (tiempo, flujo parado, el proceso muerto) se carga a su tope de 4,50 $, como en todas las tandas
  largas. Si no hizo nada (ninguna herramienta, el mismo diff) se repite una vez; si hizo algo, el
  brazo sigue en la petición siguiente como desviación declarada (`long_guard.resume_decision`
  "continue": las cinco cadenas son de los repartos `gate`, `dev` y `reserve`). "Set aside" solo
  existe para cadenas `held`, así que aquí no puede pasar. Las llamadas cortadas, repetidas y
  apartadas se publican por brazo y cadena (`long_pointers_read.cuts`).
- **Guarda que falla (se cuenta, no para).** Cuando la guarda falla construye el bloque de la regla
  (peticiones y rastro, sin punteros ni resultados) y lo marca: `pointers (archive failed: rule
  only)` en P (no pudo escribir el archivo) y `struct (error: rule only)` en F (excepción al
  construir). Las dos pasan la comprobación de arriba porque empiezan por el elegido de su brazo.
  **Decisión**: una compactación con la guarda fallida no para la tanda (la instalación falla
  abierta igual en el campo y eso es parte de lo que se mide); se cuentan y se publican por brazo y
  cadena (`long_pointers_read.carry`: `failed` y `choosers`). Si en algún brazo fallan más de 1 de
  cada 10 de sus compactaciones, se dice al lado del veredicto, que no cambia.
- **Qué pasa si una comprobación salta** (como en el cierre, sección 2 de su prereg): la tanda
  queda parada con `STOP` y se mira a mano.
  - Si el tratamiento no es el registrado (una compactación sin la guarda de su brazo, otro
    elegido, la ventana que no tomó, un prefijo distinto, una decisión pagada), la tanda queda
    parada y decide el dueño; esa cadena no se lee (`long_pointers_read.paused`: un brazo parado
    por `harness`, `limit` o `ceiling`, o con fila parcial, deja la cadena sin puntuar y la tanda
    "sin veredicto" mientras siga así).
  - Si fue un fallo del arnés que no toca al tratamiento (p. ej. Docker, disco, un init con el
    servidor diferido aún arrancando que no esté previsto), se anota como desviación, se quita el
    `STOP` y se reanuda desde el mismo worktree (`long_resume`: lo acabado no se repite, la llamada
    a medias se carga a su tope). La cadena se lee entera solo cuando sus dos brazos acabaron (por
    su final, su tope o su pared).
  - Una cadena que no puede acabar se excluye y se dice; con menos de cinco no hay veredicto.
## 3. Cadenas

Las cinco cadenas long60 válidas con manifiesto, en el orden del cierre: **conan-1, pydantic-1,
conan-2, moto-1, moto-2** (`long_run.GUARDPTR_CHAINS`). conan-3 y dvc-1 no son válidas. Las cinco
completas (60 bugs y 2 *callbacks*, 62 peticiones).

## 4. Diseño

- **Modelo**: Sonnet 5.5 (`claude-sonnet-5-5`), Claude Code 2.1.287 fijado (`claude-pin`,
  `DISABLE_AUTOUPDATER=1`).
- **k = 1 por brazo y cadena; la unidad es la corrida** (el par de corridas de una cadena). Los dos
  brazos de una cadena corren seguidos, el mismo día, en el orden de `long_run.arm_order` (rotación
  por el sha256 del nombre): P primero en conan-1 y moto-1; F primero en pydantic-1, conan-2 y
  moto-2.
- Usuario limpio y caché aislada por brazo (`CLAUDE_CONFIG_DIR` propio por cadena y brazo,
  `carry.clean_config`), copia de trabajo nueva por brazo, raíz `C:\sp-runs\L-guardptr` nueva.
- No se reutiliza ninguna corrida anterior.
- **La caché de prompts del servidor es compartida** entre los dos brazos de una cadena: corren
  seguidos con el mismo prefijo (mismo usuario de la suscripción), así que el segundo brazo puede
  leer de caché lo que escribió el primero. P va segundo en tres cadenas (pydantic-1, conan-2,
  moto-2) y F en dos. Es otra razón por la que el coste es solo descriptivo; la calidad no depende
  de ello.
## 5. Topes y gasto

- Dólares del dueño a precio de lista (`meter.OWNER_RATES`), de cada transcripción; corre con la
  suscripción.
- **4,50 $ por llamada, 25 $ por corrida, 250 $ de techo duro en el código** (`GUARDPTR_CEILING`,
  `hard_cap`: ninguna línea de comandos lo sube; 5 × 2 × 25 = 250, retenidos antes de la primera
  llamada). `--max-budget-usd` solo corta entre turnos: una llamada empieza solo si caben su tope y
  un turno más (el peor, contexto en la ventana de 193k: 1,64 $), así que **ninguna corrida empieza
  llamadas pasados 18,86 $**.
- **Estimación**: Ne en el cierre (misma ventana, sin instalación) gastó 15,08-19,27 $ por corrida
  entera; dos de sus cinco corridas pararon por el tope (y las dos de la repetición de conan-2). Con la instalación (memoria +12 % en su
  celda) y el bloque de F, casi todas las corridas acabarán en su tope (~19-20,5 $) y pydantic en
  ~17-18: **~185-200 $ esperados**; el modelo de coste (sin topes) da 171 $; **máximo 250 $, por
  código**. Más el humo (sección 12, ≤ 8 $ duros, raíz propia): **≤ 258 $ en total**.
- Una corrida parada por su tope compara en las llamadas comunes; sigue el brazo siguiente
  (`local_stops = ("cap", "wall")`).
- **La copia congelada es el paquete sellado**: antes de la primera llamada, cada
  `src/sanchopanza/**/*.py` del manifiesto tiene que estar en su `site-packages` con el mismo
  sha256 (`guardptr_seal.frozen_refusal`), y `pip freeze` de `mcp`, `httpx` y `sanchopanza` queda
  en `launch.log`.
- **Aprobado por el dueño** el 2026-10-16: diseño A, 250 $ duros más el humo (8 $ duros).

## 6. Medidas

Lectura: `benchmarks/adopt/long_pointers_read.py` (`grade` con Docker, `read`, gratis), sobre
`long_compact.chain_line` con el par (P, F).

- **Llamadas comunes**: de la 1 a la última que corrieron los dos brazos. Una cadena cuenta con
  **≥ 30 llamadas comunes** y la nota común de los dos brazos, y **solo con sus dos filas
  finales**: un brazo pausado (`stopped` en `limit`, `harness` o `ceiling`) o con fila parcial deja
  la cadena sin puntuar (`chains_paused`) y la tanda sin veredicto mientras dure (sección 2).
- **Principal: bugs resueltos.** Cada brazo puntuado en su instantánea tras la última llamada común
  (`diff-<k>.patch`, `perbug.grade`), sobre los bugs pedidos a los dos. **Todas las cadenas con un
  tiempo de 300 s por test** (`TEST_TIMEOUT`, fijado aquí, antes de los datos: en el cierre la nota
  de moto se colgó sin él). P − F en tasa de resueltos:
  - remuestreo de cadenas enteras (`long_report.cluster_bootstrap`, 10.000 réplicas, semilla
    20261005), con su cota unilateral al 95 % (`one_sided_low`) y su IC bilateral al 95 %;
  - **y** la cota unilateral al 95 % de la t sobre la media de las diferencias por cadena (`t_low`,
    gl = cadenas − 1).
  - **Dos estimandos, declarados**: el bootstrap estima la diferencia **agrupada por bugs** (cada
    bug común pesa igual, así que una cadena con más llamadas comunes pesa más); la t, la **media
    sin pesos de las cadenas** (cada cadena pesa igual). Con 43-60 bugs comunes por cadena casi
    coinciden; si no, se publican las dos.
- **La regla compara las cotas sin redondear**; se redondean a 4 decimales solo al publicar
  (`published`).
- **Secundaria, descriptiva: el coste P/F** en las llamadas comunes (`long_report.cost_ratio`: media
  pareada de ln(P/F), IC 95 % de la t), con su nombre ("más barato demostrado", "sin diferencia
  demostrada", "más caro demostrado"). No entra en el veredicto (sección 8).
- **Mecanismo, descriptivo, de las transcripciones** (`mechanism`): por brazo y cadena,
  compactaciones; lecturas de un `guard-*.txt` archivado (con `Read` o `cat`/`head`/`tail`/`sed
  -n`); comandos de antes de la compactación repetidos y ficheros de antes releídos en las 20
  peticiones siguientes a cada compactación. **Arrastre** (`carry`, del log de la guarda): bloques,
  sus caracteres (mediana), salidas archivadas, elegidos y **guardas fallidas** (sección 2). Con esto
  se compara en vivo lo que dijo el replay (49k frente a ~8k caracteres por compactación; 13 de 100
  re-peticiones).
- Se publican además: compactaciones y su `pre`, contexto pico, abandonos no resueltos, coste por
  bug resuelto, cómo acabó cada corrida, la nota final de cada brazo (`grade --final`) y los
  *callbacks*.

## 7. Regla de decisión (fijada aquí; `long_pointers_read.RULE` y `verdict`)

Margen de no inferioridad: **−5 puntos** de tasa de resueltos (3 bugs de 60 por cadena). **Por qué
−5:** P ahorra ~6 % del coste de una sesión; con ~90 % de resueltos (Ne en el cierre: 253 de 278 en
las llamadas comunes), perder más de ~5 puntos haría
el coste por bug resuelto de P peor que el de F. Un margen mayor dejaría pasar una pérdida que el
ahorro no paga.

| Calidad P − F | Veredicto |
|---|---|
| las dos cotas unilaterales (bootstrap y t) por encima de −5 pts, IC bilateral del bootstrap con su extremo alto ≥ 0 | **no inferior** |
| las dos cotas por encima de −5 pts, IC bilateral entero por debajo de 0 | **no inferior, con una pérdida menor demostrada** |
| no inferior no, IC bilateral entero por debajo de 0 | **peor** |
| ninguna de las anteriores | **no demostrado** |
| menos de 5 cadenas con ≥ 30 llamadas comunes y nota común, o alguna cadena pausada o parcial | **sin veredicto** |

- **Por qué las dos cotas**: con 5 cadenas el bootstrap por cadenas es liberal: si P pierde de
  verdad 5 puntos, dice "no inferior" en un 9-14 % de las tandas (simulado); la t, en un 4-7 %.
  Exigir las dos deja el error cerca del 5 % nominal. **En la simulación la exigencia del bootstrap
  no muerde nunca**: "las dos" da lo mismo que la t sola en todas las filas de 5 cadenas (y difiere
  en 0,001 en dos filas de 10 pares). La regla es, en la práctica, la cota t; el bootstrap se exige
  igual y se publica.
- "No demostrado" no se lee como "pierde": se publica la estimación y su intervalo y decide el
  dueño. "Peor" lo lleva el dueño (¿volver a `struct` por defecto?).
- Nada de esto cambia después de ver datos. Si algo resulta inaplicable, se dice y se publica la
  tabla sin veredicto.

## 8. Potencia (simulada con la regla de arriba; `benchmarks/adopt/guardptr_power.py`, `power.json`)

Modelo: en cada par, cada bug es discordante (lo resuelve un brazo y el otro no) con probabilidad
`d`, y un discordante cae del lado de P con 1/2 + Δ/(2d); τ es la dispersión del efecto entre pares
(una corrida que se tuerce entera). 1.000 tandas simuladas, 1.000 remuestreos.

- **d observado**: 0,068 entre Ne y Nl del cierre, el mismo día y seguidos (6 pares; la
  desviación de la diferencia por cadena, 3,0 pts, corresponde a d ≈ 0,05-0,07); 0,02-0,15 entre
  réplicas del mismo brazo en días distintos (sin el conan-1 de Ne del 7 de octubre, que perdió 19-22 bugs
  frente a las demás corridas, todos del mismo lado: una corrida torcida, eso es τ).

Probabilidad de "no inferior" (las dos cotas), 5 cadenas, el diseño registrado. **Lo esperable son
~45 bugs comunes por cadena, no 60**: la sección 5 prevé que casi todas las corridas acaben en su
tope, y en el cierre las cadenas tuvieron 43-60 bugs comunes. La columna de 45 es la que se espera;
la de 60, el techo.

| d | Δ real | τ | −5, 45 bugs | −5, 60 bugs | −7, 45 bugs | −7, 60 bugs |
|---|---|---|---|---|---|---|
| 0,07 | 0 | 0 | **0,75** | 0,85 | 0,93 | 0,97 |
| 0,07 | −2 pts | 0 | 0,44 | 0,49 | 0,75 | 0,84 |
| 0,07 | 0 | 2 pts | 0,67 | 0,73 | 0,91 | 0,94 |
| 0,07 | 0 | 5 pts | 0,47 | 0,50 | 0,72 | 0,76 |
| 0,12 | 0 | 0 | 0,59 | 0,66 | 0,81 | 0,86 |
| 0,20 | 0 | 0 | 0,41 | 0,52 | 0,62 | 0,71 |
| d ≥ margen | = margen | 0 | 0,06 | 0,05 | 0,04-0,07 | 0,05-0,06 (error de tipo I) |

- **Coste**: con 5 cadenas, un cociente real de 0,94 se demostraría (IC entero bajo 1) en un 11 %
  de las tandas con la desviación del log de 0,171 y en un 18 % con 0,10. Hacen falta ~60 cadenas
  (0,171) o ~21 (0,10) para verlo al 80 %. **Por eso el coste no decide**: la cifra del ahorro es la
  del replay (mecánica), y esta tanda la comprueba en el mecanismo (bloques y re-peticiones
  medidos), no en el total.

## 9. Lo que cuesta decidir, y la alternativa más barata

- **~70 $ no deciden.** Con 70 $ caben dos cadenas completas (cuatro corridas): dos grupos no dan
  intervalo. Cinco cadenas de 20 bugs (~60 $) tendrían una compactación por corrida (pydantic,
  ninguna) y una potencia por debajo de 0,5 a −5 puntos.
- **El diseño registrado (A), el que aprobó el dueño**: 5 cadenas × 60 bugs, ~185-200 $
  esperados, 250 duros; potencia 0,75 con ~45 bugs comunes (0,85 si las cadenas llegan enteras),
  con d = 0,07.
- **Alternativa (B), no elegida** (queda en el código, perfil `guardptr-30`, sin uso): las 30 primeras peticiones de bug
  de cada cadena (perfil `guardptr-30`, 32 peticiones, 18 $ por corrida, 180 duros; Ne gastó
  6,89-12,82 $ en esas peticiones: **~110-120 $ esperados**). Una o dos compactaciones por corrida.
  Con el margen −5 su potencia cae a 0,61 (d = 0,07); con **−7** sube a 0,86, pero −7 deja pasar
  una pérdida mayor que lo que P ahorra.
- Diez grupos de 30 bugs (5 cadenas × 2 pares) dan 0,92 a −5 con d = 0,07, por ~220-230 $: más
  caro que A por poco más potencia. No se propone.

## 10. Paradas

- **429, límite de uso o aviso de límite**: `C:\sp-runs\LIMIT.flag` (lo ven todos los runners
  largos), NOT RUN para el resto del brazo, salida 2. **Es una pausa, nunca un resultado**: sin
  reintentos en bucle; reanudar lo decide el dueño y se avisa a las demás sesiones al primer 429.
- `STOP` en la raíz (a mano o por un invariante de la sección 2), Docker caído, disco por debajo de
  30 GB: para la tanda.
- Tope de corrida o pared (4 h): para ese brazo; sigue el siguiente. Techo: para la tanda.
- **Reloj**: una cadena (los dos brazos, `hours` 1,7 por brazo: 3,4 h) no empieza si cruzaría la
  medianoche (`midnight_refusal`) ni entre las 00:00 y las 08:00 (`quiet_refusal`: Windows Update
  reinicia entre 02:00 y 08:00; el cierre perdió una llamada a las 05:04) ni con un reinicio
  pendiente de Windows (`RebootRequired`, `RebootPending`): el lanzador lo mira al empezar y el
  runner **antes de cada cadena** (`restart_refusal`), porque una actualización puede llegar a
  media tanda. Y **antes de cada llamada**, si la hora ya está entre las 00:00 y las 08:00 (una
  cadena empezada a las 20:36 con brazos de 4 h podría llegar), el brazo se pausa con `clock`
  (salida 2, reanudable: `long_resume.RESUMES`); la cadena no se puntúa mientras siga pausada, y
  un relanzamiento pasadas las 08:00 sigue desde ahí. Se anota como desviación.
- **El dueño o el coordinador vigila hasta que acaba la última cadena** (dos monitores: líneas del
  log y PID vivo); la tanda no se deja sola.
- Matar solo por PID verificado (`long_run.py kill --root C:\sp-runs\L-guardptr`).
- Vigilancia en vivo: `long-run.status.json`, `runner-sonnet.log` y `launch.log` en la raíz, y el PID
  vivo (dos monitores).

## 11. Horario

- Pared por corrida de Ne en el cierre: 0,71-1,55 h (media ~1,0); con los hooks de la instalación,
  ~1,1 h. **Por cadena, los dos brazos: ~2,2 h (1,5-3,2). Las cinco: ~11 h (8-16).**
- **Lanzamiento a las 08:05** de un día con la máquina atendida. Con ~2,2 h por cadena acaba hacia
  las 19:30 del mismo día. Si las cadenas van lentas, la regla de medianoche deja sin empezar la
  quinta (no empieza pasadas ~20:36) y el runner sale; se relanza al día siguiente a las 08:05 desde
  el mismo worktree (reanuda: lo acabado no se repite).
- Vigilada hasta el final de la última cadena (sección 10).
- Después, la nota (Docker, gratis; ~10-20 min por brazo): `long_pointers_read.py grade --final`.

## 12. Humo (antes de la tanda; perfil `guardptr-smoke`)

- Haiku 4.5, 3 bugs de pydantic-1 (5 peticiones con los *callbacks*), los dos brazos con
  `--context-budget 67000` para que compacten en una sesión corta (ventana 100.000; el humo del
  2026-10-07 compactó dos veces en la segunda llamada). 1 $ por llamada, 4 por corrida, **8 $
  duros**; raíz `C:\sp-runs\L-guardptr-smoke`. **Esperado: ~2-5 $**, ~30 min. Mismo commit
  sellado, misma copia congelada, mismo lanzador (`guard-pointers-run.cmd <SEAL> smoke`). F corre
  primero en pydantic-1 (`arm_order`); un tope de F no impide P (`local_stops` = tope y pared).
- Debe mostrar, leído a mano antes de la tanda: que el init pasa con `find_in_repo` diferido (y qué
  estado da: `connected` o `pending`); que cada compactación de P lleva `pointers` y la de F
  `struct` en `guard.jsonl` y en la fila; que P escribe sus `guard-*.txt` dentro de la copia de
  trabajo y fuera del diff; `NullDecider` y ninguna decisión pagada; errores de hooks por debajo
  del 5 %; la nota con el tiempo por test. Si algo falla, no hay tanda: se arregla con test y se
  vuelve a sellar.
- El humo no entra en ninguna cuenta del veredicto.

## 13. Lo que esta tanda no dice (escrito antes de los datos)

- **Sin clave**: el dueño con `TYPESAFE_API_KEY` tiene además memoria con decisor. Ninguna de las
  dos guardas pregunta a un modelo, pero la memoria con decisor podría cambiar lo que el agente
  tiene tras compactar en los dos brazos.
- **Ventana del defecto (160k)**: ~4 compactaciones por cadena completa (2 en pydantic). Con un
  presupuesto menor habría más compactaciones y más ocasiones de perder algo; no se mide aquí.
- k = 1 por cadena: la calidad de una corrida concreta varía mucho (una corrida torcida, τ, se
  come la potencia: 0,50 con τ = 5 pts). Solo vale el agregado.
- Cuatro repositorios (conan ×2, pydantic, moto ×2); bugs de SWE-smith, no el código del dueño.
- Sonnet 5.5 solo; Opus 5.5 no se corre.
- **No son datos nuevos para la hipótesis**: las cinco cadenas son las mismas sobre las que se hizo
  el replay que motivó el cambio (las 10 sesiones long60 de Claude Code limpio). Lo nuevo es medir
  la calidad en vivo con los dos brazos; el ahorro de coste no se confirma aquí en datos nuevos.

## 14. Comprobado en seco (gratis, antes del sello)

- `long_launch.py plan guardptr`: 250 retenidos, techo 250 duro, ventana 193.000, "ninguna llamada
  pasados 18,86".
- `tests/test_adopt_long_pointers.py` (brazos, perfiles, invariantes, lectura y regla) y
  `tests/test_adopt_long_pointers_launch.py`: el lanzador entero por `cmd.exe` en seco, con un
  `claude` de mentira que **ejecuta los hooks de guarda reales de la instalación** en cada
  compactación inyectada: P construye `pointers` y F `struct` en las cinco cadenas, sin parar; una
  compactación a 67.500 en la ventana de 193k para la tanda; el humo en Haiku compacta y construye
  la guarda de cada brazo.
- `install --scope project --write` y `--guard-full` en un repositorio vacío difieren en tres cosas
  y en nada más: el PreCompact de la guarda lleva `--parts 6`; SessionStart (compact) tiene 6
  comandos (`--part 1..6 --parts 6`) en vez de 1; y el `env` lleva `SANCHOPANZA_GUARD_CHOOSER=struct`
  y `SANCHOPANZA_GUARD_CHOOSER_BY=sanchopanza`.
- El sello en código (`tests/test_adopt_guardptr_seal.py`): en un repositorio sellado de prueba el
  lanzador rellenado, por `cmd.exe`, pasa la comprobación, escribe HEAD en `launch.status` y corre
  el humo en seco; una copia cambiada más allá de sus valores locales, un árbol sucio, un commit
  posterior al sello, un commit de sello que toca otra cosa o una copia congelada que no es el
  padre se niegan antes de cualquier llamada.

## 15. Lanzamiento y sello

1. **Instrumento**: el commit con este fichero y todo el código es `<SEAL>`.
2. **Sello** (`benchmarks/adopt/guardptr_seal.py seal`): escribe `prereg.manifest.json` y
   `prereg.sha256` (sha256 sobre este fichero, cada fichero del instrumento, `SEALED`, las fuentes
   del paquete y el lanzador con sus valores locales como marcadores). El commit de sello es hijo
   único de `<SEAL>`, añade esos dos ficheros y nada más, y nombra `<SEAL>` en su mensaje.
3. **En código, antes de gastar** (`long_launch.py` → `guardptr_seal.require_seal`, y otra vez
   el runner, `long_run.seal_refusal`, así que `long_run.py run --profile guardptr` solo se niega):
   HEAD es el commit de sello (el último que tocó `prereg.sha256`, un solo padre, solo los ficheros
   del sello), el árbol está limpio, el sello coincide, la copia del lanzador que corrió
   (`ADOPT_LAUNCHER`, que pone el propio lanzador; un nombre que ningún filtro de entorno quita) es
   la sellada salvo sus valores locales, y el `<SEAL>` dado es el padre de HEAD. HEAD queda en
   `launch.status` y en `launch.log`. **Qué se sella** (`guardptr_seal.sealed`): lo que la tanda
   ejecuta y todos los módulos del repositorio que eso importa, arriba o dentro de una función,
   por nombre o por cadena (`_optional`), sacados de su código (`imports_closure`; un test lo
   contrasta con lo que Python carga de verdad); los manifiestos de las cinco cadenas,
   `power.json`, `pyproject.toml` y todo `src/`.
4. Gratis: `python benchmarks\adopt\freeze.py <SEAL>`; `long_launch.py plan guardptr`; los tests de
   la sección 14; Docker arriba, sin `LIMIT.flag`, sin reinicio pendiente; preguntar qué otras
   sesiones gastan suscripción (límite semanal compartido).
5. `git worktree add --detach ..\sanchopanza-guardptr <commit de sello>`; copiar
   `guard-pointers-run.cmd` a la raíz de la tanda y rellenar allí **`PY`, `SANCHOPANZA_KEYS_ENV` y
   `WT`** (el fichero seguido solo lleva marcadores). `SANCHOPANZA_KEYS_ENV` nombra el `.env` que
   guarda `CLAUDE_CODE_OAUTH_TOKEN`, el token de la suscripción: un lanzamiento por WMI no recibe
   variables de la ventana. El lanzador real se niega con el marcador sin rellenar; el token se lee
   dentro del proceso y nunca se imprime (probado en seco con un fichero de claves falso nombrado
   en la copia, sin el token en el entorno).
6. Humo: la copia rellenada con `<SEAL> smoke` por WMI (`Win32_Process.Create`, `CreateFlags
   512`); leerlo a mano (sección 12).
7. Tanda: la copia rellenada con `<SEAL>`, por WMI, a las 08:05; PIDs en `launch.json`; avisar a
   las demás sesiones (PID, hora, tope).
8. Al acabar: `long_pointers_read.py grade --final` y `long_pointers_read.py read --json
   docs/results/2026-10-16-guard-pointers/read.json`; cada fallo y cada número favorable, a mano.

## 16. Revisión independiente (antes del sello)

`revisor-prereg`, sobre 85c58ee: nada bloqueante. Lo que pidió y lo que se hizo, antes de cualquier
dato:

1. **Sello en código** como los lotes hermanos: `guardptr_seal.py` y la comprobación en
   `long_launch.py` (sección 15), con test por la entrada real (`cmd.exe`).
2. **No puntuar cadenas pausadas o parciales**: `long_pointers_read.paused`; qué pasa si salta una
   comprobación (sección 2).
3. **Potencia con los bugs comunes esperados** (~45) y que "las dos" es la t (sección 8).
4. **Guardas fallidas** de P y de F: declaradas, contadas y publicadas; no paran (sección 2).
5. Además: `code` y `budget` no son decisiones pagadas; el prefijo, en la primera llamada del
   segundo brazo; las tres diferencias de la instalación (sección 14); el presupuesto de `struct`
   frente a la mediana del bloque (sección 2); el humo corre P aunque F llegue a su tope; la caché
   de prompts compartida (sección 4); vigilancia hasta la última cadena y reinicio pendiente antes
   de cada cadena (sección 10); las cadenas son las del replay (sección 13); los dos estimandos
   (sección 6); el lanzador seguido sin rutas locales y con fin de línea CRLF
   (`.gitattributes`).

Segunda pasada, sobre 89dcfce: un bloqueo y tres "debe", más "conviene":

1. **Bloqueo: el token no llegaba al runner** por el camino real. El lanzador lleva ahora
   `set "SANCHOPANZA_KEYS_ENV=<KEYS_ENV_PATH>"`, se niega sin rellenarlo, y el sello lo lee como
   valor local; test por `cmd.exe` con el token solo en el fichero de claves.
2. **Lo sellado se saca de las importaciones** (faltaban `masking`, `related`, `chains`,
   `carry_s`, `rules`, `scenes*`, ficheros no Python de `src/` y `pyproject.toml`), con un test que
   falla si un módulo importado no está sellado.
3. **Llamadas cortadas** declaradas (sección 2) y publicadas por brazo.
4. Además: la regla con cotas sin redondear; el prefijo en la primera llamada que corrió; la copia
   congelada contrastada con el manifiesto y `pip freeze` en el log; el runner comprueba el sello
   él mismo; la hora también antes de cada llamada (`clock`).

## 17. Enmienda 1 (2026-10-17, antes de cualquier dato de la tanda)

Escrita y sellada antes de que corra ninguna llamada de la tanda (el humo de la sección 12 corrió
con el sello anterior, `510a5c6`; la tanda no ha corrido nunca: `C:\sp-runs\L-guardptr` no
existe). Sustituye al sello de `510a5c6` (instrumento `8341b6c`): el sello nuevo es hijo único del
commit de instrumento que lleva esta sección y la 18. Cambia tres cosas; los brazos, cadenas,
medidas, regla, potencia y topes (secciones 2-9) no cambian.

1. **Escrituras que sobreviven a un apagado sucio.** El 16 a las 22:37 la máquina se cayó (evento
   41) con otra tanda en marcha y su fichero de filas quedó a ceros: se escribía con un temporal y
   `os.replace` sin `fsync`. Este instrumento tenía el mismo patrón en `arm_files.write_row`
   (`row.json`, del que la tanda se reanuda y se cobra). Entra el arreglo de main (`88f5400`,
   aquí `b42c1d9`, idéntico): `sanchopanza.durable` (fsync antes del rename, fsync por línea
   añadida) en `arm_files.write_row` y los demás escritores de estado de `benchmarks/`. Además,
   aquí pasan por `durable.replace_text`: `diff-<k>.patch` y `final.patch` (el runner se reanuda
   desde `diff-<k>.patch` y la nota sale de ellos), `long-run.status.json` y `launch.json` (los
   lee `busy()` al relanzar). Test: `tests/test_durable.py`. Los bytes escritos son los mismos.
   **Lo instalado en P y en F** (todo `src/`, sellado) cambia solo en cómo escriben
   `SpendLedger`, el cortacircuitos de fondos y `episodes.write_private` (memoria y el estado de
   los hooks de fetch, crawl y sources): con fsync, mismos bytes. La tanda es sin clave de Jev
   (`keyless`), así que los dos primeros no se usan. El guard escribe con `hookio.write_private`,
   que no cambia: el tratamiento es el mismo. Ningún prompt, hook ni salida del modelo cambia.
   Siguen sin fsync, y tras un evento 41 se miran a mano (bytes NUL) antes de reanudar:
   `hooks.jsonl`, `guard.jsonl`, `journal.jsonl` y el archivo `guard-*.txt` de P.
2. **Horas quietas levantadas con Windows Update en pausa (condicional).** La regla de la sección
   10 (ninguna cadena empieza ni ninguna llamada se hace entre 00:00 y 08:00, `quiet_refusal`)
   existe solo porque Windows Update reinicia la máquina de 02:00 a 08:00. Se levanta **solo si**
   las actualizaciones están pausadas al menos 24 h más allá de cada comprobación
   (`benchmarks/memory_carry/winupdate.py`): el final más temprano entre
   `PauseUpdatesExpiryTime` y `PauseQualityUpdatesEndTime` de
   `HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings`, y además `PausedQualityStatus = 1` en
   `...\UpdatePolicy\Settings`. Sin pausa, con un valor ilegible o sin la bandera, la regla
   sigue. Se comprueba donde antes: antes de cada cadena y antes de cada llamada; si la pausa se
   acaba a media tanda, la regla vuelve sola. El runner anota en `runner-sonnet.log` cada cadena
   o llamada que pasa entre 00:00 y 08:00 gracias a la pausa ("quiet hours lifted", "call in the
   quiet hours", con la fecha de fin; `long_start.quiet_lift_note`), y se publica como
   desviación del horario. **No cambian** la regla de medianoche al empezar cada cadena ni la del
   reinicio pendiente (antes de cada cadena). Con la pausa, un brazo empezado antes de las 00:00
   que la cruce sigue en vez de pausarse con `clock` (la fecha del prompt cambia a media
   corrida): se declara si pasa. A las 08:21 del 17 la pausa **no** estaba puesta
   (`quiet_lifted()` vacío), así que la tanda se lanza de día por las reglas de la sección 10, y
   esta parte solo actúa si se pone la pausa y la tanda llega a la noche. Antes de apoyarse en
   ella de noche, se comprueba en vivo que `quiet_lifted()` no sale vacío con la pausa puesta.
3. **Humo otra vez** (sección 12), con el sello nuevo, la copia congelada nueva y una copia nueva
   del lanzador seguido rellenada (`PY`, `SANCHOPANZA_KEYS_ENV`, `WT` al worktree nuevo), antes
   de la tanda: tope duro 8 USD (esperado 2-5). Antes, la raíz del humo del 16
   (`C:\sp-runs\L-guardptr-smoke`, HEAD 510a5c6, 1,77 USD) se renombra a
   `C:\sp-runs\L-guardptr-smoke-510a5c6` (no se borra), porque el runner salta los brazos
   acabados. Se lee a mano lo de la sección 12, más que `launch.status` lleva el HEAD nuevo y que
   corrieron las 5 llamadas. **Gasto del lote**: 1,77 ya gastados + 8 + 250 = **259,77 USD como
   mucho** (antes 258); el dueño autorizó el 17 de madrugada los gastos de estos puntos.

## 18. Revisión independiente de la enmienda 1 (antes del sello)

`revisor-prereg`, sobre `3beac36` (delta desde `510a5c6`): ningún bloqueo; cinco "debe", todos
hechos antes del sello:

1. El humo nuevo no habría corrido nada (raíz con brazos acabados): se renombra la raíz (17.3).
2. El sobre de gasto pasaba de 258 a 259,77 USD: dicho en la 17.3.
3. La pausa no estaba puesta: la 17.2 la escribe como condición, con comprobación en vivo antes
   de apoyarse en ella.
4. El log anotaba un levantamiento en cada cadena aunque fuera de día, y ninguno por llamada:
   `quiet_lift_note` anota solo entre 00:00 y 08:00, en la cadena y en la llamada, con test.
5. Procedimiento del resello: la copia del lanzador se rehace desde el fichero seguido (cambió un
   comentario); el commit de instrumento quita `prereg.sha256` y `prereg.manifest.json` (el
   `seal` se niega con el valor viejo dentro; el original, `8341b6c`, tampoco los tenía); el sello
   es hijo único del commit que lleva las secciones 17 y 18.

"Conviene" hechos: la bandera `PausedQualityStatus`; fsync en `launch.json` y
`long-run.status.json`; `tests/test_winupdate.py` y `tests/test_durable.py` sellados
(`guardptr_seal.ENTRIES`); la 17.1 precisa qué escribe con fsync y qué no; el cruce de medianoche
con la pausa, declarado. No hecho: un reinicio pendiente antes de cada llamada (hoy antes de cada
cadena); con las horas activas 8-2, Windows no reinicia de día, y de noche solo se corre con la
pausa. El worktree del sello viejo (`..\sanchopanza-run-gptr`) no se usa; la copia nueva del
lanzador vive solo en las raíces nuevas.
