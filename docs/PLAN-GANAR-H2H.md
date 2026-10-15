# Plan para que S gane: qué falló en h2h y qué hacemos ahora (2026-10-07)

Escrito por la sesión 6c (línea memoria y contexto, banco largo) con la sesión d6 (línea web/h2h, S2).
d6 añade su parte en la sección 6. Sale de dos auditorías gratuitas de hoy sobre las filas de
`~/.cache/sanchopanza/{gaia,bcp,longdoc}/h2h/*-conf/` (solo campos numéricos, ningún texto de
tarea) y del mapa de huecos del 2026-10-05 (`docs/MAPA-HUECOS-ARNES.md`). Los scripts están en el
scratchpad de la sesión 4b5a56dd (`h2h_stats.py`, `h2h_power.py`, `h2h_cost.py`, `detail.py`,
`tools_size.py`).

## 1. Qué pasó, en una frase

En GAIA, BrowseComp-Plus y LongBench v2 con Sonnet 5.5, **Jev casi no llegó a actuar**, y lo que
movió resultados no fue Jev. Las tres "no gana" no dicen que un decisor barato no aporte. Dicen
que lo medimos donde no tiene trabajo que hacer, con una regla que no podía declarar victoria.

## 2. Dónde nos equivocamos

### 2.1 La medida no tenía potencia

Potencia simulada de la regla de `gaia_stats.verdict` con la varianza observada:

| Suite | n | Mejora mínima detectable en aciertos | P("gana") si S hace +3 pts | P("gana") si S cuesta un 10 % menos |
|---|---|---|---|---|
| GAIA | 132 | +9 pts | 0,13 | 0,04 |
| BCP | 90 | +12 pts | 0,07 | 0,03 |
| LongBench | 50 | +20 pts | 0,04 | 0,02 |

- El carril "gana (coste)" estaba cerrado de hecho. Exige que el IC del éxito no baje de −2 puntos,
  pero la semiamplitud de ese IC era de 6 a 12 puntos. Para ganar por coste, S tenía que sacar
  además entre +4 y +10 puntos de éxito.
- Juntando las tres suites (exploratorio): 24 discordantes a favor de S frente a 15, p = 0,20,
  +3,3 pts [−1,2; +7,8]. Un efecto de unos +7 puntos no está excluido, pero tampoco demostrado.
- La regla no tiene carril para un intercambio. BCP compró +7,8 puntos con +17 % de coste, y su
  coste por acierto salió igual (1,275 frente a 1,245).
- LongBench "más barato" (0,79) es **un solo par**: N gastó 1,87 $ en él. Sin ese par, 0,934.

### 2.2 El terreno no ejercita a S

Las suites son preguntas de unos 3 turnos, con un usuario limpio en cada sesión. Las sesiones
reales del dueño gastan el 91 % en peticiones con más de 200k de contexto (mapa, sección 1).

| Componente | Decisiones de Jev | Veces que llegó algo al modelo |
|---|---|---|
| memory | 2.308 | 0 (el almacén está vacío por construcción) |
| escaneo de inyección | 435 | 0 (las suites no traen inyecciones) |
| guard de Bash | 130 | 0 |
| check-done | 25 en GAIA, 0 en BCP | 18 devoluciones, 2 arreglos |
| search (consulta repetida) | 99 | 11 avisos, cuando la búsqueda ya estaba pagada |
| find, find-auto y la skill | prefijo con `alwaysLoad` | 1 vez en 275 sesiones; la skill, nunca |

- Proporción de decisiones de Jev que cambiaron algo que el modelo vio: **GAIA ≤ 1,7 %, BCP 0 %,
  LongBench ≤ 0,3 %**.
- Lo único que movió aciertos en BCP fue la compactación temprana. Es
  `CLAUDE_CODE_AUTO_COMPACT_WINDOW`, una variable de entorno, no una decisión de Jev. Con ella, S
  ganó 4 de los pares compactados y N solo 1. Su coste: 0,62 $ por consulta, casi todo en
  reescribir la caché.

### 2.3 El diseño añadía trabajo en vez de quitarlo

- **Prefijo.** S suma unos 970 tokens fijos (MCP con `alwaysLoad`, instrucciones, la skill y la
  nota de crawl). Eso es el 40 % del delta de coste de GAIA.
- **Latencia.** Los hooks se ejecutaron miles de veces sin producir salida: candor-hook 5.369
  veces. Resultado: S fue un 39 % más lento en GAIA.
- **`fetch_passages` era anti-sustitución.** WebFetch ya trae un lector barato: Haiku resume la
  página y a Sonnet solo le llega el resumen. Con los pasajes, a Sonnet le llegaban 2.858
  caracteres por página (mediana) frente a 693 con el resumen, unas 4 veces más. Sonnet costó
  12,17 $ frente a 9,76 $, y además el hook bloqueó 34 WebFetch.
  - Confirmado en vivo por d6 (dev de GAIA, 20 tareas, S2F frente a S2): 16 frente a 15 aciertos
    (ruido) y un coste de 1,054 [0,83; 1,36]. Sonnet sube 0,28 $ (+22 %) y Haiku baja 0,18 $.
    **fetch queda fuera de la confirmación de S2.**
- **check-done** devolvió 18 veces en GAIA: 2 arreglos, 10 devoluciones inútiles y 0,78 $ directos.

## 3. La tesis corregida

**Una decisión de Jev solo paga cuando sustituye una llamada o unos tokens del modelo caro.**
Cuesta de 24 a 119 veces menos que esa llamada. Si la decisión se suma a lo que el modelo ya hacía,
lo único que añade es prefijo y latencia, por muy acertada que sea.

"Obligar al modelo a usar sanchopanza" no significa ofrecerle herramientas: la adopción de las
herramientas opcionales fue de 6 en 27 sesiones y de 2 en 78. Significa poner la decisión **dentro
del camino por el que el modelo ya pasa**: un hook que reescribe la entrada o la salida de la
herramienta que acaba de llamar. Así el modelo no tiene que elegir, y no se rompe ningún prefijo
cacheado, porque la decisión actúa antes de que el contenido entre al contexto.

Claude Code lo permite. Está documentado y confirmado hoy:

- **PreToolUse con `updatedInput`** sobre Agent/Task puede cambiar el campo `model` del subagente.
- **PostToolUse con `updatedToolOutput`** reemplaza lo que el modelo ve de Bash, Read, Grep o una
  herramienta MCP. El hook construye la salida entera; el texto completo puede quedarse en un
  fichero.
- **El lector de WebFetch no se puede configurar** (ni modelo, ni prompt, ni tamaño). Hay que
  dejarlo como está.
- **Bifurcar una sesión grabada a mitad no está documentado.** Solo se puede reanudar desde el
  final; cortar el `.jsonl` a mano sería frágil.

## 4. Apuestas de sustitución, por dinero en juego

Los techos vienen del mapa (141 sesiones reales, 14.900 $). Se solapan y no se suman.

