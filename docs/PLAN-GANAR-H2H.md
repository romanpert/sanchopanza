# Plan para que S gane: qué falló en h2h y qué hacemos ahora (2026-10-07)

Escrito por indagis-6c (línea memoria y contexto, banco largo) con indagis-d6 (línea web/h2h, S2).
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
     (`give_ups.unresolved`, 6c). 6c corrige la definición en STATUS-launch.
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

## 7. Lo que no prometemos

- LongBench no tiene palanca de S: su 0,785 es un caso atípico.
- La compactación temprana es configuración de Claude Code. La guardia (Jev eligiendo qué se
  queda) no añadió nada medible en BCP (N-early, 2026-10-07). En sesiones largas sigue sin
  medirse.
- Si A, B y C no pasan su replay, se dice tal cual. No se cambia de métrica para que algo gane.
