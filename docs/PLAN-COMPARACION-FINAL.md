# Plan de la comparación final: Claude Code solo frente a Claude Code + sanchopanza

Documento local, 2026-10-05. Para Roman y para las sesiones 95 (memoria y contexto), 8f (adopción y código) y a1 (navegación y búsqueda web). Lo que no se ha medido lleva **[sin medir]**.

## Objetivo

Roman (2026-10-05): una última vuelta de mejora y las pruebas finales, Claude Code solo frente a Claude Code + sanchopanza, en memoria, contexto, precio, rapidez, capacidad y potencia para resolver: dónde ganamos algo y dónde no ganamos nada.

## 1. Brazos y modelos (acordado hoy)

| Brazo | Definición | Referencia |
|---|---|---|
| **N** | Claude Code limpio: `CLAUDE_CONFIG_DIR` vacío por par, sin plugins, skills, MCP, hooks ni CLAUDE.md de Roman; salida fuera de `C:\Users\roman` (la búsqueda hacia arriba carga `~/.claude/CLAUDE.md` y `rules\`) | `--clean-user` y `refuse_unclean` de `benchmarks/memory_carry/carry.py`, rama memoria-f1 (ad0471c, 8e9dc68). a1 y 8f los copian |
| **S** | Lo que `sanchopanza install` deja por defecto en main tras la fusión de browse (en curso hoy), sellado **una sola vez**. Los hooks de browse (crawl, prune, sources, fetch) son opt-in y **no** van en el defecto salvo que se decida | por fijar tras la fusión |
| **S+X** (opcional) | Una variante opt-in candidata por suite, p. ej. S+find-auto (87611e1, 50f605b) | solo si su sonda sale bien |

- Modelos: **Sonnet 5.5 y Opus 5.5**; **Fable 5.1** si el presupuesto lo permite (propuesta de a1, para que el resultado no nazca viejo). Haiku solo para estudiar mecanismos (memoria `confirmar-en-modelos-frontera.md`).
- Claude Code fijado a **2.1.287** (como en `prereg-f1-gate.md`, decisión 2).
- **Las tandas en curso de 8f no cuentan para el marcador final.** La fase D (sello f422cea0) y la sonda find_auto cargan la configuración de Roman en los dos brazos, como declara su sello, y corren en Claude Code 2.1.285 y Haiku 4.5. Valen para lo que sellaron.

- **N limpio en todas las suites** con `--clean-user` / `refuse_unclean` de `carry.py` (memoria), y la carpeta de cada tarea fuera de `C:/Users/roman`.
- **Duda abierta:** confirmar que `--setting-sources ""` evita cargar `~/.claude/CLAUDE.md` **[sin comprobar]**.

Por qué N limpio: hasta hoy las tandas carry cargaban 5 MCP, 21 plugins, 119 skills y 5 hooks de Roman (`prereg-f1-correctness.md`, sección Arms).

## 2. Método común para comparar y cerrar

Es el estándar del campo (AI Agents That Matter, arXiv 2407.01502; HAL, arXiv 2510.11977; barras de error, arXiv 2411.00640), en la versión que propuso a1:

1. **Ablación pura.** Mismo modelo, Claude Code 2.1.287 fijado, mismas tareas, S frente a N y nada más. Brazos intercalados por tarea y caché aislada por brazo (la primera sesión de cada fase paga la escritura de caché: `sanchopanza-label-browse-2026-09-30.md`).
2. **Corrector oficial** de cada benchmark. Donde el automático no llegue, nota a mano **a ciegas**: hoja barajada sin brazo y clave aparte que el corrector no abre.
3. **Métricas.** Las principales son el éxito y el coste total de lista por tarea, con Jev incluido. Además se informan el coste por éxito, los turnos, el tiempo de pared y los tokens por tipo (entrada, salida, lectura y escritura de caché).
4. **Victoria = dominancia de Pareto, por modelo y nunca agregada entre modelos.** Hay dos maneras de ganar:
   - coste con IC95 que excluye 0 y éxito no peor que un margen de no inferioridad fijado antes, **−2 puntos**;
   - éxito mejor, con IC, sin perder en coste.
5. **Estadística emparejada.** McNemar exacto sobre los discordantes y bootstrap emparejado por tarea, agrupado.
6. **Repeticiones y potencia.**
   - k ≥ 3 tiradas solo donde mande la varianza (pass^k): el coste del mismo brazo varía con una desviación típica de 0,48 en logaritmo (`docs/results/2026-10-03-adopt-d/prereg.md`, línea 52). Si no, más tareas a k = 1: en pares por tarea da más potencia por dólar.
   - Tareas con éxito histórico del 30 al 70 %, elegidas solo por metadatos o por un dev separado, con un conjunto reservado.
   - Primero una prueba de margen: si N no falla, la celda es "sin margen" y no se compara.
7. **Sello y lanzamiento.**
   - registro previo sellado (sha256 y commit) **antes de la primera sesión**, verificado contra el código por un subagente independiente;
   - preflight gratis;
   - lanzamiento fuera de sesión por WMI con CreateFlags 512;
   - techo duro en el código y STOP-LIMIT ante un 429 o el límite semanal.
8. **Lectura.** Cada fallo y cada número favorable se leen a mano. Los fallos de proceso van a commit y chat, no al README.

## 3. Suites por línea

### Código (sesión 8f)

- **Banco:** SWE-bench Verified, sueltas nuevas. Sin usar quedan **133 de 500**: las 500 de `swe-eval/verified-rows.json` menos las 300 de `benchmarks/adopt_d/used-ids.json`, las 26 de D y sus 31 reservas (`singles-d.json`), las 79 de `find_need/need-table.json` y las 28 de las sondas dev. Por repositorio: django 93, sympy 22, sphinx 7, matplotlib 7 y scikit-learn 4 (contado hoy, sin leer notas de D).
- **Brazos:** N limpio frente a S por defecto; S+find-auto solo si su sonda sale bien.
- **Ejes:** capacidad (instancias resueltas), precio (coste de lista por instancia) y rapidez (pared y turnos).
- **Ya en main:** 7a39a1f (arreglo de la delegación), f7bbdbb (find solo sobre fuente), 87611e1 y 50f605b (find_auto opt-in). Comprobado con `git merge-base --is-ancestor`. Browse ya está fusionado en main: 0a7eab9 (browse-nav), 0a7d80a (browse-dev) y d34d8ec (browse-v6). D no lo nota, porque corre su copia congelada de 7a39a1f.
- **Lo medido en Haiku, solo como dirección:** sueltas de la fase A, S 17 frente a N 16 y coste S/N 1,084 [0,842; 1,158] (`docs/results/2026-09-30-adopt/dev-log.md`); find llamado 0/10 con visible 10/10 (03753f1).
- **D y las sondas de find no tienen un N limpio.** Los dos brazos cargan `~/.claude/CLAUDE.md` y `~/.claude/rules/*.md` de Roman. Lo declara el prerregistro de D ("Inputs no seal covers", línea 588) y lo registra su `D INPUTS` con hashes. Además corren en Claude Code 2.1.285 y no en 2.1.287. La comparación final cambia eso: N limpio por par, y S limpio salvo lo que pone `install`.

**Coste por sesión, medido** (solo campos de coste de `row.json`; ningún `grade.json` de D):

| Modelo | Fuente | Sesiones | $ por sesión (media / mediana) | Turnos | $ por turno | Pared por sesión |
|---|---|---|---|---|---|---|
| Haiku 4.5 | Fase A, sueltas Verified (`adopt/singles`) | 90 (N 32, S 58) | 0,486 / 0,433 (N 0,471, S 0,495) | 51-53 | 0,0093 | 240-270 s |
| Haiku 4.5 | Fase D hasta las 19:14 (`singles-d`, 16 de 26 instancias) | 96 (48 + 48) | 0,475 / 0,463 (N 0,471, S 0,479); máx. 1,43 | 48 | 0,0098 | N 327 s, S 363 s |
| Haiku 4.5 | Sondas dev-alwaysload / dev-nudge | 14 / 20 | 0,406 / 0,514 | 45-54 | 0,009-0,010 | 210-250 s |
| Haiku 4.5 | dev-need / dev-auto (solo S, instancias de búsqueda difícil; dev-auto en curso, 7 filas) | 10 / 7 | 0,698 / 0,734 | 73 | 0,0095-0,0100 | 470 s |
| Sonnet 5.5 | Fase B, `starlette-long-1r1` (10 peticiones SWE-smith en una sesión) | 2 × 10 peticiones | N 0,097 y Sm 0,093 por petición | 5,4 por petición | 0,018 | 71-96 s por petición |
| Sonnet 5.5 | Fase B2, `pydantic-long40-1` (40 peticiones) | 3 × 40 peticiones | N 0,219, S 0,183 y Sm 0,159 por petición | 5,7-7,3 por petición | N 0,039, S 0,028, Sm 0,022 (contexto de hasta 263k) | 59-86 s por petición |
| Sonnet 5.5 | memory-carry (repos pequeños, no SWE-bench; `~/.cache/sanchopanza/memory-carry`) | 416 | 0,189 / 0,188 | 6,5 | 0,029 | 35 s |
| Opus 5.5 | memory-carry (lo único grabado de Opus 5.5) | 64 | 0,359 / 0,344 | 4,4 | 0,082 | 59 s |

- **Ninguna sesión de Sonnet 5.5 ni de Opus 5.5 sobre Verified.** find-e2e es Haiku y solo localiza (0,11 $, 20 turnos). candor corrió con Sonnet 5, no 5.5, sobre tareas sintéticas. No son comparables.
- **Mismos bugs, Haiku frente a Sonnet.** starlette-1 + starlette-rel-1, brazo N; rel-1 cambia un bug, pr_2041 por pr_2443. Haiku 4.5 costó 3,22 $ en 222 turnos y Sonnet 5.5, 0,972 $ en 54. Sonnet sale a **0,30× el coste**, 0,24× los turnos y 1,24× el $ por turno. Son bugs SWE-smith fáciles.
- **Mismas 32 escenas de memory-carry.** Sonnet/Haiku **2,12×**, Opus/Sonnet **1,87×** y Opus/Haiku **3,97×**. En pared, Sonnet va a 0,45× de Haiku y Opus a 0,79×.
- **Precios de lista, USD por MTok (entrada / salida):**
  - Haiku 4.5: 1 / 5. Opus 5.5: 5 / 25. Fable 5.1: 10 / 50. Lectura de caché ×0,10 y escritura ×1,25 (5 min) o ×2 (1 h). Fuente: `benchmarks/meter.py`, `PRICES`, "checked against the vendor's model table on 2026-09-24".
  - Sonnet 5.5: no está en `meter.py`, que solo tiene `claude-sonnet-5` a 2 / 10. `src/sanchopanza/harness/sources_v2.py` da "sonnet" a 2 / 10, con escritura de 1 h a 4 y lectura a 0,2. Esa tarifa reproduce exacto el `costUSD` que Claude Code registra en las filas de B2: 158,64 + 6,14 M de escritura × 1,5 = 167,85.

**Estimación por sesión en Verified [no medido].**

- Base: Haiku 0,48 $ por sesión, la media de A y D.
- Sonnet 5.5: de **0,145 $** (×0,30, mismos bugs) a **1,02 $** (×2,12, memory-carry).
- Opus 5.5: de **0,27 $** (×0,30 × 1,87) a **1,91 $** (×3,97).
- El presupuesto toma el extremo alto: las dos referencias se contradicen y ninguna es Verified.
- Tope por sesión propuesto [no medido]: 3,20 $ en Sonnet y 6,00 $ en Opus. Es el máximo de Haiku, 1,51 $, escalado igual. D usaba 1,50 $.

**Diseños.** Siguiendo el estándar común, se ofrecen 26×3 o más instancias a k=1; el 26×2 queda fuera. Sesiones = instancias × repeticiones × 2 brazos. El tope es 1,3× el estimado alto; el suelo es el extremo bajo.

| Diseño | Sesiones | Sonnet 5.5: estimado (tope) / suelo | Opus 5.5: estimado (tope) / suelo | Potencia H1, 1 %, margen 2/26 | Tipo I en el margen |
|---|---|---|---|---|---|
| 26×3 | 156 | 159 $ (207) / 23 $ | 298 $ (387) / 42 $ | 0,842 | 0,041 |
| 26×1 | 52 | 53 $ (69) / 8 $ | 99 $ (129) / 14 $ | 0,630 | **0,083** (> 5 %) |
| 52×1 | 104 | 106 $ (138) / 15 $ | 198 $ (258) / 28 $ | 0,789 | 0,041 |
| **78×1** | 156 | **159 $ (207) / 23 $** | **298 $ (387) / 42 $** | **0,891** | 0,037 |
| 133×1 (todas las libres) | 266 | 271 $ (352) / 39 $ | 507 $ (660) / 72 $ | 0,976 | 0,022 |

- Con S+find-auto se suma un brazo: +50 % de sesiones y de coste en cada fila.
- **Pared.**
  - D, medido: 96 sesiones en 5 h 24 min (13:50 a 19:14), 6 a la vez, unos 20 min por instancia. De ellos, 4-8 min de sesiones, unos 5 min para corregir 3 repeticiones y el resto para preparar la imagen.
  - 26×3 ≈ **8,8 h**. Las sesiones de Sonnet y Opus serán algo más cortas: en pared van a 0,45-0,54× y 0,79× de Haiku.
  - k=1 [no medido]: hay una pareja y una corrección por imagen, unos 14 min por instancia si se corren una a una. Eso da 52×1 ≈ 12 h, 78×1 ≈ 18 h y 133×1 ≈ 31 h. Con tres instancias a la vez (6 sesiones, como D), un tercio: unas 4, 6 y 10 h.

**Potencia** (`sim_h1.py` generalizado a n×k, en el scratchpad de esta sesión; gratis, semilla 20261005, 4.000 estudios).

- **Perfil de resolución:** el de las sueltas de la fase A, con media 0,654. Reproduce el 26×3 del prerregistro de D: 0,842 / 0,041 frente a 0,838 / 0,044.
- **Por qué k=1 con más tareas:** las dos lecturas de S de la fase A discrepan en 1 de 26 instancias, así que una repetición añade poca información.
  - **78×1 domina a 26×3.** Tiene las mismas sesiones y el mismo coste, más potencia (0,891 frente a 0,842) y menos error de tipo I.
  - **52×1 es el mínimo que merece pagarse** (0,789).
  - **26×1 no merece la pena:** el bootstrap al 1 % deja pasar en el margen el 8,3 % de los estudios.
- **Margen de −2 puntos (0,02) en vez de −2/26.** No hay diseño asequible: la potencia en igualdad queda en 0,21-0,51 desde 26×3 hasta 133×1. A 26×1 sale 0,63, pero es degenerada (todas las diferencias son 0) y deja un tipo I de 0,38. Un margen de −2 puntos pide cientos de instancias, y solo quedan 133.
- **McNemar exacto (k=1, bilateral al 5 %; potencia para ver que S resuelve más):**
  - S +5 puntos: 0,06 con 52, 0,20 con 78 y 0,43 con 133.
  - S +10 puntos: 0,38, 0,66 y 0,93.
  - Solo ve efectos grandes: ganar en éxito solo se puede afirmar con unas 133 instancias y +10 puntos.
- **Coste** (`power.py`: sd de ln(S/N) pareado de 0,381 en las sueltas de A). La semiamplitud del IC95 sobre la media es ×1,158 con 26×1, ×1,109 con 52×1, ×1,088 con 78×1 y con 26×3 (optimista), y ×1,067 con 133×1. Basta para ver una diferencia de coste del 10 % desde 78×1.
- **Límites:**
  - El perfil es de Haiku. Sonnet y Opus resuelven más Verified [no medido], lo que deja menos pares discordantes y menos margen. La prueba de margen va primero.
  - El tipo I depende de la forma del daño, como dice el prerregistro de D.

**Propuesta para Roman:**

| Opción | Diseño | Estimado | Tope | Pared |
|---|---|---|---|---|
| Recomendada | Sonnet 5.5 a 78×1 | 159 $ | 207 $ | 6-18 h |
| Recomendada | Opus 5.5 a 52×1 | 198 $ | 258 $ | 4-12 h |
| Recomendada, juntas | Sonnet 78×1 + Opus 52×1 | 357 $ de lista | 465 $ | — |
| Más barata, aceptable | Las dos a 52×1 | 304 $ | — | — |

- Que S resuelva más no se podrá afirmar con ninguna de estas opciones. Lo que se decide es la no inferioridad al margen de D y el coste.
- Antes de lanzar se presenta la estimación y Roman la aprueba.

### Web y búsqueda (sesión a1)

- **GAIA validation.** Roman aceptó el gate el 2026-10-05. Aún no hay gasto.
  - Preparado en el worktree `sanchopanza-h2h`, rama h2h, commit c37d691, carpeta `benchmarks/h2h/`: corrector oficial reproducido caso por caso, revisión a mano de los dudosos, runner reanudable con topes por sesión (Fable 6 $, Opus 3 $, Sonnet 1,5 $, Haiku 0,75 $), denegaciones anti-fuga en todas las herramientas y Bash permitido.
  - 165 tareas: L1 53, L2 86, L3 26; 127 sin adjunto. Las 10 de vídeo se excluyen: quedan **155**.
  - **Ejes:** capacidad (éxito oficial), precio y rapidez; también lectura grande (adjuntos pdf/xlsx/docx) y búsqueda.
  - **Diseño propuesto:** antes, un dev de 20 tareas en Sonnet 5.5 (sorteadas con semilla entre las 155) solo para comprobar el brazo S de punta a punta; no se ajusta ningún umbral con él y esas 20 **salen** de la confirmación. Confirmación: las **135** restantes × 1 tirada × 2 brazos (S, N), en Sonnet 5.5 y Opus 5.5; Fable 5.1 opcional. GAIA no trae éxito histórico por tarea: se usan todas las que quedan, sin filtro del 30-70 %, y se dice así.
- **FRAMES, confirmación fetch1, en curso.**
  - Fetch por pasajes v2, sellada en `docs/results/2026-10-05-browse-frames/prereg-fetch1.md` (rama browse-dev, 8388b66, sha a9712121...).
  - 60 tareas nuevas y 240 sesiones en Haiku y Sonnet 5. Coste esperado ~38 $, con techo de 55 $ en el código; fin hacia las 21:30 del 2026-10-05.
  - **Ojo:** fetch1 compara "Claude Code + fetch-mcp" contra Claude Code, **no** el S por defecto, y sin constancia de N limpio. Cuenta como mecanismo, no como el marcador S−N.
- **Crawl:** las confirmaciones 3, 4 y 5 fallan por precio; respuestas y no-daño aguantan (conf 5, Haiku 19 frente a 12; `HANDOFF-2026-10-05-browse.md`).
- **Decidido por Roman (2026-10-05):** criterio de victoria = el estándar general de la sección 2 (Pareto por modelo, margen de no inferioridad −2 puntos), igual en todas las suites; el coste por respuesta correcta se reporta como métrica, no decide. Nada de API de búsqueda de pago: la búsqueda se facilita con opciones opensource y sin cuenta (en estudio en la línea browse).

### Memoria (sesión 95)

1. **Prueba de margen F1, sellada en c4b853c y aprobada.**
   - Solo N limpio, 24 escenas en tres familias (principios, regla caducada, sesión paralela), Sonnet y luego Opus.
   - Una familia pasa si N rompe el hecho, con la tarea hecha, en al menos 3 de 8 escenas (`prereg-f1-gate.md`).
   - **No lanzada aún:** no existe `C:\sp-runs\memory-carry\f1-gate-run.status`.
2. **F1 completa, N frente a S**, solo en las celdas que abra la prueba de margen. S va en v8.2 (84cdd49: sustitución de reglas y almacén por repo). Hasta 221,8 $ si se abren las seis celdas (`prereg-f1-correctness.md`). Es un borrador.
3. **F2, traspasos:** ~180,5 $ (`prereg-f2-handoff.md`). Es un borrador. Se apoya en que el 61 % de las sesiones reales de Opus 5.5 abren con un traspaso pegado; ahí está el margen real (memoria `confirmar-en-modelos-frontera.md`).
- **Ya se sabe:** carry v6.2 confirmado en Sonnet 5.5 (23/24 frente a N 14/24, p 0,002) y sin margen en Opus 5.5 (16/16 frente a 14/16) (`docs/results/2026-10-02-memory-carry/README.md`).

### Contexto (sesión 95)

**Lo medido:**

| Mecanismo | Resultado | Fuente |
|---|---|---|
| Guardia de compactación | Tareas terminadas: nativo 2/7, regla 5/7, cascada keep 6/7; McNemar p 0,375; Haiku | `docs/results/2026-09-29-context-guard/README.md` |
| Enmascarado ligero (autopilot) | El 12/12 quedó retirado por un bug; rehecho: nativo 5/7, ligero 3/7, borrar 0/6 | `docs/results/2026-09-28-context-lean/` |
| Predecir con Jev qué hará falta | Va al azar, AUC 0,53-0,61 | `docs/results/2026-09-28-context/` |
| Presupuesto 160k, simulado | Releer cuesta un 42 % de lo actual en sesiones reales de 300k-400k con ventana de 1M | `2026-09-30-adopt/dev-log.md`, "Where the context goes" |
| Presupuesto 160k, en vivo | Haiku compacta a 161,7k y 160,6k (cadenas); Sonnet llega a un pico de 80k y no compacta | dev-log, tablas del piloto y de la fase B |
| Compactar al empezar cada petición | 46 %, pero `session.compact()` no resuelve en `claude -p` 2.1.285 | dev-log, sección de compactación |

**Lo que falta:** nada en modelos frontera; el presupuesto nunca se midió en vivo en sesiones de más de 200k, donde está el gasto; la guardia solo tiene 7 tareas en Haiku.

**Suite corta propuesta [sin medir, sin presupuesto]:**

- **Tareas:** sesiones largas que lleven a N por encima de 200k de contexto, como cadenas de 10 o más bugs o tareas de exploración amplia. La prueba de margen va primero: si N no pasa de 160k ni compacta, la celda es "sin margen".
- **Brazos:** N limpio, S por defecto (guardia + presupuesto 160k) y un brazo de **delegación** (ver la sección 6).
- **Métricas:**
  - tokens de contexto por turno (pico y mediana);
  - compactaciones;
  - tarea completada tras compactar, con un hecho de control releíble;
  - coste total con subagentes;
  - tiempo de pared.
- **Modelos:** Sonnet 5.5 y Opus 5.5.

### Sesiones largas (sesión 95, añadida el 2026-10-05 por la noche, de acuerdo con la sesión a1)

`MAPA-HUECOS-ARNES.md` muestra que el dinero real está aquí. En 141 sesiones reales, el 91 % del
coste sale de peticiones con más de 200k de contexto; la mediana es de 370k y hubo 3
compactaciones en dos semanas. Ninguna de nuestras tandas se parecía a eso.

- **Tareas:** sesiones de más de 200k de contexto y 100 peticiones o más, como cadenas de issues de
  un mismo repo o exploración y edición amplia. Antes, una prueba de margen: N tiene que pasar de
  200k.
- **Brazos:** N limpio frente a S. Las apuestas candidatas (compactación temprana con guardia,
  selección al entrar en Bash y Read, trabajador barato) se prueban primero en un replay sobre lo
  grabado y después en desarrollo. Entran en S2 solo si ganan allí.
- **Veredicto:** el estándar común de la sección 2, dominancia de Pareto por modelo con una no
  inferioridad de −2 puntos en tareas resueltas. **"$ por tarea resuelta" es la métrica
  principal de lectura, no un criterio aparte**: así hay una sola vara. El precio de la caché de
  1 h se calcula a 2x.
- **Instrumentación:** se cuenta cuántas veces actúa cada componente de S y las re-ejecuciones
  tras recortar una salida.
- **Modelos:** Sonnet 5.5 y Opus 5.5.

## 4. Orden

1. **Fusionar a main:**
   - browse primero, como ensayo;
   - memoria v8.2 cuando Roman lo diga;
   - partir `install.py` (814 líneas) al juntar las dos líneas.
2. **Sellar una única versión de S** y anotar su commit en cada prerregistro.
3. **Lanzar las confirmaciones** con los brazos intercalados dentro de cada suite.
   - Las suites pueden solaparse en la suscripción, porque Roman pidió paralelo.
   - Las mediciones de rapidez van solas, porque compartir la máquina falsea el tiempo de pared.
4. **No tocar el código vigilado de D** hasta que acabe, hacia las 22:00-23:00. A las 19:08 el ledger iba por 254,10 $ (base 206,42 $, techo 316,42 $; `~/.cache/sanchopanza/adopt/D.log`).

## 5. Marcador final común

Una tabla por eje y por modelo:

| Eje | Modelo | S−N (éxito) | IC95 | p | Coste S/N | Pared S/N | Veredicto |
|---|---|---|---|---|---|---|---|

El veredicto es uno de estos: "gana", "no gana" o "sin margen", dicho tal cual. No se agrega entre modelos ni entre ejes.

## 6. Presupuesto estimado

Precios de lista, pagados por la suscripción.

| Suite | Modelo | Tamaño | Estimado | Fuente | Estado |
|---|---|---|---|---|---|
| Memoria, margen F1 | Sonnet 5.5 | 64 sesiones | 12,2 $ (tope 16,5) | `prereg-f1-gate.md` | **aprobado** |
| Memoria, margen F1 | Opus 5.5 | 64 sesiones | 23,0 $ (tope 31) | idem | **aprobado** |
| Memoria, F1 completa | Sonnet 5.5 | hasta 3 celdas | hasta 76,6 $ | `prereg-f1-correctness.md` | pendiente de Roman |
| Memoria, F1 completa | Opus 5.5 | hasta 3 celdas | hasta 145,1 $ | idem | pendiente de Roman |
| Memoria, F2 | Sonnet (+ piloto) / Opus | 52 / 24 tríos | 96,3 $ / 84,2 $ | `prereg-f2-handoff.md` (costes en parte supuestos) | pendiente de Roman |
| Código | Sonnet 5.5 | 78×1×2 brazos = 156 sesiones (o 52×1 = 104) | 159 $, tope 207 (52×1: 106 $, tope 138) **[sin medir]** | Haiku 0,48 $/sesión medido (A y D) × 2,12 (Sonnet/Haiku en memory-carry); suelo ×0,30 (mismos bugs SWE-smith): 23 $ | pendiente de Roman |
| Código | Opus 5.5 | 52×1×2 = 104 sesiones (o 78×1 = 156) | 198 $, tope 258 (78×1: 298 $, tope 387) **[sin medir]** | Haiku 0,48 $ × 3,97 (Opus/Haiku en memory-carry); suelo 28 $ | pendiente de Roman |
| Código, S+find-auto | por modelo | +1 brazo | +50 % de la fila | idem | pendiente de Roman |
| Web, FRAMES fetch1 | Haiku, Sonnet | 240 sesiones | ~38 $ (techo 55) | `prereg-fetch1.md` | en curso |
| Web, GAIA dev | Sonnet 5.5 | 20×2 brazos = 40 sesiones | ~14 $ **[sin medir]** | ~0,35 $ por tarea y brazo, extrapolado de FRAMES y precios de lista | pendiente de Roman |
| Web, GAIA validation | Sonnet 5.5 | 155×2 = 310 sesiones | ~110 $ **[sin medir]** | idem, ~0,35 $ | pendiente de Roman |
| Web, GAIA validation | Opus 5.5 | 155×2 = 310 sesiones | ~220 $ **[sin medir]** | idem, ~0,7 $ | pendiente de Roman |
| Web, GAIA validation (opcional) | Fable 5.1 | 155×2 = 310 sesiones | ~540 $ **[sin medir]** | idem, ~1,75 $ | pendiente de Roman |
| Contexto | Sonnet, Opus | por fijar | sin estimar | — | pendiente de Roman |
| Otras suites | Fable 5.1 | — | sin precio medido | — | pendiente de Roman |

- **Web, estimado por tarea y brazo** (extrapolado de FRAMES y precios de lista): Haiku 0,2 $, Sonnet 5.5 ~0,35 $, Opus 5.5 ~0,7 $, Fable 5.1 ~1,75 $. Total web sin Fable ~345 $; con Fable ~885 $. Lo decide Roman.
- **Hoy solo está aprobada la prueba de margen F1 (~35 $).** fetch1 y D se lanzaron con permisos anteriores y corren por su cuenta.
- **El límite semanal de la suscripción es compartido** por las tres sesiones. Se agotó el 2026-10-01 (memoria `suscripcion-limite-semanal.md`), y su equivalencia en dólares de lista no está comprobada (`prereg-f1-correctness.md`, línea 334).
- Hoy ya van unos 120 $ de browse (handoff de a1) más lo de D. Lo pendiente de aprobar, sumando las filas de arriba (actualizado por la sesión 95 el 2026-10-05 a las 19:40 con los números de código de la sesión 8f):

  | Bloque pendiente | Estimado | Topes |
  |---|---|---|
  | Memoria: F1 completa (Sonnet + Opus) | 221,7 $ | según celdas abiertas |
  | Memoria: F2 | 180,5 $ | costes en parte supuestos |
  | Código: Sonnet 78×1 + Opus 52×1 | 357 $ | 465 $ |
  | Web: GAIA dev + validation (Sonnet + Opus) | 344 $ | sin medir |
  | **Total, sin brazos opcionales** | **~1.100 $** | |
  | Opcional: S+find-auto en código | +~178 $ | |
  | Opcional: Fable 5.1 en GAIA | +~540 $ | |

  No cabe en una semana de suscripción. La prueba de margen decide qué celdas de F1 se abren: si una familia no tiene margen, su celda no se corre. Roman tiene que priorizar.

## 7. Nota: el círculo de contexto que apenas se llena

Roman observa que el círculo de contexto de su sesión apenas se llena. No es sanchopanza: en el agente con harness propio no hay hooks de sanchopanza. Ni `.claude/settings.json` ni `~/.claude/settings.json` mencionan sanchopanza ni `SANCHOPANZA_*` (comprobado hoy con grep).

**La causa más probable es la delegación.** La sesión manda la lectura a subagentes, y el contexto de un subagente no cuenta en el de la sesión principal. Otra causa que contribuye, sin comprobar: con una ventana de 1M el círculo avanza despacio.

Los tokens de los subagentes se pagan igual (`total_cost_usd` los incluye). Es un patrón de arnés que merece medirse: delegar frente a no delegar, misma tarea y modelo, contando contexto principal, coste total, compactaciones y éxito. Va como tercer brazo de la suite de contexto.

## 8. Decisiones de Roman

1. **Presupuesto y orden de las confirmaciones frontera** dentro del límite semanal. Las candidatas son:
   - Código: Sonnet 78×1 y Opus 52×1 (unos 357 $ de lista, tope 465), o 52×1 en los dos (304 $); 26×3 queda dominado por 78×1;
   - F1 completa;
   - F2;
   - Fable 5.1 sí o no.
2. ~~Criterio de precio para crawl y web~~ **Decidido 2026-10-05:** estándar general (sección 2) en todas las suites; coste por acierto solo como métrica.
3. **Fusión a main y sello único de S:** browse ahora, memoria v8.2 cuándo, y partir `install.py`.
4. ~~API de búsqueda de pago~~ **Decidido 2026-10-05: no.** Opensource y sin cuenta; sanchopanza no es un buscador, facilita la búsqueda (WebSearch es el 36 % del gasto de Sonnet en tareas libres).
5. **Suite de contexto con el brazo de delegación:** sí o no, y con qué tope.
6. **Push:** nada se publica sin su OK.
7. **Aviso de seguridad, fuera de sanchopanza.** Retirado de la versión publicada (2026-10-15): describía un fallo de otro repositorio privado, que se trata allí.
