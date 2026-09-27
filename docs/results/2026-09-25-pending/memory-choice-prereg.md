# Pre-registro: `memory_write` como una sola pregunta Choice

Escrito el 2026-09-25, **antes de cualquier llamada** con esta pregunta. Ninguna respuesta de
Jev a esta pregunta existía cuando se escribió este fichero (el fixture
`memory-choice.jsonl` no existía). El script `benchmarks/pending/memory_choice.py --live` se
niega a ejecutarse si este fichero no cita el hash de la pregunta.

**Hash de la pregunta (sha256 de `asdict(QUESTION)`, 16 hex): `e382c91e96b1aed3`**

## Hipótesis

La infografía del fabricante propone decidir una escritura de memoria con **una** pregunta
Choice (largo plazo / solo sesión / descartar). Sanchopanza hace tres Truth (`durable`,
`specific`, `derivable`) y las combina en `decide_write`. Choice es la primitiva mejor
calibrada que hemos medido (ECE 0,035 en 392 decisiones de otros puntos). La pregunta es si
el **formato** Choice, con el mismo contenido, decide mejor, peor o igual que la política
enviada sobre los mismos casos.

## La pregunta, exacta

Clave de la pregunta `where`, punto `memory_write_choice`, estado `{"fact": <fact>}` (igual
que la línea base de `benchmarks/memory_common.py`, que tampoco pasa `source`; seis casos de
`memory.jsonl`/`memory-b.jsonl` traen `source` y se ignora en los dos brazos por igual).

Instrucciones:

> An agent keeps two stores: a long-term memory that is read again in every later task, and
> the working context of the task in progress. Where does `fact` belong?

Opciones (texto literal; el código en `memory_choice.py` es la fuente y el hash lo fija):

- `long_term` — what: "It will still be true and still matter after the current task is
  finished (a stable property of a person, organization, case or system; a decision taken and
  why; a constraint, preference or rule that will apply again), AND it is concrete: it names
  the entity and states the value, outcome or reason, AND it cannot be recovered cheaply and
  exactly by re-reading a source the agent already has: it is a conclusion, a reconciliation
  between sources, a negative result, or something the agent learned by doing and would have
  to redo". Examples: "the registry only serves rulings from 2018 onward"; "the client asked
  for the report in Spanish"; "we ruled out the 2019 case: different defendant with the same
  name"; "the two registries disagree on the depth; the official one is SGC"; "the portal
  rejects requests without a referer header".
- `session_only` — what: "It matters only for the task in progress: the state of the current
  step, a transient value, a plan for the next few minutes, or a restatement of the task that
  was just given". Examples: "we are on search number four"; "the page is loading slowly
  today"; "the user asked us to investigate this company".
- `drop` — what: "It is not worth keeping at all: a generality, a summary of the obvious, or
  a pointer with no content; or a verbatim copy of, or a direct lookup in, something durable
  and reachable (a file in the repository, a row in the database, a document already
  downloaded) that can be re-read exactly at any time". Examples: "there is relevant
  information about the company"; "defamation law has changed over the years"; "the function
  is defined in agent/harness/motor.py"; "the ruling's text says '500,000 pesos' in its third
  page".

**Contenido constante a propósito.** Cada opción traduce los criterios y los ejemplos de las
tres preguntas enviadas (`points/memory.py`, `write_questions`). No se añade nada de lo que
enseñaron los lotes de memoria: ni la cláusula de conocimiento general de `common`, ni nada
sobre instrucciones del cliente más allá de lo que ya decía `durable`. Ningún ejemplo sale de
un banco (comprobado con grep). Lo que se prueba es el formato, no una pregunta mejor
informada.

## Casos

Todos los `memory_write` etiquetados: `memory.jsonl` (16), `memory-b.jsonl` (34),
`memory-c.jsonl` (50), `memory-e.jsonl` (48), `memory-f.jsonl` (36), `memory-g.jsonl` (24) =
**208**, con los lotes que usa `memory_common.py` (`old` = los 100 primeros, `new`, `new2`,
`new3`). Etiquetas: las del autor, sin cambios.

