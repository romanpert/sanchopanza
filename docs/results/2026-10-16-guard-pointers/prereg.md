# Prerregistro: la guarda con punteros (P) frente a la guarda entera (F) en el banco largo (2026-10-16)

Borrador para sellar. Escrito antes de cualquier corrida de esta tanda. Lo revisa contra el código
un `revisor-prereg` independiente; después se sella con su commit y su sha256 (sección 15) y la
tanda corre desde un `git worktree add --detach` en ese commit. Los marcadores `<SEAL>` se rellenan
al sellar.

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
| **F** (guarda entera) | `long_run.arm_spec("F")` | `--guard-full` | `struct`: los resultados enteros, hasta 44.000 caracteres en 6 partes (`SANCHOPANZA_GUARD_CHOOSER=struct`) |

- Lo demás es el defecto en los dos (comprobado en seco, sección 14): el guardia de shell (perfil
  `coding`), memoria (registra y devuelve por código), `find_in_repo` diferido tras la búsqueda de
  herramientas de Claude Code, la skill `sanchopanza-code`, y `--context-budget` 160.000 (ventana
  193.000: compacta cerca de 160k, como Ne en el cierre).
- **Sin clave de decisor en ningún brazo** (`Profile.keyless`): el runner escribe un fichero de
  clave vacío, sin leer ninguna clave; los hooks construyen el decisor nulo (`NullDecider`,
  comprobado antes de la primera llamada), no hay `jev-preflight` ni gasto de Jev. Motivo: la
  guarda, en sus dos variantes, no pregunta a ningún modelo; Jev solo añadiría gasto, el riesgo de
  402 y ruido igual en los dos brazos. Lo que el dueño tiene con clave (memoria con decisor) queda
  fuera (sección 13).
- **El archivo de P va donde lo pone la instalación**, dentro de la copia de trabajo del agente: el
  runner no lo desvía a la evidencia (`hook_env`, `ADOPT_GUARD_LOT=1`), porque la guarda le dice al
  agente que lo lea en esa ruta. `.sanchopanza/` se ignora a sí misma y queda fuera del diff
  (`docker_env.agent_diff`).
- La memoria guarda su almacén por brazo y sesión (`SANCHOPANZA_MEMORY_STORE` en la evidencia): no
  hay arrastre entre brazos.
- **Comprobaciones en vivo que paran la tanda** (fichero `STOP`, en cada llamada de P o F):
  - **la guarda de su brazo**: cada compactación tiene su bloque construido en el PreCompact, con
    el elegido del brazo (`pointers` en P, `struct` en F), leído del propio log de la guarda
    (`<evidencia>/guard.jsonl`, `long_pointers.guard_breaks`). Un `pointers (archive failed: rule
    only)` se anota, no para;
  - **la ventana**: una compactación con `pre` fuera de 120.000-185.000 o una llamada con más de
    203.000 de contexto (`long_pointers.window_breaks`). Ne compactó en el cierre entre 159.643 y
    162.755;
  - **sin pagos**: cualquier decisión respondida por un proveedor que no sea el nulo
    (`long_pointers.keyless_breaks`);
  - **el mismo prefijo**: la primera petición de P y la de F, a ±50 tokens (`prefix_breaks`);
  - lo de siempre: init (versión 2.1.287, modelo, modo de permisos, sin clave de API), el servidor
    `sanchopanza` conectado o, por estar diferido, `pending` en el init (`Expect.deferred`); un
    `failed` o ausente para; diff que desaparece; errores de hooks por encima del 5 %.

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
- **Por encima de 70 $: lo aprueba el dueño** (sección 9).

## 6. Medidas

Lectura: `benchmarks/adopt/long_pointers_read.py` (`grade` con Docker, `read`, gratis), sobre
`long_compact.chain_line` con el par (P, F).

- **Llamadas comunes**: de la 1 a la última que corrieron los dos brazos. Una cadena cuenta con
  **≥ 30 llamadas comunes** y la nota común de los dos brazos.
