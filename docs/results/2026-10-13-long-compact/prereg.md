# Prerregistro: N-early frente a N-early bajo en el banco largo (cierre de contexto, 2026-10-13)

Sesión de la línea contexto / sesiones largas. Aprobado por el dueño hoy, con la suscripción de
Claude Code: cerrar la propuesta de `docs/PLAN-GANAR-H2H.md`, sección 6, "Dónde puede pagar Jev en
código largo con N-early de listón". **No es una apuesta de Jev: es configuración de Claude Code.**
Escrito antes de cualquier corrida de esta tanda; se sella con su commit y su sha256, y lo verifica
contra el código un subagente independiente antes de lanzar.

## 1. Pregunta

¿Compactar antes, cerca de 67k en vez de cerca de 160k, abarata el código largo frente a N-early
(el listón actual) sin una pérdida de calidad mayor que el margen fijado aquí?

- Predicción gratis (replay de indagis-b9, 2026-10-08): compactar al final del turno con umbral
  de 60-70k daba entre −20 y −25 % frente al umbral de Ne. **Es una cota optimista**: supone que el
  agente no relee más tras 9-11 compactaciones en lugar de 2-4, y la calidad no estaba medida.
- Si gana, el candidato es cambiar el valor por defecto de `sanchopanza install --context-budget`.
  Ver la sección 9: este banco no basta por sí solo para ese cambio.

## 2. Brazos

Los dos son N (Claude Code 2.1.287 limpio, usuario limpio, `carry.py`) más una sola variable en el
bloque `env` de `.claude/settings.json` del proyecto. Nada más cambia: ni hooks, ni MCP, ni Jev.

| Brazo | Código | `CLAUDE_CODE_AUTO_COMPACT_WINDOW` | Es lo que escribe | Compacta cerca de |
|---|---|---|---|---|
| **Ne** (N-early, el listón) | `long_run.arm_spec("Ne")` | 193.000 | `install --context-budget 160000` | 160k |
| **Nl** (N-early bajo) | `long_run.arm_spec("Nl")` | 100.000 | `install --context-budget 67000` | 67k |

- **Mecanismo.** Claude Code compacta en `ventana − 20k − 13k` (`install_defaults.COMPACT_MARGIN`,
  leído del binario). 100.000 es el mínimo que admite la variable, y `install` acepta como
  presupuesto mínimo 67.000 (`install_defaults.MIN_BUDGET`). Compacta antes de cada petición a la
  API, también a mitad de turno: no es la regla "al final del turno" del replay. Se elige porque es
  exactamente lo que un usuario obtendría con `install`, sin código nuevo.
- **Comprobación de que dispara donde se dice:**
  - con 2.1.287 y ventana 100.000, el humo del 2026-10-07 (Haiku, `C:\sp-runs\L-smoke`, brazo Ne)
    compactó con `pre` 67.753 y 67.443;
  - con Sonnet 5.5 y ventana 193.000, las corridas Ne del 2026-10-07 compactaron con `pre` entre
    159.911 y 161.205 (10 compactaciones en `L-ne` y `L-ne2c`): la misma fórmula, en este modelo;
  - en seco (gratis): el lanzador escribe 193.000 y 100.000 en el `env` de cada brazo y el plan los
    imprime (`tests/test_adopt_long_compact.py`, con un `claude` de mentira);
  - **en vivo, guarda que para la tanda**: si una compactación de Nl tiene `pre` fuera de
    50.000-110.000 o una llamada de Nl pasa de 130.000 de contexto, la llamada rompe un invariante,
    se escribe `STOP` y la tanda para (`long_run.low_window_breaks`, `LOW_PRE`, `LOW_PEAK`). Así, si
    la variable no surtiera efecto, se pierde como mucho una llamada de Nl, no una corrida.
  - Además, Ne y Nl deben tener el mismo prefijo en su primera petición (±50 tokens,
    `long_guard.prefix_breaks`); si no, `STOP`.

## 3. Cadenas

Cadenas long60 validadas (60 bugs, `benchmarks/adopt/long60/<cadena>.json`, con manifiesto y
digest comprobados por el lanzador): **conan-1, pydantic-1, conan-2 y moto-1**, más una quinta.

- **Quinta cadena**, regla fijada antes de conocer ninguna validación: `getmoto__moto-long60-2` si
  valida; si no, `iterative__dvc-long60-1` si valida; si no, la tanda no se lanza con 4 y se valida
  la siguiente reserva antes (decide el dueño).
  - Por qué moto-2: dvc-1 no había conseguido terminar una ronda de validación en tres intentos; la
    primera reserva en el orden sorteado (`long.RESERVE60`) cuyo repositorio no tiene ya dos cadenas
    validadas es moto-2 (conan-4, -5 y -6 se saltan porque conan ya tiene conan-1 y conan-2). Es un
    criterio de metadatos, no de resultados.