**Contaminación declarada.** El autor de esta pregunta leyó `memory.md` (familias y fallos)
antes de escribirla. Ningún lote es ciego al diseño. La mitigación es la de arriba (solo
contenido enviado), pero incluso un resultado "mejor" aquí sería evidencia dentro de muestra
para el diseño, y no justificaría cambiar un defecto sin un lote nuevo escrito antes.

## Línea base

La política enviada (`memory.decide_write`, umbrales por defecto) sobre la llamada de tres
preguntas **grabada**, reproducida desde `fixtures/*.jsonl` como hace `memory_common.py`. El
script aborta si algún veredicto difiere de la columna `shipped` de
`docs/results/2026-09-25-window/memory-common.json`. Cifras de la línea base, ya publicadas
y comprobadas antes de llamar: 130/208, 11 errores caros (70/7, 25/3, 23/1, 12/0 por lote).

## Políticas del brazo Choice

- **Primaria (C1):** `store` si y solo si la opción elegida (argmax) es `long_term`. Sin
  umbral: no se elige ningún número.
- **Secundaria (C2):** `store` si `P(long_term) >= 0,70`, el valor enviado de
  `Thresholds.remember`. No derivado de estos casos; se informa, no decide.

No se derivará ningún umbral sobre estos casos.

## Métricas

- Acuerdo con la etiqueta (k/n, Wilson 95 %), total y por lote; por familia en e/f/g.
- **Error caro** (definición de `memory.md`): guardar lo que debería descartarse
  (`predicho store`, etiqueta `skip`). Se cuenta también el error seguro (no guardar lo que
  debía guardarse).
- Respuestas vacías o llamadas fallidas: cuentan como `skip` (el defecto del harness) y se
  informan aparte.

## Comparación y regla de decisión (sobre C1, los 208 casos)

Pareada, mismos casos. McNemar exacto (`eval/stats.mcnemar`) sobre acierto; IC bootstrap de
la diferencia (`bootstrap_difference`, semilla 7); McNemar exacto sobre el indicador de
error caro en los casos etiquetados `skip`.

- **PEOR** si el acuerdo es significativamente menor (p < 0,05) **o** los errores caros son
  significativamente más (p < 0,05, discordantes en contra de Choice).
- **MEJOR** si el acuerdo es significativamente mayor (p < 0,05) **y** los errores caros de
  Choice son ≤ 11.
- **INTERCAMBIO** si el acuerdo es significativamente mayor pero con más de 11 errores caros
  (no significativos).
- **INDISTINGUIBLE** en cualquier otro caso.

Sea cual sea el resultado, **no se cambia ningún defecto**. Un "mejor" justificaría un lote
nuevo escrito antes y un segundo anotador, no un cambio.

## Calibración

- ECE de `P(long_term)` frente a `store` (binaria, `stats.ece`, 5 cajas iguales), junto a
  AUC y Brier. Misma construcción que el 0,227 publicado de `memory_write`, cuyo "probabilidad"
  es `min(durable, specific, 1 - derivable)`: **un mínimo de tres probabilidades no es una
  probabilidad**, así que comparar ese ECE con el de una distribución Choice no es comparar
  primitivas. Se da la ECE del compuesto en los mismos 208 casos (0,142, medida antes de
  llamar) para que la comparación sea al menos sobre los mismos casos.
- ECE de confianza declarada frente a acierto (la construcción del 0,035 de la primitiva).
- **Sesgo del estimador.** Para cada ECE se da el ECE esperado de un modelo *perfectamente*
  calibrado con las mismas probabilidades (2.000 simulaciones, semilla 7; media y p95). Una
  ECE por debajo de ese p95 no se distingue de calibración perfecta a este n, y una
  diferencia entre dos ECE menor que ese suelo no se lee.

## Gasto

Tope duro en el script: 0,05 USD. Esperado: 208 llamadas × ~1.000 tokens × 0,042 $/MTok ≈
0,009 USD. Cada respuesta se graba una vez en `memory-choice.jsonl` y toda re-ejecución la
reproduce; si una llamada falla, una segunda ejecución la reintenta una vez y lo que siga
fallando es abstención. No se repite ninguna llamada para obtener otra respuesta.