- **Principal: bugs resueltos.** Cada brazo puntuado en su instantánea tras la última llamada común
  (`diff-<k>.patch`, `perbug.grade`), sobre los bugs pedidos a los dos. **Todas las cadenas con un
  tiempo de 300 s por test** (`TEST_TIMEOUT`, fijado aquí, antes de los datos: en el cierre la nota
  de moto se colgó sin él). P − F en tasa de resueltos:
  - remuestreo de cadenas enteras (`long_report.cluster_bootstrap`, 10.000 réplicas, semilla
    20261005), con su cota unilateral al 95 % (`one_sided_low`) y su IC bilateral al 95 %;
  - **y** la cota unilateral al 95 % de la t sobre la media de las diferencias por cadena (`t_low`,
    gl = cadenas − 1).
- **Secundaria, descriptiva: el coste P/F** en las llamadas comunes (`long_report.cost_ratio`: media
  pareada de ln(P/F), IC 95 % de la t), con su nombre ("más barato demostrado", "sin diferencia
  demostrada", "más caro demostrado"). No entra en el veredicto (sección 8).
- **Mecanismo, descriptivo, de las transcripciones** (`mechanism`): por brazo y cadena,
  compactaciones; lecturas de un `guard-*.txt` archivado (con `Read` o `cat`/`head`/`tail`/`sed
  -n`); comandos de antes de la compactación repetidos y ficheros de antes releídos en las 20
  peticiones siguientes a cada compactación. **Arrastre** (`carry`, del log de la guarda): bloques,
  sus caracteres (mediana), salidas archivadas, elegidos. Con esto se compara en vivo lo que dijo el
  replay (49k frente a ~8k caracteres por compactación; 13 de 100 re-peticiones).
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
| menos de 5 cadenas con ≥ 30 llamadas comunes y nota común | **sin veredicto** |

- **Por qué las dos cotas**: con 5 cadenas el bootstrap por cadenas es liberal: si P pierde de
  verdad 5 puntos, dice "no inferior" en un 9-14 % de las tandas (simulado); la t, en un 5-7 %.
  Exigir las dos deja el error cerca del 5 % nominal.
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

Probabilidad de "no inferior" (las dos cotas), 5 cadenas de 60 bugs, el diseño registrado:

| d | Δ real | τ | margen −5 | margen −7 |
|---|---|---|---|---|
| 0,07 | 0 | 0 | **0,85** | 0,97 |
| 0,07 | −2 pts | 0 | 0,49 | 0,84 |
| 0,07 | 0 | 2 pts | 0,73 | 0,94 |
| 0,07 | 0 | 5 pts | 0,50 | 0,76 |
| 0,12 | 0 | 0 | 0,66 | 0,86 |
| 0,20 | 0 | 0 | 0,52 | 0,71 |
| d ≥ margen | = margen | 0 | 0,05 | 0,05-0,06 (error de tipo I) |

- **Coste**: con 5 cadenas, un cociente real de 0,94 se demostraría (IC entero bajo 1) en un 11 %
  de las tandas con la desviación del log de 0,171 y en un 18 % con 0,10. Hacen falta ~60 cadenas
  (0,171) o ~21 (0,10) para verlo al 80 %. **Por eso el coste no decide**: la cifra del ahorro es la
  del replay (mecánica), y esta tanda la comprueba en el mecanismo (bloques y re-peticiones
  medidos), no en el total.

## 9. Lo que cuesta decidir, y la alternativa más barata

- **~70 $ no deciden.** Con 70 $ caben dos cadenas completas (cuatro corridas): dos grupos no dan
  intervalo. Cinco cadenas de 20 bugs (~60 $) tendrían una compactación por corrida (pydantic,
  ninguna) y una potencia por debajo de 0,5 a −5 puntos.
- **El diseño registrado (A)**: 5 cadenas × 60 bugs, ~185-200 $ esperados, 250 duros; potencia
  0,85 con d = 0,07.
- **Alternativa (B), solo si el dueño la elige antes del sello**: las 30 primeras peticiones de bug
  de cada cadena (perfil `guardptr-30`, 32 peticiones, 18 $ por corrida, 180 duros; Ne gastó
  6,89-12,82 $ en esas peticiones: **~110-120 $ esperados**). Una o dos compactaciones por corrida.
  Con el margen −5 su potencia cae a 0,61 (d = 0,07); con **−7** sube a 0,86, pero −7 deja pasar
  una pérdida mayor que lo que P ahorra. Si se elige B, se cambian aquí el perfil, el margen
  (`MARGINS["guardptr-30"]` = 0,07), el mínimo de llamadas comunes (20) y la sección 11, antes de
  sellar.
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
  reinicia entre 02:00 y 08:00; el cierre perdió una llamada a las 05:04). El lanzador se niega si
  Windows tiene un reinicio pendiente (`RebootRequired`, `RebootPending`).
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
- Después, la nota (Docker, gratis; ~10-20 min por brazo): `long_pointers_read.py grade --final`.