| # | Palanca | Qué sustituye | Techo | Evidencia de Jev | Riesgo a medir |
|---|---|---|---|---|---|
| A | **Pasajes al entrar** en Bash, Read y Grep: un PostToolUse deja al modelo solo lo pertinente para la intención que acaba de escribir; lo demás va a un fichero | Tokens de salida que luego se releen más de 50 veces (31 % del coste) | 11-22 % | Torneo de párrafos: 96,5 % con el 3,1 % del texto; `select_passages` 87,2 % con el 21 % | Que el modelo vuelva a pedir lo que falta (rtk salió +7,6 %). Contar las re-ejecuciones |
| B | **Delegar tandas mecánicas** (correr tests, buscar, aplicar un patrón) a un trabajador barato. PreToolUse elige el modelo del subagente; el hilo principal no cambia | Peticiones de Opus o Sonnet que son pasos mecánicos (55 % de las peticiones) | 28 % de Opus a Haiku; 10 % a Sonnet | `route_task` 17/20 offline; la delegación se rompía 13/13 (arreglado en 7a39a1f) | Calidad del trabajador; caché del subagente con TTL de 5 minutos (mapa, hueco 5) |
| C | **Compactar antes, con la guardia eligiendo qué se queda**, a ~160-200k | Releer un contexto enorme a 0,1x en cada petición (91 % del coste por encima de 200k) | ~17 % o más | keep 6/7; una sesión 30/40 frente a 27/40 a 0,837x | Que compactar pierda el hilo; medir aparte la ventana (N-early) y la guardia (Jev) |
| D | **Verificar el documento devuelto** ("¿este documento contesta la pregunta?") en las sesiones de búsqueda que ya lo tienen. Reformulada por d6 el 2026-10-07: **es calidad, no ahorro**. En BCP, en las respuestas buenas el agente para justo al llegar al documento que la contiene (mediana: 0 búsquedas después), así que parar antes no ahorra nada. El dinero se va en las malas (N 43,7 $ de 61; S 45,4 $ de 71), y en la mayoría de ellas el documento correcto no apareció nunca | 8 sesiones de N y 9 de S recibieron el documento correcto y fallaron igual; S siguió buscando una mediana de 10 veces más (7,8 $) | ~9 respuestas de 90 | Verificación de citas 19/20 | **Medida y cerrada** (d6, 2026-10-07, OK de Roman, Jev 0,11 $, 2.674 decisiones, rama h2h-d 11625f4). Jev `triage_part` separa el documento correcto del resto con AUC 0,95. Pero de las 17 sesiones, 10 ya habían abierto el documento correcto y fallaron leyéndolo. De las 7 que no lo abrieron, un aviso con corte 0,9 habría marcado 3. Techo: ~3 respuestas en 180 sesiones. **No compensa construirla.** En BCP las respuestas se pierden por recuperación: 58 de 75 sesiones malas no vieron nunca el documento correcto |
| E | **check-done que pregunte algo comprobable** (si la respuesta sale de un resultado de herramienta, si hay una cuenta sin hacer) o devolución más barata. **No por umbral**: en GAIA la p de Jev no separa (las 2 útiles, p 0,12 y 0,20; las 10 inútiles, de 0,04 a 0,49; las 6 que siguen mal, de 0,04 a 0,25), y cualquier corte más exigente se lleva las dos que arreglan (d6, 2026-10-07) | Devoluciones inútiles | Pequeño | 18 devoluciones: 2 de mal a bien, 10 buenas devueltas para nada, 6 malas que siguen mal, 0 estropeadas | **Medida en seco y cerrada** (d6, rama h2h-ne 2d5acc6, `docs/results/2026-10-07-h2h-e`): ninguna señal comprobable en código separa las respuestas malas de GAIA (270 sesiones, 24 % malas). La que más concentra es la duda en el mensaje final: 36 % de malas frente a 17 %, pero marca el 36 % de las sesiones. Respuesta copiada, cálculo tras la última lectura o respuesta numérica: no separan. El check-done actual lo hace mejor (devuelve el 13 % de las sesiones; el 44 % de ellas eran malas). **check-done se queda como está** |

**Replay gratis del 2026-10-07** (141 sesiones principales y 863 subagentes, 15.384 $ con la caché
a su TTL real; 2,2 caracteres por token medidos con el `usage`, no 3,5; scripts en el scratchpad de
4b5a56dd, `replay/`):

- **A pasa.** Las relecturas de salidas de shell, Read y Grep cuestan 4.982 $, el 32 % del total
  (shell 76 %, Read 23 %, Grep 1 %).
  - Con T = 2k tokens y recorte al 25 %, el techo bruto es del 15,9 %. Neto, con el re-pedido
    natural (~31 %) y trozos dirigidos, queda en el 11,2 %. Al 10 %, el 14,3 %.
  - Equilibrio: perdería solo si casi cada recorte provocase un re-pedido entero (r ≥ 0,7).
  - Las salidas grandes no se re-piden más que las pequeñas.
  - El 60 % del ahorro está en los subagentes.
  - Se lanza con: T = 2k en shell y Read, sin Grep; un brazo al 25 % y otro al 10 %; el texto entero
    a un fichero; registrar los re-pedidos por recorte; abortar si r > 0,5 con trozos enteros.
- **B no pasa.**
  - Las peticiones mecánicas son el 19-25 %, no el 55 %, y casi todas van sueltas. Las tandas de 3
    o más son el 4 % de las peticiones.
  - Neto: 3,1 % con oráculo, ~1 % en vivo, y dos tercios se solapan con A.
  - Queda descartada como tanda propia.
- **A se construye extendiendo `harness/browse_hook.py`**, que ya reemplaza salidas con
  `updatedToolOutput`, archiva el texto entero, lee las salidas de Bash de más de 30k que Claude
  Code guarda aparte y se registró 12-13 % más barato con Playwright MCP. No se hace un módulo
  paralelo.

A, B y C son exactamente lo que mide el banco largo (60 bugs seguidos en un repositorio, más de
200k de contexto). D y E son de la línea de d6.

## 5. Cómo medimos esta vez

1. **Primero el terreno donde está el dinero.** Banco largo: humo hoy, después la prueba de margen
   (solo N, Sonnet 5.5 y Opus 5.5, techo 175 $), que dice si N deja hueco y cuánto varía, y
   dimensiona n y k. Es independiente del diseño de S, así que no se tira aunque S cambie.
2. **Replay gratis antes de cada apuesta.** Sobre las transcripciones del banco y las 141 sesiones
   reales:
   - A: cuántos tokens de salida de herramientas se habrían quedado fuera, y cuántos de esos se
     volvieron a leer después.
   - B: qué fracción de peticiones clasifica Jev como mecánicas, y cuánto costaron.
   - C: dónde habría compactado y qué se habría quedado.
   Solo pasa a una tanda de pago la apuesta cuyo techo realista supere el 5 % del coste.
3. **Registrar si cada componente actuó.** Cada fila lleva `prefix_tokens`, `compactions`,
   `compact_usd`, `tool_result_tokens` por herramienta y `hook_ms` por componente. Cada decisión
   del journal lleva `acted` e `injected_chars`. Un S que no actúa no puede pasar por neutro.
4. **Medir cada mecanismo donde actúa,** además del veredicto global. Hay dos formas:
   - estratos por punto de disparo (sesiones que compactaron, sesiones que check-done devolvió);
   - un brazo que aísle el mecanismo (N-early para la ventana).
5. **Una regla que pueda ganar,** escrita antes de lanzar:
   - el margen de no inferioridad, a la semiamplitud esperada del IC, nunca −2 puntos con estos n;
   - un carril de intercambio: dólares por tarea resuelta, Pareto por modelo;
   - n y k dimensionados por la varianza medida en el margen.