- **Sexta cadena, condicional**: la que de {moto-2, dvc-1} no sea la quinta, si valida antes de que
  acabe la tanda de cinco y lo gastado + 50 $ cabe bajo los 250 $ duros. Corre con el perfil
  `compact-extra`, en la misma raíz y con el mismo techo, y se lee junto a las demás.
- **Lo que pone el sello** (sección 11) es la lista final de `long_run.COMPACT_CHAINS` y
  `COMPACT_EXTRA`.

## 4. Diseño

- **Modelo**: Sonnet 5.5 (`claude-sonnet-5-5`), Claude Code 2.1.287 fijado (`claude-pin`).
- **k = 1 por brazo y cadena.** La unidad de réplica es la corrida (sección 7 del plan); la
  inferencia va por cadena.
- **Emparejadas e intercaladas**: los dos brazos de una cadena corren uno detrás del otro, en el
  orden que da `long_run.arm_order` (rotación por el sha256 del nombre de la cadena; no lo elijo
  yo). Con estas cadenas, Ne va primero en conan-1, moto-1 y dvc-1, y Nl en pydantic-1, conan-2 y
  moto-2. Las cadenas, en el orden de `COMPACT_CHAINS`.
- **No se reutilizan las Ne del 2026-10-07** (conan-1: Ne y Ne2; pydantic-1: Ne). Motivos:
  1. emparejar en el tiempo: mismas fechas de servicio del modelo y misma versión de servidor para
     los dos brazos de cada cadena;
  2. conan-1 tiene dos Ne (37 y 51 resueltos, 17,33 y 19,37 $): reutilizar obligaría a elegir una,
     y cualquier elección sería discutible;
  3. Ne2 de conan paró por su tope en la llamada 52.
  Las Ne viejas se publican al lado solo como comprobación de deriva (coste de Ne nuevo frente al
  viejo en la misma cadena), sin entrar en ninguna cuenta.
- **Medianoche**: el runner no empieza una cadena (los dos brazos, ~3,2 h) que cruzaría la
  medianoche (la fecha del prompt cambia y la caché falla). La tanda se lanza pasada la medianoche;
  si una cadena no cabe en el día, el runner para y se relanza al día siguiente (reanuda).
- **Raíz**: `C:\sp-runs\L-compact`, nueva y vacía.

## 5. Topes y gasto

- Precio: dólares del dueño (`meter.OWNER_RATES`, lista de la API), calculados de cada transcripción.
  La tanda corre con la suscripción; el dólar es la unidad del libro de cuentas, no una factura.
- **4,50 $ por llamada, 25 $ por corrida (brazo y cadena), 250 $ de techo duro en el código**
  (`long_run.COMPACT_CEILING`, `hard_cap`: ninguna línea de comandos lo sube). Una llamada solo
  empieza si caben su tope y un turno más bajo el tope de la corrida y bajo el techo: en la
  práctica, Ne no empieza llamadas pasados ~18,9 $ y Nl pasados ~19,4 $.
- Cinco cadenas: 5 × 2 × 25 = 250 $ retenidos al empezar. La sexta solo si cabe (sección 3).
- **Estimación**: con Ne de 2026-10-07 (conan 17,33 $ entero; pydantic 13,84 $) y Nl a x0,75-0,85,
  ~27-34 $ por cadena, **~135-175 $ las cinco**. Si todas las corridas llegan a su tope, cada una
  acaba entre ~19 y 25 $ (~200-215 $ en total, de forma realista); el máximo absoluto es 250 $,
  por código. Por encima de 250 $ no se lanza.
- Una corrida parada por su tope deja su cadena para comparar en las llamadas comunes (sección 6);
  la tanda sigue con el brazo siguiente (`Profile.local_stops = ("cap", "wall")`).

## 6. Medidas

Script: `benchmarks/adopt/long_compact.py` (lee filas, notas y diffs; gratis). Notas con
`long_run.py grade` (Docker, gratis) si el lanzador no las pone solo.

- **Principal: el cociente de coste Nl/Ne por cadena**, sobre las llamadas que corrieron los dos
  brazos (`common_calls`: de la 1 a la última que corrieron ambos). Sobre las cadenas:
  `long_report.cost_ratio` (media pareada de ln(Nl/Ne), IC 95 % de t). Cuenta una cadena con al
  menos 30 llamadas comunes.
- **Calidad**: bugs resueltos (`grade.json`, F2P por bug) en los bugs que corrieron los dos dentro
  de las llamadas comunes. Diferencia Nl − Ne en tasa de resueltos con `long_report.cluster_bootstrap`
  (se remuestrean cadenas enteras, 10.000 réplicas, semilla 20261005) y su cota inferior unilateral
  al 95 % (`one_sided_low`).
