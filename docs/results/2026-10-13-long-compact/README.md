# Compactar antes en código largo: N-early bajo frente a N-early (cierre de contexto, 2026-10-13/14)

Sesión de la línea contexto / sesiones largas. Prerregistro sellado antes de cualquier corrida:
[`prereg.md`](prereg.md), commit fb42fa4 de la rama `cierre-contexto`, sha256
`fb1bbd537c8752434105538952b6c99ae67d1ce34e4f97e38d98abbfddbd3ae1`, verificado contra el código por
un subagente independiente en dos pasadas. Lectura con `benchmarks/adopt/long_compact.py`
([`read.json`](read.json)).

## Veredicto

**Sin diferencia demostrada (no gana).** Compactar cerca de 67k (Nl) en vez de cerca de 160k (Ne)
cuesta x0,900 de media sobre 5 cadenas, con un IC 95 % de [0,741; 1,093], que contiene el 1. La
calidad es no inferior: −1,4 puntos de bugs resueltos, IC [−3,8; +1,1], cota unilateral −3,5 frente a
un margen de −10. Con la regla sellada, `install --context-budget` no cambia de valor por defecto.

**Repetición de conan-2 (2026-10-15, enmienda posterior a los datos): tampoco gana.** La repetición
da 0,952 en conan-2; sustituida, 0,875 [0,754; 1,015], y promediada con la de la tanda, 0,887
[0,750; 1,050]: sin diferencia demostrada las dos. El veredicto sellado de arriba sigue siendo el
primario. Ver ["Repetición de conan-2"](#repetición-de-conan-2-enmienda-posterior-a-los-datos-2026-10-15).

## Lo que se corrió

- **Brazos** (solo cambia una variable en el `env` del proyecto; ni hooks, ni MCP, ni Jev):
  - Ne: `CLAUDE_CODE_AUTO_COMPACT_WINDOW=193000`, lo que escribe `install --context-budget 160000`.
  - Nl: `CLAUDE_CODE_AUTO_COMPACT_WINDOW=100000`, lo que escribe `install --context-budget 67000`.
- Sonnet 5.5, Claude Code 2.1.287, usuario limpio, k = 1 por brazo y cadena, los dos brazos de cada
  cadena seguidos (orden por `arm_order`).
- **Cadenas** long60: conan-1, pydantic-1, conan-2 y moto-1, más moto-2 (validada para esta tanda,
  4 rondas). dvc-1 terminó inválida a 57 bugs (sin repuestos), así que no hubo sexta.
- Topes: 4,50 $ por llamada, 25 $ por corrida y 250 $ de techo duro en el código. **Gasto: 173,11 $**
  (dólares del dueño, precio de lista; con la suscripción).
- El mecanismo disparó donde decía el prerregistro: 80 compactaciones de Nl con `pre` entre 66.253 y
  73.752 (la primera, 67.358 en la llamada 5 de conan-1); las 18 de Ne, entre 159.643 y 162.755. La
  guarda de Nl no saltó nunca.

## Resultados por cadena

Coste en las llamadas que corrieron los dos brazos (`k`). Calidad: cada brazo puntuado en su
instantánea tras la llamada `k`, sobre los bugs que se habían pedido a los dos.

| Cadena | k | Ne $ | Nl $ | Nl/Ne | Resueltos Ne / Nl (solo Ne, solo Nl) | Compactaciones Ne / Nl | Pared Nl/Ne | Cómo acabaron |
|---|---|---|---|---|---|---|---|---|
| conan-1 | 62 | 19,27 | 18,61 | 0,966 | 59 / 58 de 60 (2, 1) | 4 / 20 | 1,28 | las dos enteras |
| pydantic-1 | 62 | 15,08 | 13,38 | 0,888 | 47 / 48 de 60 (2, 3) | 2 / 12 | 1,22 | las dos enteras |
| conan-2 | 43 | 17,78 | 19,53 | **1,098** | 35 / 36 de 43 (3, 4) | 4 / 15 | 0,77 | las dos por su tope (Ne 44, Nl 43 llamadas) |
| moto-1 | 56 | 19,26 | 13,79 | 0,716 | 54 / 51 de 55 (3, 0) | 4 / 15 | 1,11 | Ne por su tope; Nl entera (14,64 $) |
| moto-2 | 62 | 18,20 | 15,93 | 0,875 | 58 / 56 de 60 (2, 0) | 4 / 18 | 1,18 | las dos enteras |
| **Sobre cadenas** | | | | **0,900 [0,741; 1,093]** | **−1,4 pts [−3,8; +1,1]** | | **1,09 [0,85; 1,41]** | |

- Abandonos no resueltos: Ne 3 (pydantic 2, a 65k y 114k; conan-2 1, a 113k), Nl 4 (pydantic 3,
  a 62-66k; conan-2 1, a 58k). Ninguno pasado 150k. No separan a los brazos.
- Nota final (`grade.json`, parche final de cada brazo): conan-1 59/58, pydantic-1 47/48, conan-2
  37/37, moto-1 55/56, moto-2 58/56 (Ne/Nl).
- Pared: Nl es más lento en 4 de 5 cadenas (compacta 12-20 veces en vez de 2-4); la media 1,09
  [0,85; 1,41] no es medida principal.

## Lectura a mano de lo desfavorable y lo favorable

- **conan-2 es la única cadena en contra, y lleva el reinicio del PC.** El equipo se reinició a las
  05:04 del 14 (evento 109, "Power Action Reboot", motivo "Kernel API") con Nl de conan-2 en la
  llamada 40. Fue Windows Update: el evento 1074 de las 05:16, 12 minutos después, nombra a
  `TrustedInstaller.exe` ("Sistema operativo: actualización (planeada)"), y le sigue otro 109 a las
  05:16:41. *(Corregido el 2026-10-15: aquí decía "ningún evento 1074 dice quién", y era falso. El
  109 de las 05:04 no tiene un 1074 propio; el de las 05:16 sí, y es el de la actualización.)* Al reanudar, el runner cargó esa llamada cortada a su tope de
  4,50 $, como dice el prerregistro (sección 6); medida en su transcripción costó 0,35 $. Ese cargo
  empujó a Nl contra su tope de corrida, que paró en la llamada 43 en lugar de seguir.
  - **Sensibilidad (no cambia el veredicto):** con la llamada 40 a lo que costó, conan-2 da 0,865 y
    el cociente sobre cadenas, **0,858 [0,748; 0,984]**, que ya no contiene el 1. Sin conan-2 (4
    cadenas): 0,856 [0,700; 1,048].
  - El veredicto sellado se queda como está: la regla se escribió antes, incluido el cargo de las
    llamadas cortadas. **Se dice al lado, como pide el prerregistro, y la decisión es del dueño**
    (ver "Para el dueño").
- **moto-1 (0,716) es la cadena más favorable**, y en parte es asimétrica: Ne paró por su tope en
  la llamada 56 (19,26 $) y Nl llegó entera a la 62 con 14,64 $. En las 56 comunes, Nl resolvió 3
  bugs menos (54 frente a 51); en la nota final, 1 más (56 frente a 55), porque siguió.
- **El efecto es menor que lo que predijo el replay** (−20 a −25 %, cota optimista): sale −10 %
  (−14 % con la sensibilidad). Nl compacta 12-20 veces por cadena en vez de 2-4: cada compactación se
  paga (el resumen y reescribir la caché) y tras cada una el agente vuelve a leer.
- **Deriva frente a la tanda del 2026-10-07** (solo como comprobación): Ne de conan-1 resolvió 59
  (antes 37 y 51) con 19,27 $ (antes 17,33 $ entera); Ne de pydantic-1, 47 (antes 44) con 15,08 $
  (antes 13,84 $). Las dos cadenas salieron más fáciles hoy para los dos brazos, y algo más caras.

## Desviaciones e incidencias (todas anotadas al ocurrir)

1. **Reinicio del PC a las 05:04 del 14**: la tanda murió con 0x40010004 a las 05:03:41 (80,06 $
   gastados). Se reanudó a las 10:16 desde el mismo worktree sellado con el mismo lanzador (los brazos
   acabados no se repiten; la llamada a medias se asienta con `long_resume`). Docker Desktop no
   arrancó solo tras el reinicio: el primer relanzamiento (10:15) se negó antes de llamar a nada.
2. **Nota de las cadenas de moto con un tiempo por test** (después del sello). La nota del
   lanzador sobre moto-1 se colgó 16 minutos al 92 % sin CPU (un test de servidor con hilos) y habría
   vuelto sin resultado. Las dos cadenas de moto se puntuaron con `long_compact.py grade
   --test-timeout 300` (el mismo complemento que la validación), los dos brazos igual. En moto-2,
   la nota sellada del lanzador sí terminó y da lo mismo (58 y 56).
3. **La quinta cadena se lanzó a mano** (14:15), al acabar las cuatro, porque el lanzamiento
   automático esperaba un `exit 0` y la nota colgada de moto-1 hubo que pararla por PID.
4. Validación (gratis, antes de sellar): dvc-1 no pasaba de la primera ronda porque un test colgado
   retenía cada ejecución 3.600 s; moto-2 se colgaba igual al 98 %. Arreglado con un tiempo por test
   propio montado en el contenedor (dd5631d, 6778f53, e06f46b). La causa de la muerte de la
   validación de dvc del 8-9 oct no quedó en ningún registro del sistema: cmd, python y el vigilante
   murieron a la vez sin evento de apagado.
5. La sesión de memoria corría su tanda a la vez (carry.py, desde las 00:02); ningún runner vio un
   límite de uso.

## Para el dueño

- **¿Vale la sensibilidad de conan-2?** Con la regla sellada no hay ahorro demostrado. Si se acepta
  medir la llamada cortada por el reinicio a lo que costó, el ahorro sería de un 14 % [2 %; 25 %]
  con calidad no inferior. Repetir solo conan-2 (dos corridas, ~35 $; quedan 77 $ bajo el techo de
  250) zanjaría la duda sin tocar la regla. *(Hecho el 2026-10-15, 33,69 $: tampoco gana. Ver
  "Repetición de conan-2".)*
- Aunque ganara, el prerregistro ya decía (sección 9) que 67k no puede ser el valor por defecto de
  `install`: en las sesiones reales del dueño la base de contexto es de ~68k, y un umbral de 67k
  quedaría por debajo. Haría falta un umbral relativo a la base de cada sesión.
- Opus 5.5: no corrido.

## Repetición de conan-2 (enmienda posterior a los datos, 2026-10-15)

Enmienda [`amendment-conan2.md`](amendment-conan2.md), escrita después de los datos de la tanda y
antes de los de la repetición, sellada en 1c916fe (sha256
`762d421eef480bdeadc30769c1e9e2f30c630d7a3c0cab55c0d004ad0a46bb3e`) tras una revisión independiente.
Lectura con `long_compact.py amend` ([`amend.json`](amend.json)); `read` sigue reproduciendo
[`read.json`](read.json) byte a byte.

**Veredicto sellado, el primario: sigue sin diferencia demostrada (no gana)**, 0,900 [0,741; 1,093].
**Bajo la enmienda posterior a los datos tampoco gana**: R1 y R2 dan las dos "sin diferencia
demostrada". `install --context-budget` se queda en 160.000.

### Lo que se corrió

- Perfil `compact-conan2` en 335cea8, desde un worktree `--detach`, raíz `C:\sp-runs\L-compact-conan2`,
  lanzado por WMI a las 08:05 del 15. Nl de 08:05 a 09:26, Ne de 09:27 a 10:47, nota del lanzador
  hasta las 10:50 (`exit 0` del runner y de la nota).
- Los dos brazos pararon por su tope de corrida de 22,5 $, como estaba previsto: Nl tras la llamada
  52 (17,20 $), Ne tras la 44 (16,49 $). Es una parada del brazo, no de la tanda.
- **Gasto: 33,69 $** (techo 45, duro). Con la tanda: **173,11 + 33,69 = 206,80 $** de los 250.
- Sin incidentes: ningún reinicio (último arranque, 05:17 del 14; ningún evento 109, 1074, 41 ni
  6008 durante la corrida), ningún 429, ninguna llamada cortada ni repetida. Una denegación de
  permiso en la llamada 3 de Ne, que siguió normal.
- Nota común con `long_compact.py grade --root C:\sp-runs\L-compact-conan2 --chains
  conan-io__conan-long60-2`, sin tiempo por test, como la conan-2 de la tanda. No se colgó.

### conan-2: la de la tanda frente a la repetición

| | conan-2 de la tanda (14 oct) | Repetición (15 oct) |
|---|---|---|
| Llamadas comunes | 43 | 44 (se esperaban ~41) |
| Ne $ en las comunes | 17,78 | 16,49 |
| Nl $ en las comunes, sellado | 19,53 (llamada 40 cargada a 4,50) | 15,70 |
| Nl $ en las comunes, medido | 15,38 (llamada 40 a 0,35) | 15,70 (ninguna cortada) |
| **Nl/Ne sellado** | **1,098** | **0,952** |
| Nl/Ne medido | 0,865 | 0,952 |
| Resueltos comunes Ne / Nl (solo Ne, solo Nl) | 35 / 36 de 43 (3, 4) | 39 / 38 de 44 (1, 0) |
| Nota final Ne / Nl (`grade.json`) | 37 / 37 (44 y 43 llamadas) | 40 / 46 (44 y 52 llamadas) |
| Compactaciones Ne / Nl (corrida entera) | 4 / 15 | 3 / 17 |
| Abandonos no resueltos Ne / Nl | 1 / 1 | 0 / 0 |
| Cómo acabaron | las dos por su tope de 25 (Ne 44, Nl 43 llamadas) | las dos por su tope de 22,5 (Ne 44, Nl 52) |

### Las tres lecturas de la enmienda (sección 5)

| Lectura | conan-2 | Coste Nl/Ne sobre 5 cadenas | Calidad Nl − Ne (cota unilateral) | Por `RULE` |
|---|---|---|---|---|
| **R0, réplica** (descriptiva) | 0,952 (tanda: 1,098 sellado, 0,865 medido) | — | — | — |
| **R1, sustitución** | 0,952 | **0,875 [0,754; 1,015]** | −2,2 pts [−4,2; 0,0] (−3,9) | sin diferencia demostrada |
| **R2, promedio** | 1,022 (media geométrica de las dos; 87 pares de bugs) | **0,887 [0,750; 1,050]** | −1,6 pts [−3,8; +0,3] (−3,5) | sin diferencia demostrada |

- **Veredicto de la enmienda** (`amended_verdict`): "R1: no difference shown; R2: no difference
  shown". Ninguna de las dos gana: los dos IC contienen el 1.
- Calculado antes de los datos: R1 ganaba con una repetición entre 0,635 y 0,916, y R2 entre 0,367 y
  0,764. Salió 0,952.
- La calidad sigue siendo no inferior en las dos (cotas −3,9 y −3,5 frente a −10).

### Lectura a mano

- **El mecanismo, igual que en la tanda.** 17 compactaciones de Nl con `pre` entre 66.376 y 70.142
  (la primera, 69.446 en la llamada 3), 16 de ellas en las comunes; las 3 de Ne, entre 160.054 y
  160.545. Contexto pico: Nl 66.879, Ne 159.911. La guarda de Nl no saltó.
- **La repetición cae entre el 1,098 sellado y el 0,865 medido**: el cargo de la llamada cortada
  explicaba buena parte del 1,098, y el 0,865 medido debía otra parte a un Ne caro (siguiente punto).
- **El cociente se movió porque Ne salió más barato, no porque Nl saliera más caro.** En las 43
  primeras llamadas, Ne costó 15,96 $ frente a 17,78 $ en la tanda (−10 %), y Nl 15,27 $ frente a
  15,38 $ medidos (−1 %). Por eso Ne llegó a 44 llamadas comunes y no a las ~41 previstas (la
  previsión pasaba por el tope las filas de Ne de la tanda).
- **Número favorable, leído a mano: la nota final, 46 de Nl frente a 40 de Ne.** Es asimétrica: con el
  mismo tope de 22,5 $, Nl hizo 52 llamadas y Ne 44. En las 44 comunes, Ne resolvió 39 y Nl 38 (1 bug
  solo de Ne, ninguno solo de Nl). No es mejor calidad de Nl. Coste por resuelto en las comunes: Nl
  0,413 $, Ne 0,423 $ (descriptivo).
- Pared en las comunes (suma de `wall_s`): Nl 4.492 s, Ne 4.822 s, 0,93. En la tanda, con la misma
  medida, 0,75. No es medida principal.
- La línea `gate: {'sonnet': 'sin margen'}` de `grade.log` es la puerta genérica de `long_run`, la
  misma que imprimió la tanda; no es la regla de este prerregistro.
- **La regresión a la media que la enmienda temía (sección 6) favorecía a Nl, y aun así no gana.**

### Otra fecha y otra hora (nota posterior al sello de la enmienda)

La enmienda (sección 6) ya dice que la repetición va en otra fecha. Además, **corrió por la mañana**
(08:05-10:47 del 15, los dos brazos seguidos), mientras que en la tanda Nl de conan-2 corrió de
madrugada (04:00-05:03 del 14, y sus tres últimas llamadas a las 10:16-10:20 tras el reinicio) y Ne
por la mañana (10:21-11:53). En la tanda, los dos brazos de conan-2 no quedaron emparejados en el
tiempo; en la repetición, sí. Se anota aquí porque la enmienda está sellada por su sha256 y no admite
notas posteriores.

## Reanudar sin pagar dos veces (si otro reinicio corta algo)

`long-compact-run.cmd` (o `long-compact-run.cmd fifth`) lanzado otra vez desde el worktree sellado
(`git worktree add --detach <ruta> fb42fa4`) por WMI reanuda: los brazos acabados se saltan
("never run twice") y el que se cortó sigue en su siguiente llamada. La llamada a medias se carga a su
tope. Antes, Docker Desktop tiene que estar arriba. El techo de 250 $ cuenta todo lo gastado bajo
`C:\sp-runs\L-compact`.

## Ficheros

- Raíz de la tanda: `C:\sp-runs\L-compact` (filas, transcripciones, diffs, `grade.json`,
  `grade-common.json`, `launch.log`, `runner-sonnet.log`, `grade.log`).
- [`prereg.md`](prereg.md) (sellado), [`read.json`](read.json) (la lectura por la regla).
- Repetición de conan-2: raíz `C:\sp-runs\L-compact-conan2` (las mismas piezas, más `launch.json` y
  `windows.json`); [`amendment-conan2.md`](amendment-conan2.md) (sellada) y
  [`amend.json`](amend.json) (R0, R1, R2 y el veredicto de la enmienda).
