# Enmienda al prerregistro: repetir conan-2 (cierre de contexto, 2026-10-14)

Enmienda a [`prereg.md`](prereg.md) (sellado en fb42fa4, sha256
`fb1bbd537c8752434105538952b6c99ae67d1ce34e4f97e38d98abbfddbd3ae1`). Aprobada por el dueño el
2026-10-14, con la suscripción de Claude Code, 45 $ duros.

**Es posterior a los datos.** Se escribe después de leer la tanda del cierre (README, `read.json`)
y antes de cualquier llamada de la repetición. Se sella con su commit y su sha256, y un subagente
independiente la revisa contra el código antes de gastar.

## 1. Por qué se repite

- En `conan-io__conan-long60-2` un reinicio del PC (05:04 del 14, evento 109) cortó la llamada 40
  de Nl. La regla sellada la cargó a su tope de 4,50 $ (sección 6 del prereg); en su transcripción
  costó 0,35 $.
- Ese cargo empujó a Nl contra su tope de corrida: paró en la llamada 43 en lugar de seguir. Por
  eso conan-2 es la única cadena en contra (1,098).
- Con la llamada medida a lo que costó, conan-2 daría 0,865 y el cociente sobre cadenas
  0,858 [0,748; 0,984]. Se publicó al lado, fuera de la regla.
- La repetición mide conan-2 otra vez, sin ese incidente, y deja la duda zanjada sin tocar la
  regla sellada.

## 2. Lo que no cambia

- **El veredicto sellado se queda publicado tal cual como primario**: sin diferencia demostrada (no
  gana), 0,900 [0,741; 1,093]. No se tocan `prereg.md` ni `read.json`, y tampoco las filas de
  `C:\sp-runs\L-compact`.
- La repetición se publica como **réplica declarada** (sensibilidad), con las reglas de la sección 5,
  escritas aquí antes de sus datos.
- `install --context-budget` se queda en 160.000 salga lo que salga (prereg, sección 9: 67k queda
  por debajo de la base de contexto de las sesiones reales del dueño).
- La regla de decisión (`long_compact.RULE`, `verdict`), el margen (−10 puntos), el mínimo de 30
  llamadas comunes con nota común y el mínimo de 5 cadenas son los sellados.
- El cargo de una llamada cortada sigue siendo su tope (4,50 $). Si la repetición tiene otra, se
  carga así y se publica al lado lo que costó, como en la tanda.

## 3. Qué se corre

- **Perfil `compact-conan2`** (`long_run.PROFILES`), en el commit 0696e3a de la rama `conan2-run`.
  Ese commit sale del sellado fb42fa4, y su único cambio es este perfil: su raíz, el argumento
  `conan2` de `long-compact-run.cmd` y sus tests. El runner, los guardas, el contador y
  `carry.py` son los de la tanda sellada.
- Igual que en la tanda:
  - los brazos Ne (ventana 193.000) y Nl (ventana 100.000), sin hooks, MCP ni Jev;
  - Sonnet 5.5, Claude Code 2.1.287 fijado, usuario limpio, k = 1 por brazo;
  - el tope de 4,50 $ por llamada;
  - el orden por `arm_order`: Nl primero y después Ne, seguidos;
  - las guardas de Nl (`LOW_PRE` 50.000-110.000, `LOW_PEAK` 110.000), la del prefijo, y las
    paradas locales por tope o pared.
- **Raíz nueva**: `C:\sp-runs\L-compact-conan2`. No se reutiliza ni se sobrescribe nada de
  `C:\sp-runs\L-compact`.