## 12. Humo (antes de la tanda; perfil `guardptr-smoke`)

- Haiku 4.5, 3 bugs de pydantic-1 (5 peticiones con los *callbacks*), los dos brazos con
  `--context-budget 67000` para que compacten en una sesión corta (ventana 100.000; el humo del
  2026-10-07 compactó dos veces en la segunda llamada). 1 $ por llamada, 4 por corrida, **8 $
  duros**; raíz `C:\sp-runs\L-guardptr-smoke`. **Esperado: ~2-5 $**, ~30 min. Mismo commit
  sellado, misma copia congelada, mismo lanzador (`guard-pointers-run.cmd <SEAL> smoke`).
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

## 14. Comprobado en seco (gratis, antes del sello)

- `long_launch.py plan guardptr`: 250 retenidos, techo 250 duro, ventana 193.000, "ninguna llamada
  pasados 18,86".
- `tests/test_adopt_long_pointers.py` (brazos, perfiles, invariantes, lectura y regla) y
  `tests/test_adopt_long_pointers_launch.py`: el lanzador entero por `cmd.exe` en seco, con un
  `claude` de mentira que **ejecuta los hooks de guarda reales de la instalación** en cada
  compactación inyectada: P construye `pointers` y F `struct` en las cinco cadenas, sin parar; una
  compactación a 67.500 en la ventana de 193k para la tanda; el humo en Haiku compacta y construye
  la guarda de cada brazo.
- `install --scope project --write` y `--guard-full` en un repositorio vacío: difieren solo en
  `SANCHOPANZA_GUARD_CHOOSER=struct` (con su marca) y los 6 comandos de SessionStart.

## 15. Lanzamiento y sello

1. Sello: commit del instrumento, sha256 de este fichero y de `guard-pointers-run.cmd` en el
   mensaje; `<SEAL>` = ese commit. Revisión independiente (`revisor-prereg`) antes; lo que
   encuentre se arregla y se vuelve a sellar antes de cualquier dato.
2. Gratis: `python benchmarks\adopt\freeze.py <SEAL>`; `long_launch.py plan guardptr`; los tests de
   la sección 14; Docker arriba, sin `LIMIT.flag`, sin reinicio pendiente; preguntar qué otras
   sesiones gastan suscripción (límite semanal compartido).
3. Humo: `git worktree add --detach ..\sanchopanza-guardptr <SEAL>`; `guard-pointers-run.cmd <SEAL>
   smoke` por WMI (`Win32_Process.Create`, `CreateFlags 512`); leerlo a mano (sección 12).
4. Tanda: `guard-pointers-run.cmd <SEAL>` por WMI desde el mismo worktree, a las 08:05; PIDs en
   `launch.json`; avisar a las demás sesiones (PID, hora, tope).
5. Al acabar: `long_pointers_read.py grade --final` y `long_pointers_read.py read --json
   docs/results/2026-10-16-guard-pointers/read.json`; cada fallo y cada número favorable, a mano.

- Commit sellado: `<SEAL>`. sha256 de este fichero: `<SHA256>`. Revisión: `<REVISOR>`.
