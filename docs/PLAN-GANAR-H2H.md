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
| d6 | **S2** para las suites de una pregunta: `--guard --guard-profile coding --context-budget 160000 --check-done --provider jev`, chooser keep. Fuera memory, candor, fetch, crawl, find, find-auto, skill, scan-content y prune. El brazo S2F (S2 + fetch v3) en el dev de GAIA, para medir fetch justo donde actúa | Dev en preparación, techo 20 $; prereg con margen a la semiamplitud y medida por mecanismo |
| d6 | D y E (parada temprana en la búsqueda, check-done más exigente) | Por diseñar |
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

## 7. Lo que no prometemos

- LongBench no tiene palanca de S: su 0,785 es un caso atípico.
- La compactación temprana es configuración de Claude Code. Lo que aporta Jev ahí es la guardia,
  y eso está por demostrar en sesiones largas.
- Si A, B y C no pasan su replay, se dice tal cual. No se cambia de métrica para que algo gane.