- **Diferencias declaradas:**
  - **Techo de 45 $, duro en el código** (`COMPACT_CONAN2_CEILING`, `hard_cap`: ninguna línea de
    comandos lo sube). Con la tanda, el gasto bajo el techo de 250 $ queda como mucho en
    173,11 + 45 = 218,11 $ (quedan 76,89).
  - **Tope por corrida de 22,5 $, no 25.** El plan se niega a lanzar si los topes retenidos pasan
    del techo (`long_guard.plan_refusal`), y 2 × 22,5 = 45. Así, Ne no empieza llamadas pasados
    16,36 $ (en la tanda, 18,86 $), ni Nl pasados 16,92 $ (en la tanda, 19,42 $). El techo no puede
    morder antes que el tope de cada corrida.
  - **Consecuencia: menos llamadas comunes.** En la tanda, Ne de conan-2 pasó de 16,36 $ en la
    llamada 40, así que se esperan unas 40 llamadas comunes en lugar de 43. Lo que se compara es
    lo de siempre: las llamadas que corrieron los dos brazos.
  - **Otra fecha**: los dos brazos de la repetición van emparejados en el tiempo entre sí, pero no
    con la conan-2 original. Puede haber deriva del servicio.
- **Estimación**: ~16,5-17,5 $ por brazo, **~34-35 $** en total. El máximo absoluto son 45 $, por
  código.
- **Medianoche**: la cadena entera necesita ~3,2 h, así que la regla del runner la impide pasadas
  ~20:48. Se lanza pasada la medianoche del 15.

## 4. Qué se mide

Lo de la sección 6 del prereg, para una cadena:

- `common_calls`: de la 1 a la última llamada `k` que corrieron los dos brazos.
- **Coste** en esas llamadas, como lo cargó el runner.
- **Nota común**: cada brazo puntuado en su instantánea tras la llamada `k` con
  `long_compact.py grade --root C:\sp-runs\L-compact-conan2 --chains conan-io__conan-long60-2`.
  - Igual que conan-2 en la tanda, va sin tiempo por test: el lanzador la puntuó sin él.
  - Si una nota se cuelga (más de 60 minutos sin avanzar), se paran por PID y los dos brazos de la
    repetición se puntúan con `--test-timeout 300`, igual los dos, y se anota como desviación.
- Además, la nota final (`grade.json`), las compactaciones y su `pre`, el contexto pico, los
  abandonos no resueltos, cómo acabó cada corrida y la pared.

## 5. Cómo se combina (`long_compact.py amend`, escrito y probado antes de los datos)

Cada lectura cuenta conan-2 solo si la repetición tiene al menos 30 llamadas comunes y nota común de
los dos brazos (`counts`). Si no, **no hay lectura enmendada**: queda el veredicto sellado y se
publica el gasto.

| Lectura | Qué es | Regla |
|---|---|---|
| **R0, réplica** | El cociente Nl/Ne de la repetición en sus llamadas comunes, al lado del original (1,098 sellado; 0,865 con la llamada medida) | Descriptiva |
| **R1, sustitución** | Las 5 cadenas de la tanda, con la línea de conan-2 cambiada por la de la repetición (su coste común, su nota común) | `RULE` sellada |
| **R2, promedio** | Las 5 cadenas, con conan-2 como las dos corridas juntas. Coste de cada brazo: la media geométrica de sus dos costes comunes, así que el log-cociente es la media de los dos. Calidad: los pares de bugs de las dos corridas en un solo grupo (se remuestrea entero) | `RULE` sellada |

- R2 usa la conan-2 original **tal como la leyó la regla sellada** (con el cargo de 4,50 $), no
  la medida. Por eso es la lectura más conservadora.
- **Veredicto de la enmienda**:
  - **"gana bajo la enmienda"** solo si R1 y R2 dan "gana" las dos;
  - si solo R1 da "gana", se publica literalmente: "gana con la sustitución, no con el promedio (R2:
    <veredicto>)". No se resume como que gana;
  - en otro caso, el veredicto de R1 y el de R2, cada uno con su nombre.
