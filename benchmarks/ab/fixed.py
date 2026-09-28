"""The fetch-heavy A/B with the document sequence held fixed in both arms.

    python -m benchmarks.ab.fixed --dry-run              # the plan and the bill, no API calls
    python -m benchmarks.ab.fixed --repeats 3 --docs 20 --out benchmarks/ab/results/<date>
    python -m benchmarks.ab.fixed --lever pages --fake --corpus-ref HEAD --repeats 1
                                                         # whole pipeline, fake decider, free
    python -m benchmarks.ab.fixed --lever pages --via claude-cli --corpus-ref <sha> ...
                                                         # answers through `claude -p`

`--lever pages` is described in `pages.py`: the shipped in-context tournament over passages,
the answer to the two failure shapes of the 2026-09-24 triage run.

## Why this exists, and why it is not `run.py --lever redundancy`

A fetch-heavy A/B (`docs/paper.md` Section 5.15, `docs/where-it-pays.md` Section 6) needs the
fetch sequence held fixed: the free-loop pilot of 2026-09-24 could not settle it. The reason is a
design flaw, not a sample size:

> An avoidance lever can only act on what the agent fetches, and the run that fetches many
> redundant sources is the run that was already going badly. The lever's opportunity is
> correlated with the arm having a bad draw, so pairing on (task, repetition) does not
> isolate it.

That is what produced the 48 % "saving" that was not there: the bare arm wandered through
eight documents and nine turns against four and five, and the number measured the agent's
search-path variance. The prescription in the same paragraph is explicit - **both arms must
be driven through the same fixed document sequence, so that the only remaining difference is
what the squire removes from it** - and that is what this file does.

## What changes, and what it costs in realism

The agent stops choosing. For each task the retriever returns a deterministic ranked list,
the harness walks it in order, every document goes through the lever (or not), and the
survivors are handed to one model call that answers. Both arms therefore see **byte-identical
input before the squire acts**, and the paired difference is the lever and nothing else.

The honest cost of that: this is no longer an agent loop, it is a pipeline. It cannot say
anything about how a lever changes an agent's *behaviour* - whether it re-fetches, gives up
early, or burns turns. It answers one question cleanly instead of four questions muddily, and
that is the trade `run.py` could not make. **Both files stay**: `run.py` measures the loop,
this measures the lever.

## What is pre-registered here, before any money is spent

Recorded in advance, as Section 6 asks: a real effect on input tokens, a smaller one on cost,
and quality holding. If quality drops, the lever is removing documents the answer needed, and
the token saving is the cost of not answering - the same shape as the search router that
routed into a hole. That is why `--dry-run` prints the bill and why correctness is reported
beside every cost figure and never on its own.

## The counter lesson, applied

The 48 % ghost survived partly because the summary's drop row read the **triage** list while
a redundancy run was being measured, so it printed `drop 0` whether the point dropped
everything or nothing. Here both lists are reported always, and a run whose lever dropped
nothing is labelled **uninformative** in the summary, with the reason, instead of publishing
a difference of zero as a result.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
for ruta in (str(AQUI), str(RAIZ / "src"), str(RAIZ / "benchmarks")):
    if ruta not in sys.path:
        sys.path.insert(0, ruta)

from corpus import Document, build, search  # noqa: E402
from meter import PRICES, Usage  # noqa: E402
from pages import (  # noqa: E402
    EveryQuestion,
    check_reusable,
    fake_answer,
    git_reader,
    trim_by_pages,
)
from run import (  # noqa: E402
    CONDICIONES,
    MODELO_POR_DEFECTO,
    Ejecucion,
    _texto_de_pagina,
    acierta,
    bootstrap_ratio,
    verificar,
)

from sanchopanza.eval.stats import wilson  # noqa: E402
from sanchopanza.policy import Thresholds  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.squire import Squire  # noqa: E402

SISTEMA = (
    "You are a research assistant. The user's question is followed by the documents that a "
    "search returned, in the order the search ranked them. Some are irrelevant and some "
    "repeat each other. Answer the question from these documents only. If a document was "
    "withheld you will see a one-line note in its place; work with what remains. Be brief "
    "and state the figures exactly as the documents give them."
)

# Documentos por tarea. El experimento se llama fetch-heavy porque la mayoria tienen que
# sobrar: con `answer_in` de 1 a 4 sobre este corpus, 20 deja 16 a 19 fuera de proposito,
# que es la forma de carga que la evitacion necesita para poder demostrar algo.
DOCS_POR_TAREA = 20


def _secuencia(documentos: list[Document], tarea: dict[str, Any], cuantos: int) -> list[Document]:
    """La lista que ven los DOS brazos. Deterministica: misma consulta, mismo orden.

    Se pide por la pregunta de la tarea, no por una consulta escrita a mano, para que nadie
    pueda elegir una que favorezca a un brazo. Y se comprueba que los documentos que
    contienen la respuesta estan dentro: una secuencia sin la respuesta mide la incapacidad
    del buscador, no la de la palanca.
    """
    fila = search(documentos, tarea["question"], cuantos, realce_titulo=1)
    ids = {d.id for d in fila}
    faltan = [d for d in tarea.get("answer_in", []) if d not in ids]
    if faltan:
        por_id = {d.id: d for d in documentos}
        fila = fila[: cuantos - len(faltan)] + [por_id[d] for d in faltan if d in por_id]
    return fila


# (answer, input tokens, output tokens, cost in USD) for one user message.
Answerer = Callable[[str], Awaitable[tuple[str, int, int, float]]]


def _answer_api(cliente: Any, modelo: str) -> Answerer:
    async def answer(contenido: str) -> tuple[str, int, int, float]:
        respuesta = cliente.messages.create(
            model=modelo,
            max_tokens=1500,
            system=SISTEMA,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": contenido}],
        )
        acumulado = Usage()
        acumulado.add(respuesta.usage)
        texto = "".join(b.text for b in respuesta.content if getattr(b, "type", "") == "text")
        coste = acumulado.cost(modelo if modelo in PRICES else MODELO_POR_DEFECTO)
        uso = respuesta.usage
        return texto.strip(), uso.input_tokens, uso.output_tokens, coste

    return answer


def _answer_cli(cli: Any) -> Answerer:
    """Through `claude -p` (subscription): list-price cost as Claude Code reports it."""

    async def answer(contenido: str) -> tuple[str, int, int, float]:
        sesion = await cli.run(contenido)
        if not sesion.ok:
            raise RuntimeError(f"claude cli: {sesion.reason or 'no answer'}")
        entrada = sesion.input_tokens + sesion.cache_read_tokens + sesion.cache_write_tokens
        return sesion.text.strip(), entrada, sesion.output_tokens, sesion.list_cost_usd

    return answer


async def _fake(contenido: str) -> tuple[str, int, int, float]:
    return fake_answer(contenido)


async def _una(
    responder: Answerer,
    secuencia: list[Document],
    tarea: dict[str, Any],
    *,
    arm: str,
    repeat: int,
    modelo: str,
    squire: Squire | None,
    lever: str,
    via: str = "api",
) -> Ejecucion:
    registro = Ejecucion(
        task=tarea["id"],
        arm=arm,
        repeat=repeat,
        model=modelo,
        retrieval="fixed",
        lever=lever,
        via=via,
    )
    inicio = time.monotonic()
    piezas: list[str] = []
    try:
        cuerpos: dict[str, str] | None = None
        if squire is not None and lever == "pages":
            cuerpos, retenidos, pasajes = await trim_by_pages(squire, tarea["question"], secuencia)
            registro.dropped.extend(retenidos)
            registro.dropped_passages.extend(pasajes)
        for doc in secuencia:
            registro.fetched.append(doc.id)
            if cuerpos is None:
                cuerpo = await _texto_de_pagina(doc, tarea["question"], squire, registro, lever)
            else:
                cuerpo = cuerpos.get(doc.id) or (
                    "[withheld: no passage of it holds a fact the question needs] "
                    "Work with the other documents."
                )
            piezas.append(f"--- {doc.id}: {doc.title} ---\n{cuerpo}")

        contenido = f"{tarea['question']}\n\n" + "\n\n".join(piezas)
        texto, entrada, salida, coste = await responder(contenido)
        registro.input_tokens = entrada
        registro.output_tokens = salida
        registro.model_cost_usd = coste
        registro.answer = texto
        registro.correct = acierta(registro.answer, tarea["answer_contains"])
        registro.turns = 1
    except Exception as error:  # una ejecucion rota no tumba la tanda
        registro.error = f"{error.__class__.__name__}: {error}"

    registro.wall_s = round(time.monotonic() - inicio, 2)
    if squire is not None:
        registro.squire_cost_usd = squire.meter.cost_usd
        registro.squire_decisions = squire.meter.decisions
    return registro


def _resumen(filas: list[Ejecucion], lever: str) -> dict[str, Any]:
    bare = [f for f in filas if f.arm == "bare"]
    sq = [f for f in filas if f.arm == "squire"]
    pares = [
        (b, s)
        for b in bare
        for s in sq
        if b.task == s.task and b.repeat == s.repeat and not b.error and not s.error
    ]
    # Los DOS contadores, siempre. El del 2026-09-24 leia solo el de triaje y por eso una
    # tanda de redundancia imprimia `drop 0` tirase lo que tirase.
    caidos_triaje = sum(len(s.dropped) for _b, s in pares)
    caidos_redundancia = sum(len(s.dropped_redundant) for _b, s in pares)
    pasajes = sum(len(s.dropped_passages) for _b, s in pares)
    caidos = caidos_triaje + caidos_redundancia + pasajes
    servidos = sum(len(s.fetched) for _b, s in pares)

    def _acierto(filas_: list[Ejecucion]) -> tuple[int, int]:
        validas = [f for f in filas_ if f.correct is not None]
        return sum(1 for f in validas if f.correct), len(validas)

    aciertos_b, n_b = _acierto([b for b, _s in pares])
    aciertos_s, n_s = _acierto([s for _b, s in pares])
    return {
        "lever": lever,
        "pairs": len(pares),
        "docs_served_per_arm": servidos,
        "dropped_triage": caidos_triaje,
        "dropped_redundant": caidos_redundancia,
        "dropped_passages": pasajes,
        "dropped_total": caidos,
        # Sin caidas no hay experimento: los dos brazos entregaron los mismos bytes.
        "informative": caidos > 0,
        "input_tokens": {
            "bare": sum(b.input_tokens for b, _s in pares),
            "squire": sum(s.input_tokens for _b, s in pares),
            "ratio": bootstrap_ratio(pares, lambda e: float(e.input_tokens)),
        },
        "cost_usd": {
            "bare": round(sum(b.total_cost_usd for b, _s in pares), 6),
            "squire": round(sum(s.total_cost_usd for _b, s in pares), 6),
            "ratio": bootstrap_ratio(pares, lambda e: e.total_cost_usd),
        },
        "squire_cost_usd": round(sum(s.squire_cost_usd for _b, s in pares), 6),
        "correct": {
            "bare": f"{aciertos_b}/{n_b}",
            "squire": f"{aciertos_s}/{n_s}",
            "bare_lower_bound": round(wilson(aciertos_b, n_b)[1], 3) if n_b else None,
            "squire_lower_bound": round(wilson(aciertos_s, n_s)[1], 3) if n_s else None,
        },
    }


def _render(resumen: dict[str, Any]) -> str:
    lineas = ["# Fetch-heavy A/B, fixed document sequence", ""]
    lineas.append(
        f"{resumen['pairs']} pairs, {resumen['docs_served_per_arm']} documents walked per arm, "
        f"lever `{resumen['lever']}`."
    )
    lineas.append("")
    if not resumen["informative"]:
        lineas.append(
            "**UNINFORMATIVE.** The lever dropped nothing, so both arms were handed the same "
            "bytes and this run is one experiment performed twice. Any difference below is "
            "noise. Do not quote it. (This is the check the run of 2026-09-24 did not have: "
            "its drop counter read the triage list during a redundancy run and printed "
            "`drop 0` either way.)"
        )
        lineas.append("")
    lineas.append(
        f"Dropped: {resumen['dropped_triage']} by triage, {resumen['dropped_redundant']} as "
        f"redundant, of {resumen['docs_served_per_arm']} documents served; "
        f"{resumen.get('dropped_passages', 0)} passages removed from documents that stayed."
    )
    lineas.append("")
    lineas.append("| | bare | squire | paired ratio [95 %] |")
    lineas.append("|---|---|---|---|")
    for clave, nombre in (("input_tokens", "Input tokens"), ("cost_usd", "Cost USD")):
        observado, bajo, alto = resumen[clave]["ratio"]
        intervalo = f"{observado:+.1%} [{bajo:+.1%}, {alto:+.1%}]"
        lineas.append(
            f"| {nombre} | {resumen[clave]['bare']} | {resumen[clave]['squire']} | {intervalo} |"
        )
    c = resumen["correct"]
    lineas.append(
        f"| Correct | {c['bare']} | {c['squire']} | lower bounds "
        f"{c['bare_lower_bound']} / {c['squire_lower_bound']} |"
    )
    lineas.append("")
    lineas.append(
        f"The squire's own cost: {resumen['squire_cost_usd']:.6f} USD. **Read the correctness "
        "row before the cost row**: a cheaper arm that answers fewer questions is measuring "
        "the cost of not delivering, which this project has mistaken for a saving twice."
    )
    return "\n".join(lineas)


JEV_PER_DECISION_USD = 0.000029  # measured list figure, output included (README, "What it costs")


def _tareas(leer: Callable[[str], str]) -> list[dict[str, Any]]:
    return [
        json.loads(linea)
        for linea in leer("benchmarks/ab/tasks.jsonl").splitlines()
        if linea.strip() and not linea.lstrip().startswith("#")
    ]


def _plan(args: argparse.Namespace, tareas: list[dict[str, Any]], secuencias: dict) -> None:
    entrada_estimada = sum(sum(len(d.text) for d in secuencias[t["id"]]) // 4 + 400 for t in tareas)
    brazos = 1 if args.reuse_bare else 2
    llamadas = len(tareas) * brazos * args.repeats
    coste_estimado = entrada_estimada * args.repeats * brazos * 2e-6
    print(f"Tareas: {len(tareas)}  documentos por tarea: {args.docs}  repeticiones: {args.repeats}")
    print(f"Corpus: {args.corpus_ref or 'working tree'}  via: {args.via}  lever: {args.lever}")
    print(
        f"Llamadas al modelo: {llamadas}  entrada estimada por vuelta: {entrada_estimada:,} tokens"
    )
    print(f"**Coste estimado del modelo: {coste_estimado:.2f} USD** (tope: {args.max_usd:.2f} USD)")
    for tarea in tareas:
        seq = secuencias[tarea["id"]]
        dentro = [d for d in tarea.get("answer_in", []) if d in {x.id for x in seq}]
        print(
            f"  {tarea['id']:<16} {len(seq):>2} docs, "
            f"{sum(len(d.text) for d in seq) // 4:>6} tokens, respuesta dentro: "
            f"{len(dentro)}/{len(tarea.get('answer_in', []))}"
        )


def _responder(args: argparse.Namespace) -> tuple[Answerer, Any]:
    if args.fake:
        return _fake, None
    if args.via == "claude-cli":
        from sanchopanza.eval import harness

        _h = harness.load()
        ClaudeCLI, SessionCache = _h.ClaudeCLI, _h.SessionCache

        cache = SessionCache(args.cli_cache) if args.cli_cache else None
        cli = ClaudeCLI(
            model=args.model,
            system=SISTEMA,
            ceiling_usd=args.max_usd,
            max_budget_usd=0.5,
            concurrency=1,
            effort="low",
            cache=cache,
            count_cached=True,
        )
        return _answer_cli(cli), cli
    import anthropic

    return _answer_api(anthropic.Anthropic(), args.model), None


async def principal(args: argparse.Namespace) -> int:
    leer = git_reader(args.corpus_ref, RAIZ) if args.corpus_ref else None
    documentos = build(read=leer)
    tareas = _tareas(leer or (lambda ruta: (RAIZ / ruta).read_text(encoding="utf-8")))
    if args.tasks:
        pedidas = {t.strip() for t in args.tasks.split(",")}
        tareas = [t for t in tareas if t["id"] in pedidas]
    secuencias = {t["id"]: _secuencia(documentos, t, args.docs) for t in tareas}

    grabadas: list[Ejecucion] = []
    if args.reuse_bare:
        filas_grabadas = json.loads(Path(args.reuse_bare).read_text(encoding="utf-8"))
        motivos = check_reusable(filas_grabadas, secuencias, args.model)
        if args.via != "api":
            motivos.append(f"the recorded arm went through the API, this run through {args.via}")
        if motivos:
            print("The recorded bare arm cannot be reused:", file=sys.stderr)
            for motivo in motivos:
                print(f"  {motivo}", file=sys.stderr)
            return 2
        campos = set(Ejecucion.__dataclass_fields__)
        grabadas = [
            Ejecucion(**{k: v for k, v in f.items() if k in campos})
            for f in filas_grabadas
            if f["arm"] == "bare" and f["repeat"] == 0 and f["task"] in secuencias
        ]

    _plan(args, tareas, secuencias)
    # Each fact must sit in exactly one document of this corpus, and inside its task's
    # sequence: otherwise a miss measures the retriever or a moved pin, not the lever.
    problemas = verificar(documentos, tareas)
    for tarea in tareas:
        pins = tarea.get("pins") or [tarea["pin"]]
        dentro = {d.id for d in secuencias[tarea["id"]]}
        fuera = [p for p in pins if not any(p in d.text for d in secuencias[tarea["id"]])]
        if fuera:
            problemas += 1
            print(f"  MAL {tarea['id']}: {fuera} not in its sequence ({len(dentro)} docs)")
    if problemas:
        print(f"\n{problemas} problems with this corpus: fix or pin another --corpus-ref.")
        return 3
    if args.dry_run:
        print("\n--dry-run: nada se ha llamado y nada se ha gastado.")
        return 0

    import hashlib
    import os

    if args.lever == "pages" and not args.fake:
        prereg = RAIZ / "docs" / "results" / "2026-09-28-fixed-pages" / "prereg.md"
        registrado = prereg.with_name("prereg.sha256")
        huella = hashlib.sha256(prereg.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        if not registrado.exists() or registrado.read_text().strip() != huella:
            print("prereg.md de --lever pages sin registrar o cambiado: nada gastado.")
            return 1

    clave_jev = os.environ.get("TYPESAFE_API_KEY", "")
    if not clave_jev and not args.fake:
        print("Sin TYPESAFE_API_KEY el brazo `squire` seria identico al `bare`.", file=sys.stderr)
        return 1
    responder, cli = _responder(args)
    brazos = ("squire",) if grabadas else ("bare", "squire")
    filas: list[Ejecucion] = list(grabadas)
    gastado = 0.0
    decisiones = 0
    for repeticion in range(args.repeats):
        for tarea in tareas:
            for brazo in brazos:
                squire = None
                if brazo == "squire":
                    # Mismo proveedor y mismos umbrales que `run.py`: si estos dos ficheros
                    # midieran con configuraciones distintas, sus numeros no se podrian leer
                    # juntos, que es la mitad del valor de tener los dos.
                    decisor = EveryQuestion() if args.fake else create("jev", api_key=clave_jev)
                    squire = Squire(decisor, thresholds=Thresholds(), brief=tarea["question"])
                fila = await _una(
                    responder,
                    secuencias[tarea["id"]],
                    tarea,
                    arm=brazo,
                    repeat=repeticion,
                    modelo=args.model,
                    squire=squire,
                    lever=args.lever,
                    via="fake" if args.fake else args.via,
                )
                filas.append(fila)
                gastado += fila.total_cost_usd
                decisiones += fila.squire_decisions
                print(
                    f"  [{repeticion}] {tarea['id']:<16} {brazo:<6} "
                    f"{fila.input_tokens:>6} tok  {fila.total_cost_usd:.4f} $  "
                    f"decisiones={fila.squire_decisions}  retenidos={len(fila.dropped)}  "
                    f"pasajes={len(fila.dropped_passages)}  correcto={fila.correct}  "
                    f"acumulado={gastado:.2f} $"
                )
                if fila.error:
                    print(f"    error: {fila.error}")
                if gastado > args.max_usd:
                    print(f"\nTOPE ALCANZADO ({args.max_usd:.2f} $). Se para aqui.")
                    break
            else:
                continue
            break
        else:
            continue
        break

    if args.fake:
        print(
            f"\n--fake: {decisiones} decisiones del decisor falso; con Jev serian unos "
            f"{decisiones * JEV_PER_DECISION_USD:.4f} USD. Las respuestas son vacias: la fila "
            "de aciertos no significa nada."
        )
    resumen = _resumen(filas, args.lever)
    texto = _render(resumen)
    print("\n" + texto)
    if args.out:
        destino = Path(args.out)
        destino.mkdir(parents=True, exist_ok=True)
        (destino / "rows.json").write_text(
            json.dumps([asdict(f) for f in filas], ensure_ascii=False, indent=1), encoding="utf-8"
        )
        (destino / "summary.json").write_text(
            json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        (destino / "summary.md").write_text(texto + "\n", encoding="utf-8")
        print(f"\nEscrito en {destino}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--docs", type=int, default=DOCS_POR_TAREA)
    p.add_argument("--tasks", default="")
    p.add_argument("--model", default=MODELO_POR_DEFECTO)
    p.add_argument("--lever", default="both", choices=["triage", "redundancy", "both", "pages"])
    p.add_argument("--via", default="api", choices=["api", "claude-cli"])
    p.add_argument("--cli-cache", default="", help="SessionCache path for --via claude-cli")
    p.add_argument("--corpus-ref", default="", help="build the corpus from this git commit")
    p.add_argument("--reuse-bare", default="", help="recorded rows.json whose bare arm to reuse")
    p.add_argument("--fake", action="store_true", help="fake decider and answers: free")
    p.add_argument("--max-usd", type=float, default=6.0)
    p.add_argument("--out", default="")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    assert CONDICIONES  # las condiciones de run.py siguen siendo la referencia del corpus
    return asyncio.run(principal(args))


if __name__ == "__main__":
    raise SystemExit(main())