6. **Modelos frontera para la pregunta principal:** Sonnet 5.5 y Opus 5.5. Haiku solo sirve para
   comprobar mecanismos.

## 6. Reparto y orden

| Quién | Qué | Estado |
|---|---|---|
| d6 | **S2** para las suites de una pregunta: `--guard --guard-profile coding --context-budget 160000 --check-done --provider jev`, chooser keep. Fuera memory, candor, fetch, crawl, find, find-auto, skill, scan-content y prune. El brazo S2F (S2 + fetch v3) en el dev de GAIA, para medir fetch justo donde actúa | **Cerrado** (11,4 $): más barato que S0, no que N; fetch fuera. Sin confirmación (decisión del dueño) |
| d6 | D y E (verificar los documentos devueltos, check-done más exigente) | **Cerrados, sin palanca**: D techo ~3/180 (`2026-10-07-h2h-d`); E ninguna señal separa (`2026-10-07-h2h-e`) |
| d6 | N-early en BCP | **Cerrado** (37,97 $): la ventana sola iguala a S0 |
| 6c | Banco largo: humo, margen y después N frente a S en cadenas largas | Humo en curso (2026-10-07) |
| 6c | Replay gratis de A, B y C sobre transcripciones; después A y B en una rama con prueba en seco | Siguiente |
| 6c | Registro de actuación por componente (sección 5, punto 3) en el runner largo | Siguiente |

Una tanda de pago a la vez entre las dos líneas, avisando antes con PID, hora y techo.

### Estado del 2026-10-07, 13:40

- **Dev de S2 (d6)**: 11,4 $, 10 tareas comunes por suite, solo dirección
  (`sanchopanza-s2`, `docs/results/2026-10-07-h2h-s2/README.md`, 835bd6f).
  - Frente a S0, S2 es más barato en las tres: LongBench 0,675 [0,60; 0,75], BCP 0,832
    [0,54; 0,98], GAIA 0,886. No pierde respuestas.
  - Frente a N no es más barato en ninguna: GAIA 1,085, LongBench 1,28, BCP 1,41. Ojo: N corrió el
    día antes.
  - S2 no añade nada al prefijo. Si N va siempre primero, S2 puede heredar su caché, así que en la
    confirmación hay que alternar el orden.
  - Propuesta de d6: medir D y la compactación sola (N-early) donde actúan, antes de sellar.
- **Banco largo (6c)**:
  - Humo: 2,88 $; todo el camino visto en vivo salvo los callbacks.
  - Margen: lanzado a las 12:41, techo 190 $.
  - **Piloto A**: lanzado a las 13:40 con el OK del dueño, en paralelo a la fase Sonnet del margen.
    - Brazo A = N + solo `passages-hook` (lean edd37bb, revisado con 13 hallazgos arreglados).
    - Mismas 2 cadenas y topes que N; techo 80 $.
    - Aborto si r_whole > 0,5 tras 10 cortes.
    - Comparación descriptiva con `pilot_a_compare.py`.
- **Resultado del piloto A** (16:06; `sanchopanza-pilot-a`, `docs/results/2026-10-07-pilot-a/`;
  A 54,89 $; k = 1, descriptivo):
  - **Calidad, mismos bugs**: A 91 y N 86 resueltos; 8 solo A frente a 3 solo N (p 0,23).
  - **Coste, mismas peticiones**:
    - conan: −10,7 % en la llamada 50.
    - pydantic: −3,6 % en la 50, pero +1,9 % al cerrar, por dos llamadas caras.
  - **Coste por bug resuelto**: conan 0,657 frente a 0,647 (con el coste real de N); pydantic
    0,500 frente a 0,535.
  - **Re-pedidos**: 0 enteros en 26 cortes.
  - **El hook actuó poco**: Sonnet acota casi todos los `Read`.
  - **Lectura**: no daña la calidad y cuesta igual o hasta un 10 % menos. Es una dirección, no
    un resultado.
- **N-early en BCP** (d6; 37,97 $; rama h2h-ne 4fec545; `docs/results/2026-10-07-h2h-ne`).
  Muestra: las 26 consultas donde N pasó de 150k.

  | | N | S0 | NE |
  |---|---|---|---|
  | Aciertos | 4 | 6 | 7 |
  | Documento correcto visto | 7 | 10 | 10 |
  | Abandonos | 19 | 17 | 13 |

  - Coste NE/S0: 0,954 [0,80; 1,15].
  - **La ganancia de S en BCP es la ventana de compactación, un ajuste de Claude Code.** La
    reinyección de la petición por la guardia no añade nada medible.
  - NE frente a N está sesgado a favor de NE (consultas elegidas porque N se alargó), así que la
    comparación justa es NE frente a S0.
- **Historia común de las dos líneas: menos contexto, menos abandonos.** Se ve en BCP con la
  compactación temprana y en el banco largo con A (pydantic: 6 abandonos de N pasados 150k
  frente a 2 de A).
  - La pregunta que queda para Jev: ¿cuánto de A es Jev y cuánto es solo cortar? Hace falta un
    brazo A-BM25 (mismo hook, sin decisor) frente a A-Jev.
  - Si BM25 da lo mismo, Jev sobra en A y lo que vale es la idea de cortar al entrar.

### Decisiones del 2026-10-07 por la tarde (d6 y 6c, a petición del dueño)

- **Una sola rama para las dos líneas: `comun`** (worktree `sanchopanza-comun`, creada de main
  4f985ec). Ya lleva lean, pilot-a, este plan y el MAPA. long-launch entra cuando su nota termine.
  No se abren ramas nuevas.
- **Reglas del worktree compartido**:
  - `git add` solo de rutas propias; nada de checkout, stash, reset ni rebase.
  - Avisar antes de tocar un fichero que la otra sesión esté editando.
  - Las tandas de pago no salen nunca del worktree compartido, sino de un worktree `--detach` en
    un commit fijo: los hooks del runner se leen del disco en cada llamada.
  - `comun` entra en main solo cuando las dos lo digamos, con la suite en verde.
- **En preguntas sueltas (h2h) se deja de gastar.** S no gana ahí, y lo único que movió el
  resultado (la ventana de compactación) es un ajuste de Claude Code.
- **El listón para todo lo largo es N-early, no N pelado.** Cualquier ventaja de S sobre N puede
  ser solo la ventana. Por eso la prueba del paso siguiente es Ne frente a Ne+A: así se mide solo
  lo que A añade encima de la ventana.
- **Orden**:
  1. 6c: replay de Jev frente a BM25 en los 26 cortes de A, hecho, gratis. Jev conserva 11/32
     unidades necesarias, BM25 5/32 y el azar 6,7. Pero todo sale de conan y hay sesgo de
     exposición: es una señal, no una prueba.
  2. 6c: la prueba sin sesgo. Se aplican los dos selectores a las salidas grandes del brazo N del
     margen (Sonnet y Opus, sin cortes) y se mide contra lo que N edita o vuelve a pedir después.
     Jev ~0,10-0,20 $. **Aprobada por el dueño a las 17:3x, en marcha** con tope duro de
     0,25 $ en código.
  3. 6c: si Jev aporta, Ne frente a Ne+A en el banco largo, mismas cadenas, Sonnet, con techo que
     se pide al dueño. Si no aporta, A con BM25 y Jev fuera de ese punto.
  4. d6, gratis: el README y el install dicen que `--context-budget` es la ventana de Claude Code y
     lo que se midió con ella, sin cambiar comportamiento.