- **Qué hace falta, con las otras cuatro cadenas fijas** (calculado antes de los datos, solo coste):
  - el IC de R1 queda entero por debajo de 1 si el cociente de la repetición cae entre 0,635 y
    0,916;
  - el de R2, entre 0,367 y 0,764.
  - Por debajo del primer número de cada par, la dispersión entre cadenas ensancha el IC.
  - Como referencia, la conan-2 medida de la tanda (0,865) daría "gana" con R1 y no con R2.

## 6. Lo que esta repetición no puede decir (escrito antes de sus datos)

- **Es selectiva.** Se repite la única cadena en contra, la del incidente; las favorables no se
  repiten (moto-1, 0,716, es asimétrica: Ne paró por su tope). Si conan-2 tuvo mala suerte además del
  cargo, la regresión a la media favorece a Nl en la repetición. Por eso el primario sellado sigue
  siendo el primario.
- k = 1 también aquí. El ruido entre réplicas de un mismo brazo es grande: dos Ne en conan-1
  resolvieron 37 y 51.
- Otra fecha y un tope por corrida distinto (22,5 $): la repetición no es la conan-2 de la tanda
  corrida otra vez, sino otra medida de la misma cadena con los mismos brazos.
- Aunque la enmienda diera "gana", no cambia el valor por defecto de `install` (sección 2).

## 7. Paradas, vigilancia y reanudar sin pagar dos veces

- Las de la sección 8 del prereg:
  - **429, límite de uso o aviso de límite**: `C:\sp-runs\LIMIT.flag`, NOT RUN para el resto del
    brazo y salida con 2. **Sin reintentos en bucle**: reanudar lo decide el dueño;
  - `STOP`, Docker caído, disco por debajo de 30 GB: para la tanda;
  - tope de corrida: para ese brazo y sigue el siguiente.
- Si la sesión de memoria tiene su tanda en marcha, se lanza igual y se anota (la pared no es
  medida principal).
- Vigilancia en vivo: `long-run.status.json` y `runner-sonnet.log` en la raíz nueva.
- **Reanudar**: se vuelve a lanzar `long-compact-run.cmd conan2` desde el mismo worktree
  `--detach` en 0696e3a.
  - Los brazos acabados se saltan, y el cortado sigue en su llamada siguiente (`long_resume`).
  - La llamada a medias se carga a su tope.
  - El techo de 45 $ cuenta todo lo gastado bajo la raíz nueva, así que una reanudación nunca pasa de
    45 $ en total.

## 8. Lanzamiento y publicación

1. **Gratis**:
   - los tests (`test_adopt_long_compact.py`, con `long-compact-run.cmd conan2 dry`, y
     `test_adopt_long_compact_read.py`, con `amend`);
   - `long_launch.py plan compact-conan2`, que da 45,00 retenidos, techo 45,00 duro y ventanas
     193.000 / 100.000.
2. **De pago**:
   - `git worktree add --detach <ruta> 0696e3a`;
   - Docker arriba;
   - `long-compact-run.cmd conan2` lanzado por WMI (`Win32_Process.Create`, `CreateFlags 512`), fuera
     de cualquier sesión, pasada la medianoche. Los PIDs quedan en `launch.json` de la raíz nueva.
3. **Al acabar**:
   - `long_compact.py grade` (nota común de la repetición);
   - `long_compact.py amend --json docs/results/2026-10-13-long-compact/amend.json`;
   - se lee a mano cada fallo y cada número favorable.
4. **Dónde se publica**:
   - una sección nueva en el README de long-compact;
   - la subsección del cierre en `docs/PLAN-GANAR-H2H.md`.
5. **El marcador** (`docs/results/2026-10-13-final/README.md`, `docs/results/README.md`,
   `README.md`, `where-it-pays.md`, `CHANGELOG.md`):
   - conserva "no gana" como veredicto sellado;
   - si la enmienda dice algo distinto, se añade al lado con su nombre ("bajo la enmienda posterior
     a los datos"), sin reescribir el primario.