- **Se registran y publican** (descriptivos, sin p por bug): compactaciones por corrida y su `pre`;
  contexto pico; abandonos y abandonos no resueltos (`long_report.give_ups`, con su contexto); coste
  por bug resuelto; cómo acabó cada corrida; el cociente de coste total cuando las dos acaban.

## 7. Regla de decisión (fijada aquí; `long_compact.RULE` y `verdict`)

Margen de no inferioridad: **−10 puntos** de tasa de resueltos (6 bugs de 60 de media por cadena).
Es laxo a propósito: una sola corrida de Ne varió entre 37 y 51 resueltos en la misma cadena.

| Coste: IC 95 % del cociente Nl/Ne | Calidad: cota unilateral 95 % de Nl − Ne | Veredicto |
|---|---|---|
| entero por debajo de 1 | por encima de −10 pts | **gana** |
| entero por debajo de 1 | no por encima de −10 pts | **más barato, calidad no demostrada** |
| contiene el 1 | — | **sin diferencia demostrada** |
| entero por encima de 1 | — | **más caro** |
| menos de 5 cadenas con ≥ 30 llamadas comunes | — | **sin veredicto** |

- "Más barato, calidad no demostrada" no se lee como "pierde calidad": se publica la estimación
  puntual y su intervalo, y decide el dueño.
- Nada de esto se cambia después de ver datos. Si algo de la regla resulta inaplicable, se dice y se
  publica la tabla sin veredicto.

**Potencia** (simulada con la regla de arriba; `cost_ratio` usa la t de Student):

| Desviación del log-cociente por cadena | Efecto real | 5 cadenas | 6 cadenas |
|---|---|---|---|
| 0,171 (entre réplicas del mismo brazo, e8) | −25 % | 0,80 | 0,91 |
| 0,171 | −20 % | 0,60 | 0,73 |
| 0,171 | −15 % | 0,37 | 0,47 |
| 0,25 (si el efecto varía entre cadenas) | −20 % | 0,33 | 0,42 |

- Corrección a la nota del plan: "un −20 % se ve con ~5 cadenas al 80 %" salía de una aproximación
  normal. Con la t que usa `cost_ratio`, 5 cadenas dan ~60 % para −20 % y ~80 % para −25 %.
- En calidad, con la dispersión entre réplicas (diferencias de 1 a 14 bugs por cadena), si Nl y Ne
  son iguales la no inferioridad a −10 puntos se demuestra aproximadamente 6 de cada 10 veces.

## 8. Paradas

- **429 o límite de uso**: el runner escribe `C:\sp-runs\LIMIT.flag` (lo ven todos los runners
  largos de la máquina), marca el resto NOT RUN y sale con 2. **No hay
  reintentos en bucle**: reanudar tras el reinicio del límite lo decide el dueño.
- `STOP` en la raíz (a mano o por un invariante roto: init distinto, diff que desaparece, prefijo
  distinto, la guarda de Nl), Docker caído, disco por debajo de 30 GB: para la tanda.
- Tope de la corrida: para ese brazo; sigue el siguiente. Techo: para la tanda.
- Vigilancia en vivo del gasto: `long-run.status.json` y `runner-sonnet.log` en la raíz.

## 9. Lo que este banco no dice (escrito antes de los datos)

- **Prefijo.** En el banco, la primera petición lleva ~15,8k de prefijo y tras compactar quedan
  5-10k. En las 160 sesiones de 100 llamadas o más del dueño (de 1.283), la base de contexto era de
  ~68k (`install_defaults`): allí, en el replay, una ventana de 100k "thrasheaba" (133 % del coste). Aunque Nl gane aquí, **no basta para
  poner 67.000 de valor por defecto de `install --context-budget`**: haría falta un umbral relativo
  a la base de cada sesión, o medirlo en sesiones con prefijo grande. Ese cambio sería decisión del
  dueño.
- k = 1 por cadena: la calidad de una corrida concreta varía mucho; solo vale el agregado.
- Cinco repositorios como mucho (conan ×2, pydantic, moto ×1-2, dvc): no es una muestra del código
  del dueño.

## 10. Lanzamiento

1. Preflight gratis desde el commit sellado: `long_launch.py plan compact`, los tests de
   `test_adopt_long_compact*.py` y el lanzamiento en seco (`long-compact-run.cmd dry`).
2. Tanda de pago: `git worktree add --detach` en el commit sellado (los hooks y el runner se leen
   del disco); `long-compact-run.cmd` lanzado por WMI (`Win32_Process.Create`, `CreateFlags 512`),
   fuera de cualquier sesión. PIDs en `launch.json` de la raíz; se para solo por PID verificado.
3. Si la sesión de memoria tiene su tanda en marcha, se lanza igual y se anota (el tiempo de pared
   no es una medida principal).

## 11. Sello

Se rellena en el commit que sella (lista de cadenas, sha256 de este fichero y commit).