### Resultados del 2026-10-07, 17:30 (6c)

- **Margen (solo N, cadenas largas, 168,57 $)**:
  - **Sonnet 5.5** resuelve 44 de 60 en las dos cadenas: deja un 27 % de hueco.
  - **Opus 5.5** resuelve 57 de 60 en conan (sin margen) y 53 de 60 en pydantic.
  - N no compactó nunca hasta 452k.
  - Los abandonos se acumulan pasados 150k: en pydantic, 6 de 7 en los dos modelos.
  - El modelo de coste se quedó corto: Sonnet ~41 $ por cadena entera (decía 25); Opus 61 $
    por 59 peticiones.
- **Prueba sin sesgo de Jev frente a BM25** (brazo N del margen, que lo vio todo; Jev real,
  0,013 $ en 45 decisiones; scripts en el scratchpad de 4b5a56dd, `jevbm25/`):
  - El hook habría actuado en 43 de 1.074 llamadas de Bash y Read (4 %).
  - De las 59 unidades que N usó después, a igual presupuesto de caracteres:
    - Jev se queda 20 (34 %), BM25 13 (22 %) y el azar 12,7.
    - **Jev le gana al azar (p 0,007); BM25 no (p 0,56).**
    - **Jev frente a BM25 no se separa**: signo 6 a 4 (p 0,75). La ventaja de Jev se concentra
      en tres salidas.
  - Lectura: elegir con Jev es mejor que cortar a ciegas. Para separarlo de BM25 harían falta
    unas 250-300 salidas elegibles (~25 cadenas).
  - Coste real: ~0,00028 $ por decisión de torneo, diez veces la cifra supuesta.
- **Consecuencia para A**:
  - Con Sonnet y Opus en Claude Code actúa en el 4 % de las llamadas. Su techo aquí es pequeño.
  - El −10,7 % de conan en el piloto puede ser en parte ruido.
  - Lo que sí se repite en todas las líneas es que con menos contexto el agente se rinde menos.

### Decisión del 2026-10-07, noche (d6 y 6c; aprobada por el dueño)

- **Siguiente tanda de pago: Ne en las dos cadenas largas y N repetido en pydantic**, con Sonnet
  5.5 y techo duro de 110 $: perfil Ne 76 $ (2 × 38, como N) y repetición de N 34 $ (N gastó
  23,55 $ ahí). La lanza 6c desde un worktree `--detach` en un commit fijo.
- Se descartó la propuesta de Ne + Ne+A (~110 $): con A actuando en el 4 % de las llamadas y
  k = 1, lo que A añade encima de Ne quedaría dentro del ruido. Ne+A se aplaza hasta que Ne
  muestre algo.
- **Por qué la repetición de N**: sin saber cuánto varía N contra sí mismo en la misma cadena, Ne
  frente a N con k = 1 no se puede leer (el 91 frente a 86 del piloto A puede ser eso).
- **Medida principal**: los abandonos y el contexto en el que se producen, por encima de los bugs
  resueltos. Es lo que se movió en BCP (19 → 13) y es más sensible que el recuento.
- **Se lee como dirección, no como veredicto**: k = 1 y dos cadenas.

### Suelo de ruido y medida de abandono, 2026-10-07 a las 18:44 (e8, relevo de d6, y 6c)

- **N2** (N repetido en pydantic, 21,92 $): 46/60, sin compactar, techo sin tocar. Se compara con
  `benchmarks/adopt/long_compare.py`, que absorbe `pilot_a_compare.py`.
- **Suelo N frente a N2**, mismo brazo y misma cadena:
  - Resueltos 44 frente a 46. Discrepan 6 de 60 bugs (2 solo N, 4 solo N2).
  - Coste N2/N 0,931 (0,917 en la llamada 50): una sola cadena mueve el coste un ±7-8 %. El
    −3,6 % y el +1,9 % de A en pydantic quedan dentro, y el −10,7 % de conan, en el borde.
  - A frente al suelo: en los 54 bugs en que N y N2 coinciden, +2 resueltos y −0. Su 0/4 frente
    a N baja a 2/4 frente a N2.
- **Fallo en la medida de abandono.** `long_report.give_ups` contaba toda llamada que no cambia
  código, también cuando un bug anterior de la cadena ya había arreglado el bug ("the fix was
  made under bug 12"). Esas llamadas acaban resueltas: son aciertos, no abandonos. Afectaba a 3
  de 7 en N, 3 de 6 en N2 y 3 de 4 en A.
- **Decisión**, antes de ver ningún resultado de calidad de Ne:
  1. La medida principal de la tanda pasa a ser el **abandono no resuelto**: give_up con
     `grade.resolved` falso, con su contexto. El give_up crudo se publica al lado.
  2. Va como campo derivado en `long_compare` (`gave_up_unresolved`, e8) y en `long_report`
     (`give_ups.unresolved`, 6c). 6c corrige la definición en `docs/history/STATUS-launch.md`.
  3. Ne se lee contra los dos N, en pydantic: discordantes y `stable_flips` sobre los bugs en que
     N y N2 coinciden. Una diferencia del tamaño del suelo (6 de 60) es ruido.
- **Lo que se había visto de Ne al decidir**, dicho para que conste: 6c seguía en vivo su coste y
  su contexto en conan (en la llamada 50, 14,06 $ frente a 27,56 de N, y 130k frente a 427k de
  contexto). No se había visto ni un resuelto ni un abandono de Ne: no había nota.
- **Con la medida nueva, en pydantic**: N 4 abandonos no resueltos (3 pasados 150k; contexto 57k,
  161k, 190k y 327k), N2 3 (2 pasados 150k; 146k, 264k y 287k), A 1 (148k). Entre N y N2 solo se
  repiten 2: qué bug abandona varía tanto como cuántos.

### N-early en el banco largo: más barato y peor (2026-10-07, 19:45, 6c)

Tanda aprobada por el dueño: 110 $ duros; gastado 31,17 + 21,92 = 53,09 $. Sonnet 5.5. Leída con
`long_compare` desde comun 71a582e. La medida principal es el abandono no resuelto, decidida antes
de ver ningún resultado de calidad de Ne.

| | conan: resueltos | conan: coste | pydantic: resueltos | pydantic: coste | Abandonos no resueltos (conan / pydantic) |
|---|---|---|---|---|---|
| N | 44 (51 llamadas, tope) | 28,45 | 44 | 23,55 | 1 / 4 |
| N2 (N repetido) | – | – | 46 | 21,92 | – / 3 |
| **Ne** (N + ventana 193k) | **37** (62 llamadas) | **17,33** | 44 | **13,84** | **3 / 6** |
| A (N + pasajes de Jev) | 47 (58, tope) | 30,90 | 48 | 24,00 | **0 / 1** |

- **conan, sobre los 49 bugs comunes**:
  - N frente a Ne: 12 solo N y 1 solo Ne (p 0,003).
  - Ne frente a A: 4 solo Ne y 16 solo A (p 0,012).
  - Coste de Ne: x0,54.
- **pydantic**:
  - Ne frente a N: discordantes 3/3, a x0,59 del coste.
  - Pero Ne se rinde más: 6 abandonos no resueltos frente a 4 (N) y 3 (N2), y lo hace a contexto
    bajo, tras compactar (43-147k).
  - Suelo de ruido N frente a N2: 2/4 discordantes, coste x0,93.
- Salvedad: k = 1, y McNemar supone bugs independientes, que dentro de una cadena no lo son del
  todo.

**Lectura, solo cifras: la causa está pendiente** (corregido a petición de e8, 19:55):

- Ne cuesta un 41-46 % menos.
- En conan resuelve menos.
- En pydantic se rinde más.

**No está demostrado que sea por compactar.** La mitad de las pérdidas de Ne en conan ocurren
antes de su primera compactación: bugs 1, 4, 6, 7, 9 y 12, cuando Ne es todavía el mismo
tratamiento que N. Las otras seis caen después (16, 23, 24, 33, 35 y 50).

Por tercios de la cadena:

| | 1.er tercio | 2.º tercio | 3.er tercio |
|---|---|---|---|
| Ne | 11 | 12 | 14 |
| N | 18 | 15 | 8 |
| A | 20 | 15 | 12 |

Ne no cae tras compactar, empieza peor; N cae en el último tercio. En conan no hay N2, así que
no hay suelo de ruido allí.

e8 comprueba gratis si Ne ya falla los bugs 1-12 en su instantánea de la llamada 12. Hasta
entonces no se escriben causas, y las consecuencias de abajo quedan en suspenso.

**Consecuencias, en suspenso hasta esa comprobación**:

1. Que N-early sea listón de coste y no de calidad en código largo: **prematuro**.
2. Ne+guard frente a Ne (¿recupera la guardia lo que la ventana pierde?): **depende de que la
   pérdida venga de compactar**.
3. A sigue siendo el brazo con menos abandonos no resueltos (0 y 1), con el coste dentro del ruido
   de N. Actúa en el 4 % de las llamadas: hacen falta más cadenas.

### N-early: la comprobación de la llamada 12 (e8, 2026-10-07, 20:05)

Instantánea `diff-12`, anterior a cualquier compactación de Ne, puntuada con `perbug.grade`
(Docker, gratis), sobre los bugs 1-12 de conan:

| | Resueltos |
|---|---|
| N | 10/12 |
| Ne | 5/12 |
| A | 12/12 |

- Antes de compactar, Ne es el mismo tratamiento que N. La llamada 1 tiene un init idéntico salvo
  las rutas: la ventana no se ve en el modelo (`contextWindow` 1.000.000 en los dos) y la lectura
  del prefijo es la misma (15.786).
- Aun así, Ne falla el bug 1 tras 13 peticiones, mientras N lo resuelve en 4. **Es variación entre
  corridas**, y en conan parece mayor que en pydantic.
- Sobre los 49 bugs comunes, con la nota final:

  | Tramo | N | Ne | A |
  |---|---|---|---|
  | Llamadas 1-12 | 11 | 5 | 12 |
  | Llamadas 13-50, tras la primera compactación de Ne | 30 | 25 | 30 |

  En el segundo tramo Ne pierde 5 de 37, del orden del suelo de pydantic (6 de 60 discordantes).

**Lectura acordada (e8 y 6c)**:

- (a) **Coste: firme como dirección.** Ne cuesta x0,54 (conan) y x0,59 (pydantic), muy fuera del
  ±8 % del suelo de N.
- (b) **Calidad: no hay prueba de que compactar haga perder el hilo.** La parte grande de la
  brecha de conan es anterior a compactar; la de después está en el ruido. En pydantic Ne = N
  (3 y 3).
- (c) **Abandonos: Ne no se rinde menos.** Tiene 6 no resueltos, frente a 4 y 3, todos por debajo
  de 150k porque nunca pasa de 160k. Sobre los 57 bugs estables, stable_flips da +1, dentro del
  ruido. No se confirma "menos contexto, menos abandonos" con Ne, pero tampoco lo contrario.
- (d) **A es el brazo más fuerte en calidad**: 12/12 antes de la llamada 13 en conan; en pydantic,
  +2/−0 sobre los bugs estables.

**Lo que falta para separar (b) y que proponemos al dueño**:

- conan necesita su propio suelo de ruido.
- Mínimo: Ne repetido en conan (~17 $) y N repetido en conan (~32-41 $, tope 38), ~55-60 $ en
  total.
- Con solo Ne repetido en conan (~17 $) ya se vería si el 5/12 del principio se repite.

### Repetición en conan: N2, Ne2 y A2 (sesión 5a, relevo de 6c, con e8; 2026-10-07, 21:30)

Tanda aprobada por el dueño: 100 $ duros. Lanzada a las 20:02 desde run-noise (comun 1bf7343),
Sonnet 5.5, conan-long60-1, una raíz por brazo. Gastado: N2 30,61 + Ne2 19,37 + A2 29,37 =
**79,35 $** (lo cobrado por el runner; report.json da 18,79 en Ne2).

- Los tres pararon por su tope (exit 2): N2 tras la llamada 49, A2 tras la 50 y Ne2 tras la 52.
  El lanzador solo puntúa con exit 0, así que la nota se puso a mano (`long_run.py grade`,
  Docker, gratis).
- Lectura con `long_compare`. La medida principal es el abandono no resuelto, decidida antes de
  ver nada.

| | Resueltos /60 | En los 48 bugs que corrieron los seis | Bugs 1-11 (antes de compactar) | Bugs 12+ | USD en la llamada 50 | Abandonos no resueltos (contexto) |
|---|---|---|---|---|---|---|
| N | 44 | 40 | 10 | 30/37 | 27,56 | 1 (101k) |
| N2 | 47 | 47 | 11 | 36/37 | 30,61 | 0 |
| Ne | 37 | 30 | 5 | 25/37 | 14,06 | 3 (83k, 125k, 130k) |
| **Ne2** | **51** | **48** | 11 | **37/37** | **18,24** | 0 |
| A | 47 | 41 | 11 | 30/37 | 24,61 | 0 |
| A2 | 46 | 45 | 11 | 34/37 | 29,37 | 0 |

- La columna "Bugs 1-11" es la nota final. La instantánea `diff-11` de e8 da lo mismo: N 10,
  N2 11, Ne 5, Ne2 11, A 11, A2 11.
- Ne2 compactó en las llamadas 12, 25, 41 y 52, así que sus 37/37 de los bugs 12+ son todos
  posteriores a compactar.
- **Pares de réplicas del mismo brazo**, en bugs comunes: N/N2 0 frente a 7, Ne/Ne2 0 frente
  a 19, A/A2 1 frente a 5.
- Stable flips con base de dos corridas:

  | Brazo | Base | Bugs en que la base coincide | El brazo gana | El brazo pierde |
  |---|---|---|---|---|
  | Ne | N+N2 | 41 | 0 | 11 |
  | N | Ne+Ne2 | 30 | 0 | 1 |
  | A | N+N2 | 41 | 1 | 3 |
  | N | A+A2 | 43 | 2 | 3 |

**La unidad de réplica es la corrida, no el bug** (e8):

- N contra N2 (el mismo brazo dos veces) da 0 frente a 7, con un McNemar de p 0,016.
- Dentro de una cadena los bugs no son independientes: una corrida que entra en mala racha
  arrastra varios a la vez.
- Por eso los p por bug de conan publicados más arriba **quedan retirados como evidencia**: N
  frente a Ne, p 0,003, y Ne frente a A, p 0,012.
- Con k = 2 por brazo se dan rangos entre corridas. La inferencia irá por cadena cuando haya
  varias (`long_report.cluster_bootstrap`).

**Respuestas, solo cifras** (la causa de la variación entre corridas no está demostrada):

- **(a) ¿Pierde calidad N-early? No hay evidencia de que pierda calidad en conan.**
  - Ne resuelve entre 37 y 51 y N entre 44 y 47.
  - La repetición de Ne es la mejor de las seis corridas, también después de compactar (37/37).
  - Ne tiene la mayor dispersión entre corridas: 37-51, con 0 frente a 19 entre réplicas,
    contra 0 frente a 7 de N y 1 frente a 5 de A. Con k = 2 no se puede decir si esa dispersión
    es propia de Ne o de la cadena.
  - Su mala corrida ya iba mal antes de compactar (diff-11: 5/11, frente a 11/11 de Ne2 con el
    mismo brazo). La dispersión observada no viene de la ventana: viene de una trayectoria
    temprana mala que arrastra la cadena, algo que puede pasarle a cualquier brazo y que explica
    también el 0 frente a 7 de N.
  - Tampoco hay prueba de que Ne gane calidad.
- **(b) ¿Se sostiene la ventaja de A? No.**
  - A resuelve 46-47 y N 44-47. Contra N2, A2 sale 1 frente a 3 en bugs comunes.
  - El 47 frente a 44 del piloto era el N bajo de la primera corrida.
  - En abandonos no resueltos, A (0 y 0) tampoco se separa de N (1 y 0).
  - pydantic tiene una sola corrida de A (48 frente a 44-46): no cambia la lectura.
- **(c) ¿Es firme el coste de N-early? Sí, como dirección.**
  - En la llamada 50, Ne/N va de x0,46 a x0,66 según el par de corridas: x0,56 con las medias,
    16,15 frente a 29,09.
  - N/N2 da x0,90 en el mismo punto.
  - En pydantic, x0,59.
  - Ne2 costó más que Ne a igual llamada (18,24 frente a 14,06). El intervalo se ensancha, pero
    el coste sigue muy por debajo del de N.
  - Lo que paga el usuario es el coste por bug resuelto: Ne 0,38-0,47 $, N 0,65-0,73 $ y A
    0,64-0,66 $.
  - A frente a N: x0,80-1,07 (x0,93 con las medias), dentro del ruido.
- **(d) La medida principal no separa a ningún brazo.** Hay 0 o 1 abandonos no resueltos por
  corrida, salvo los 3 de la mala corrida de Ne.
  - En conan, "menos contexto, menos abandonos" no se puede probar: N casi no abandona (0-1).
  - Donde había abandonos pasados 150k era en pydantic, y allí Ne no los redujo: 6, frente a 4
    de N y 3 de N2.

**Consecuencias** (las que quedaban en suspenso en la subsección anterior):

1. **N-early es el listón en código largo** (conan y pydantic, Sonnet 5.5): cuesta x0,46-0,66
   y no hay evidencia de que pierda calidad, dentro del rango entre corridas. Que la iguale no
   está demostrado.
2. **Ne+guard queda descartado.** Solo tenía sentido si compactar perdía el hilo, y no aparece
   ninguna pérdida.
3. **A no ha mostrado ventaja de calidad sobre N.** Lo que queda abierto es lo que A añade encima
   de Ne (Ne frente a Ne+A). Con 6 a 19 bugs discordantes entre réplicas del mismo brazo, eso solo se
   puede leer con varias cadenas.
4. Antes de la próxima tanda de A hay que corregir un fallo visto en vivo: Claude Code ignora el
   permiso para leer el archivo de salidas recortadas, porque la carpeta de trabajo no está
   marcada como de confianza. Pasó igual en A y A2, así que las dos son comparables entre sí.

**Propuesta al dueño para el siguiente paso** (5a y e8, 21:45; nada decidido):

1. **Gratis: replay de A sobre las transcripciones de Ne** (Ne y Ne2 de conan, Ne de pydantic).
   - Mide qué parte del coste de Ne son relecturas de salidas grandes de Bash y Read que A habría
     recortado, como el replay de las 141 sesiones.
   - Da el ahorro por cadena y su dispersión entre Ne y Ne2. El replay es determinista sobre una
     misma transcripción: no tiene ruido entre corridas.
   - Regla 5.2: si el techo realista no pasa del 5 % del coste de Ne, **A se archiva para código
     largo**. Con Ne por debajo de 160k se relee menos, y es de esperar que el techo baje.
2. **Gratis, en paralelo: validar más cadenas long60.**
   - moto-1, con el arreglo de lectura de color (comun ca1796a).
   - dvc-1, que se relanza: murió por un cierre de consola (0x40010004), no por el código.
   - conan-2 y conan-3, con repuestos extra (`long.py extra60`), comprobando antes que su sorteo
     sigue tras los repuestos de conan-1.
   - Disco: 72 GB libres; como mucho dos a la vez y moto al final.
   - Hacen falta para cualquier comparación futura de calidad (sección 7).
3. **De pago, solo si (1) pasa y la potencia alcanza: Ne frente a Ne+A como prueba de coste**, con
   no inferioridad laxa en calidad. La calidad de Ne+A frente a Ne no se puede leer: Ne va de 37
   a 51.
   - Ruido de coste entre réplicas en la llamada 50: N/N2 1,11 (conan) y 0,92 (pydantic), A/A2
     1,19, Ne/Ne2 1,30. Es decir, entre un 8 y un 30 % por corrida.
   - El efecto que cabe esperar de A es de un 5-10 %. La desviación del log-cociente entre dos
     corridas, medida en esas cuatro réplicas, es de 0,171 (e8; verificada por 5a). Para ver un
     −7 % (ln 0,93 = 0,073) con alfa 0,05:
     - ~21 cadenas para una potencia del 50 %;
     - ~43 cadenas para el 80 %;
     - con 4 cadenas, el IC95 del cociente sale de x0,76 a x1,31.
   - Antes de pedir dinero se calcula gratis, con la desviación que dé (1) y
     `long_report.cost_ratio`, el número de cadenas necesario.
   - Si son más de las validadas, no va a pago, y se dice así: "el efecto de A sobre Ne, si
     existe, es menor de lo que este banco puede medir".
   - Si va a pago: más cadenas con k = 1 mejor que k = 2 en menos, porque la unidad es la cadena.
     Referencia: ~19-22 $ por corrida de Ne o Ne+A, con un tope de 25 por corrida.
   - **4 cadenas** (las dos de hoy y dos nuevas) son 6 corridas: ~125 $ esperados, 150 de techo.
     No bastan para ver un 7 %, así que con 4 cadenas **no se propone**.

El dueño aprobó (1) y (2) a las 21:50 y pidió que nos coordinásemos: 5a hace (1) y e8 hace (2),
desde un worktree `--detach` en comun f511abd.

### Replay de A sobre N-early (5a, 2026-10-07, 22:10; gratis)

Script: `replay_ne.py`, en el scratchpad de la sesión 12aa49bd.

- Reutiliza tal cual `bet_a.collect` y `evaluate`, `rc.prep` (replay de 6c) y el parser de
  anatomy, sobre la transcripción de cada cadena (`cfg/<cadena>-sonnet-<brazo>/claude-config`).
- Calibración: el coste reconstruido coincide con el real (N conan 28,45, Ne 16,71, Ne2 18,79,
  Ne pydantic 13,54).
- Configuración con la que se lanzó A: T = 2k, shell y Read, sin Grep. Ahorro en % del coste de
  cada corrida:

| | Salidas que se habrían cortado | Bruto | **Neto con re-pedido natural** (la regla 5.2 de 6c) | Neto con r = 0,10 (sensibilidad) | Neto natural al 10 % |
|---|---|---|---|---|---|
| Ne conan | 44 | 13,5 | **3,4** | 11,7 | 5,9 |
| Ne2 conan | 43 | 13,6 | **4,3** | 11,8 | 6,7 |
| Ne pydantic | 10 | 3,7 | **2,2** | 3,2 | 2,9 |
| N conan / N2 (referencia) | 28 / 25 | 14,1 / 13,6 | 1,9 / 3,7 | 12,2 / 11,9 | 4,3 / 5,9 |
| N pydantic / N2 (referencia) | 11 / 5 | 5,7 / 1,4 | 1,3 / −1,2 | 4,9 / 1,1 | 2,2 / −1,0 |

- **A no pasa la regla 5.2 sobre Ne al 25 %** en ninguna cadena (2,2-4,3 %). Al 10 % solo pasa en
  conan (5,9-6,7 %), no en pydantic (2,9 %).
- La regla se queda como la definió 6c: neto con el re-pedido natural. Con el re-pedido medido en
  vivo en A y A2 (0,05-0,095, ninguno entero), el techo de conan sería de ~12 %. Se publica al
  lado como sensibilidad; no cambia el veredicto.
- **Mi hipótesis era falsa.** En conan, Ne no baja el techo de A:
  - se relee menos (34-41 % del coste, frente a ~50 % en N);
  - pero, al compactar, Ne deja más salidas grandes (43-44 frente a 25-28);
  - y el bruto se queda igual (~13,5 %). En pydantic sí es pequeño.
- **El replay sobre N predijo ~12 % (r = 0,10) en conan, y en vivo salió x0,93.** Cuadra en el
  orden de magnitud, pero con dos corridas de A en vivo no se distingue un 7 de un 12 % (e8).
- **Consecuencias**:
  - No hay tanda de pago de A en código largo.
  - El efecto de A sobre Ne, si existe, es menor de lo que este banco puede medir. Aunque pasara
    la regla, la potencia manda: ~43 cadenas para ver un −7 %.
  - A queda archivado para código largo. Su techo se lee con replay, que es determinista.

### Dónde puede pagar Jev en código largo con N-early de listón (sesión b9, 2026-10-08; gratis)

Tres replays sobre las mismas transcripciones (N, N2 y Ne de conan-1; N y Ne de pydantic-1), sin
modelo y sin Jev. Scripts en el scratchpad de la sesión ab95d8a0: `anat_ne.py`, `carry_ne.py`,
`sim_compact.py` y `oracle_compact.py`. Reutilizan el parser de anatomía y `rc.prep`. En `claude -p`
los bugs llegan como mensajes de usuario sin `turnOrigin` humano, así que el parser los archiva como
`umeta`; aquí cuentan como frontera de mensaje.

**1. En qué se va el dinero de Ne** (% del coste reconstruido; conan Ne / Ne2 / pydantic Ne):

| Parte | Ne conan | Ne2 conan | Ne pydantic | N conan (referencia) |
|---|---|---|---|---|
| Lecturas de contexto arrastrado de mensajes anteriores | 39,2 | 42,7 | 47,2 | 73,2 |
| Lecturas del prefijo base (sistema, herramientas, resumen) | 19,6 | 20,7 | 19,8 | 7,9 |
| — de ellas, el resumen de compactación | 4,6 | 5,1 | 2,7 | — |
| Escritura de caché | 23,5 | 19,1 | 16,3 | 8,8 |
| Salida | 15,0 | 13,8 | 15,1 | 8,4 |
| Lecturas del trabajo del propio bug | 2,7 | 3,7 | 1,5 | 1,6 |

**2. ¿Usa un bug el contexto arrastrado?**

- El agente lee y edita por Bash (`grep`, `sed -n`, heredocs de `python`), así que las rutas `.py`
  salen de los comandos. Es una aproximación.
- Llamo "dependencia" a editar un fichero que no se ha mirado en ese bug pero sí antes en el
  segmento:
  - en conan, 4-6 bugs de ~55 (y 6-13 en N);
  - en pydantic, 24 de 57 (Ne) y 34 (N): allí los bugs comparten ficheros.
- Arrastrar el contexto cuesta ~0,11 $ por bug en Ne (6,4-8,0 $ entre ~55 bugs). Volver a leer un
  trozo de fichero con `sed` (~3k tokens) cuesta del orden de 0,02 $.
- **Conservar el arrastre para ahorrarse una relectura no compensa nunca en coste.** Decidir bug a
  bug qué se arrastra solo podría valer por calidad.
- Los bugs que empiezan con poco arrastre (<20k) cuestan más de su propio trabajo que los de mitad
  de segmento: mediana 0,215 frente a 0,114 $ (Ne conan), 0,191 frente a 0,151 $ (Ne2) y 0,113
  frente a 0,095 $ (Ne pydantic). Son entre 9 y 12 bugs por corrida: es una dirección, no un número.

**3. ¿Cuándo compactar? Regla de umbral frente a oráculo.**

- Simulación de primer orden sobre N, que nunca compacta:
  - se compacta al acabar el turno si el contexto pasa de T;
  - cada compactación cuesta 0,145 $ (lo cobrado menos lo reconstruido en Ne2, entre sus 4);
  - se retoma desde S = 30,5k, la mediana de los inicios de segmento de Ne;
  - el comportamiento del agente se queda fijo.
- Calibración:
  - sin compactar, reproduce N: 28,54 frente a 28,45 $ (conan) y 23,64 frente a 23,55 $ (pydantic);
  - con T = 160k, cerca del disparo real de Ne, da 15,1-16,1 $ en conan, frente a 16,7-18,8 $ reales;
  - es algo optimista: Ne hizo un 12-20 % más de peticiones que N.

| | T = 160k (≈ Ne) | Mejor umbral | Oráculo (mejor colocación posible, sabiendo el futuro) | Oráculo sobre el mejor umbral |
|---|---|---|---|---|
| N conan | 15,11 $ (2) | 70k: 11,90 $ (9) | 11,69 $ (9) | **1,8 %** |
| N2 conan | 16,05 $ (3) | 60k: 12,16 $ (11) | 11,92 $ (10) | **2,0 %** |
| N pydantic | 13,54 $ (2) | 60k: 10,76 $ (9) | 10,63 $ (9) | **1,2 %** |

(Entre paréntesis, compactaciones.)

**Respuesta: no he encontrado ningún sitio donde Jev pague en coste en código largo con Ne de
listón.** Cada parte del coste, con su techo:

| Candidato | Techo | Veredicto |
|---|---|---|
| A, pasajes al entrar | 2,2-4,3 % (5a) | No pasa 5.2 |
| Cuándo compactar | Oráculo 1,2-2,0 % sobre una regla de umbral | Ninguna decisión por frontera puede pasar 5.2 |
| Qué sobrevive a la compactación (C, la guardia) | Lecturas del resumen 2,7-5,1 % + reescritura 0,9-1,9 %, aunque el resumen desapareciera entero | Elegir parte de él no llega al 5 %, y no hay pérdida de calidad que recuperar (Ne 37-51) |
| Qué arrastrar entre bugs | Arrastrar cuesta ~5 veces una relectura | En coste, nunca gana a volver a leer |
| Escritura y salida (35-40 %) | — | No son sustituibles por una decisión (B falló) |

**Lo que sí aparece, sin Jev:**

- Compactar antes, al final del turno, con un umbral de 60-70k y el resumen nativo, da entre −20 y
  −25 % frente al umbral de Ne en la simulación.
- **Es una cota superior.** Supone que el agente no relee más tras compactar 9-11 veces en lugar de
  2-4, y el punto 2 dice que algo más relee.
- La calidad con ese número de compactaciones no está medida.
- Es configuración, no Jev:
  - `CLAUDE_CODE_AUTOCOMPACT_PCT_OVERRIDE` sobre una ventana de 100k (el mínimo documentado de
    `CLAUDE_CODE_AUTO_COMPACT_WINDOW`);
  - o `SANCHOPANZA_COMPACT_AT_PERCENT` del plugin de compactación (function hooks, early access),
    que compacta al acabar el turno.
- Las cifras del brazo de enmascarado no valen: supuse el mismo S que un resumen, y en el e2e del
  2026-09-28 el enmascarado dejaba ~2/3 del contexto.

**Potencia, con la desviación de 0,171 entre réplicas:**

- Un −20 % (ln 0,8 = 0,223) se ve con ~5 cadenas al 80 % de potencia.
- Validadas a las 20:35 del 2026-10-08: conan-1, pydantic-1, conan-2 y moto-1. dvc-1 se está
  validando otra vez y conan-3 quedó inválida a 60 (ea1cf55). Con 4 cadenas, la potencia se queda
  algo por debajo del 80 %; con 5 llega.
- No alcanza para leer la calidad (Ne va de 37 a 51 en una misma cadena): habría que decidir antes
  un margen de no inferioridad laxo.
- Es una propuesta al dueño, sin lanzar. No es una apuesta de Jev, y se dice así.

### Compactar antes en código largo: cerrado, sin ahorro demostrado (cierre de contexto, 2026-10-13/14)

Aprobado por el dueño el 2026-10-13. Prerregistro sellado antes de cualquier corrida (cierre-contexto
fb42fa4, verificado contra el código por un subagente independiente). Resultados en
`docs/results/2026-10-13-long-compact/README.md`.

- **Brazos**: Ne (ventana 193.000, compacta cerca de 160k) frente a Nl (ventana 100.000, lo que escribe
  `install --context-budget 67000`, compacta cerca de 67k). Configuración de Claude Code, no Jev.
- Sonnet 5.5, k = 1, 5 cadenas long60: conan-1, pydantic-1, conan-2, moto-1 y moto-2 (validada para
  esta tanda). dvc-1 terminó inválida a 57 bugs. **173,11 $** de 250 duros.
- **Veredicto, con la regla sellada: sin diferencia demostrada (no gana).**
  - Coste Nl/Ne sobre las llamadas comunes: **0,900 [0,741; 1,093]**. Por cadena: 0,966, 0,888, 1,098
    (conan-2), 0,716 y 0,875.
  - Calidad no inferior: −1,4 puntos [−3,8; +1,1], cota unilateral −3,5 frente a −10.
  - Pared: 1,09 [0,85; 1,41]. Nl compacta 12-20 veces por cadena; Ne, 2-4.
  - Abandonos no resueltos: 3 (Ne) y 4 (Nl), ninguno pasado 150k.
- **Sensibilidad que el prerregistro mandaba publicar al lado:** un reinicio del PC (05:04 del 14)
  cortó la llamada 40 de Nl en conan-2. La regla la carga a su tope (4,50 $); costó 0,35 $. Medida a lo
  que costó, el cociente sería 0,858 [0,748; 0,984]. **No cambia el veredicto sellado.** Si se acepta,
  o si se repite conan-2 (~35 $), es decisión del dueño.
- El replay predecía −20 a −25 % (cota optimista). Sale −10 % (−14 % con la sensibilidad): compactar
  cuatro o cinco veces más se paga y obliga a releer.
- Aunque ganara, 67k no sirve de valor por defecto de `install`: la base de contexto de las sesiones
  reales del dueño es de ~68k (prerregistro, sección 9).
- **Consecuencia**: `install --context-budget` se queda en 160.000. En código largo, Jev no tiene
  dónde pagar (sesión b9), y compactar antes, que no es Jev, tampoco demuestra ahorro con 5 cadenas.

### Compactar antes: la repetición de conan-2 tampoco gana (enmienda, 2026-10-15)

Aprobada por el dueño el 2026-10-14 (45 $ duros). Enmienda escrita después de los datos de la tanda y
antes de los de la repetición, sellada en 1c916fe tras una revisión independiente
(`docs/results/2026-10-13-long-compact/amendment-conan2.md`). Resultados en el README de long-compact,
sección "Repetición de conan-2".

- **Qué**: conan-2 otra vez, los mismos brazos (Ne y Nl), Sonnet 5.5, k = 1, raíz nueva, tope de 22,5 $
  por corrida. Corrió el 15 de 08:05 a 10:50, sin reinicios ni incidentes. **33,69 $**; con la tanda,
  206,80 $ de 250.
- **Réplica (R0)**: Nl/Ne 0,952 en 44 llamadas comunes (la tanda: 1,098 sellado, 0,865 medido). Se
  movió porque Ne salió un 10 % más barato que en la tanda; Nl costó lo mismo que medido.
- **Sustitución (R1)**: 0,875 [0,754; 1,015], calidad −2,2 puntos (cota −3,9). **Sin diferencia
  demostrada.**
- **Promedio (R2)**: 0,887 [0,750; 1,050], calidad −1,6 puntos (cota −3,5). **Sin diferencia
  demostrada.**
- **Veredicto**: el sellado sigue siendo el primario, sin diferencia demostrada (no gana). Bajo la
  enmienda posterior a los datos, tampoco gana. Ganar pedía una repetición de 0,916 o menos (R1) y de
  0,764 o menos (R2).
- La nota final, 46 de Nl frente a 40 de Ne, es asimétrica: con el mismo tope, Nl hizo 52 llamadas y Ne
  44. En las comunes, 38 frente a 39.
- **Consecuencia**: nada cambia. `install --context-budget` se queda en 160.000, y la línea de compactar
  antes queda cerrada.

## 7. Lo que no prometemos

- LongBench no tiene palanca de S: su 0,785 es un caso atípico.
- La compactación temprana es configuración de Claude Code. La guardia (Jev eligiendo qué se
  queda) no añadió nada medible en BCP (N-early, 2026-10-07). En sesiones largas sigue sin
  medirse.
- Si A, B y C no pasan su replay, se dice tal cual. No se cambia de métrica para que algo gane.
- **En una cadena larga no hay p por bug** (e8 y 5a, 2026-10-07). El mismo brazo contra sí mismo
  en conan dio McNemar p 0,016 (N frente a N2, 0 frente a 7): los bugs de una cadena no son
  independientes. La unidad de réplica es la corrida. Con k = 2 se publican rangos entre
  corridas y stable_flips con base doble. Con varias cadenas, la inferencia va por cadena.
- Una sola corrida de un brazo en una cadena varía entre 37 y 51 de 60. Cualquier comparación de
  calidad futura necesita al menos dos corridas por brazo y cadena, o más cadenas.
