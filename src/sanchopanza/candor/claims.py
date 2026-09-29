"""What the agent said, cut into claims code can hold against the ledger.

Rules in English and Spanish, no model. A claim is a sentence plus what it asserts: that the
checks pass, that something was done, that something was not touched, or that a file or page
was the source. Anything the rules cannot parse is not a claim here; the optional judge
(`candor.judge`) may still read the sentence, but it only ever adds suspicion.

Deliberately narrow. A vague "done" leaves nothing atomic to contradict (arXiv 2609.08589
measured agents at 5.8-11.5 % accuracy on their own mid-task status), so the Stop adapter can
ask for a structured report instead of trying to parse prose harder.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from ..text import split_sentences

ClaimKind = Literal["checks_pass", "done", "denial", "did", "cited"]

SENTENCE_LIMIT = 400

_CHECKS_PASS = re.compile(
    r"\b(all\s+)?(the\s+)?(tests?|suite|checks?|build|ci|lint(ing)?|type[- ]?check)\s+"
    r"(now\s+)?(are\s+|is\s+)?(all\s+)?(pass(es|ing|ed)?|green|succeed(s|ed)?|clean|OK)\b"
    r"|\b(\d+|all)\s+(tests?\s+)?passed\b|\bpassing\s+tests\b|\ball\s+green\b|\b0\s+failures\b"
    r"|\b(los\s+)?(tests?|pruebas|comprobaciones|la\s+suite)\s+(ya\s+)?(pasan|pasa|est[aá]n?\s+en\s+verde"
    r"|salen\s+en\s+verde|funcionan)\b|\btodo\s+(en\s+)?verde\b|\btodo\s+(pasa|funciona)\b",
    re.IGNORECASE,
)
# The object of a denial runs to the end of the clause. A dot inside a file name ("money.py")
# does not end it: v1 cut there and read "src/money.py" as the words "src" and "money".
_TAIL = r"(?:[^.;\n]|\.(?=\w)){0,120}"
_DONE = re.compile(
    r"\b(task|work|fix|change|implementation|feature)\s+(is\s+)?(now\s+)?(complete|completed|done|"
    r"finished)\b|\bI(')?ve\s+(completed|finished|fixed|implemented|resolved)\b|\bdone\.?$"
    r"|\b(listo|hecho|terminado|completado|resuelto|arreglado)\b",
    re.IGNORECASE,
)
_HEDGE = re.compile(
    r"\b(not|n't|no|nor|still|yet|except|but|however|aunque|pero|salvo|todav[ií]a|a[uú]n)\b"
    r"|\b(fail(s|ed|ing|ures?)?|falla(n|ron)?|error(es)?|broken|rot[oa]s?)\b"
    # v2: a goal or an intention is not a claim ("the task is to make the suite pass").
    r"|\b(should|would|will|needs?\s+to|to\s+make|in\s+order\s+to|goal|task\s+is|rather\s+than"
    r"|debe|deber[ií]a|para\s+que|objetivo)\b",
    re.IGNORECASE,
)
_DENIAL = re.compile(
    r"\b(I\s+)?(did\s*n[o']t|didn't|have\s*n[o']t|haven't|never|without)\s+(touch(ing|ed)?|modif(y|ied|ying)"
    r"|chang(e|ed|ing)|delet(e|ed|ing)|remov(e|ed|ing)|edit(ed|ing)?|push(ed|ing)?|sen[dt](ing)?|"
    r"access(ed|ing)?|read(ing)?|open(ed|ing)?)\b(?P<en>" + _TAIL + r")"
    r"|\b(no\s+(he|hemos)\s+|sin\s+|nunca\s+(he\s+)?)(tocad[oa]|tocar|modificad[oa]|modificar|cambiad[oa]"
    r"|cambiar|borrad[oa]|borrar|eliminad[oa]|eliminar|editad[oa]|editar|subid[oa]|subir|enviad[oa]"
    r"|enviar|accedid[oa]|acceder|le[ií]d[oa]|leer|abiert[oa]|abrir)\b(?P<es>" + _TAIL + r")",
    re.IGNORECASE,
)
# Passive denials, which v1 missed ("nothing was deleted", "no se ha borrado nada"): universal
# unless a path follows.
_PASSIVE_DENIAL = re.compile(
    r"\b(nothing|no\s+(other\s+)?files?|none\s+of\s+(them|the\s+files))\s+(was|were|has\s+been"
    r"|have\s+been|got)\s+(deleted|removed|changed|modified|touched|edited|pushed|sent)\b"
    r"(?P<en>" + _TAIL + r")"
    r"|\b(nada\s+(se\s+)?(ha\s+)?(sido\s+)?|no\s+se\s+(ha|han)\s+|no\s+se\s+)(borrad|borr[oó]|eliminad"
    r"|elimin[oó]|tocad|toc[oó]|modificad|modific[oó]|cambiad|cambi[oó])\w*\b(?P<es>"
    + _TAIL
    + r")",
    re.IGNORECASE,
)
_I_HAVE = r"\bI(')?(ve|\s+have)?\s+((then|also|finally|now|just|first|already)\s+)?"
_DID_EN = {
    "delete": r"(deleted|removed|dropped|cleaned\s+up|purged)\b",
    "external": r"(pushed|published|deployed|sent|emailed|posted|uploaded"
    r"|opened\s+a\s+(PR|pull))\b",
    "test": r"(ran|run|re-?ran|executed)\s+([\w'’-]+\s+){0,3}(tests?|suite|pytest|checks?)\b",
    "write": r"(created|written|wrote|added|edited|updated|modified|fixed|changed|renamed)\b",
    "read": r"(read|reviewed|checked|inspected|looked\s+at|gone\s+through|examined)\b",
}
_DID_ES = {
    "delete": r"(borrado|eliminado|quitado|limpiado)\b",
    "external": r"(subido|publicado|desplegado|enviado|abierto\s+(un|el)\s+PR)\b",
    "test": r"(ejecutado|lanzado|pasado|corrido)\s+(los\s+|las\s+)?(tests?|pruebas|la\s+suite)\b",
    "write": r"(creado|escrito|a[ñn]adido|editado|actualizado|modificado|arreglado|cambiado)\b",
    "read": r"(le[ií]do|revisado|mirado|inspeccionado|examinado)\b",
}
# A first-person assertion of an action, with the effect it implies in the ledger. Order
# matters: the first effect that matches a sentence is the one it asserts.
_DID: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (effect, re.compile(_I_HAVE + _DID_EN[effect] + r"|\b(he|hemos)\s+" + _DID_ES[effect], re.I))
    for effect in ("delete", "external", "test", "write", "read")
)
_PATH = re.compile(
    r"`([^`\s]{2,160})`|(?<![\w/])((?:[\w.-]+[\\/])+[\w.-]+\.\w{1,6}|[\w-]+\.(?:py|ts|tsx|js|jsx"
    r"|md|json|ya?ml|toml|ini|cfg|txt|csv|sql|sh|go|rs|java|rb|php|html|css|lock|env))(?![\w/])"
)
_URL = re.compile(r"https?://[^\s)\]>'\"`]+")


@dataclass(frozen=True, slots=True)
class Claim:
    kind: ClaimKind
    sentence: str
    effect: str = ""  # for `did`: the ledger effect the sentence asserts
    objects: tuple[str, ...] = ()  # paths, URLs or words the claim is about


def paths_in(text: str) -> tuple[str, ...]:
    found: list[str] = []
    for match in _PATH.finditer(text):
        value = (match.group(1) or match.group(2) or "").strip(".,:;")
        if value and ("." in value or "/" in value or "\\" in value) and value not in found:
            found.append(value)
    return tuple(found)


def urls_in(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(u.rstrip(".,:;") for u in _URL.findall(text)))


_FIELD = re.compile(r"^\s*(STATUS|TESTS|TEST_FILES_CHANGED|FILES_READ)\s*:\s*(.*)$", re.I | re.M)


def report_block(said: str) -> dict[str, str]:
    """The structured report, when the harness asked for one: `STATUS: done|partial|blocked`,
    `TESTS: pass|fail|not run`, `TEST_FILES_CHANGED: yes|no`, `FILES_READ: a, b`. A vague prose
    "done" leaves nothing to contradict; these four lines always do."""
    return {m.group(1).upper(): m.group(2).strip() for m in _FIELD.finditer(said or "")}


def without_block(said: str) -> str:
    return _FIELD.sub("", said or "").strip()


def block_claims(block: dict[str, str]) -> list[Claim]:
    out: list[Claim] = []
    status = block.get("STATUS", "").lower()
    tests = block.get("TESTS", "").lower()
    if tests.startswith("pass"):
        out.append(Claim("checks_pass", f"TESTS: {block['TESTS']}"))
    elif status.startswith("done"):
        out.append(Claim("done", f"STATUS: {block['STATUS']}"))
    if block.get("TEST_FILES_CHANGED", "").lower().startswith("no"):
        out.append(Claim("denial", "TEST_FILES_CHANGED: no", effect="test_files"))
    read = [p.strip().strip("`") for p in block.get("FILES_READ", "").split(",")]
    read = [p for p in read if p and p.lower() not in ("none", "-", "n/a")]
    if read:
        out.append(Claim("cited", f"FILES_READ: {block['FILES_READ']}", objects=tuple(read)))
    return out


def extract(said: str) -> list[Claim]:
    """Every claim the rules can read: the structured block if any, then sentence by sentence."""
    out: list[Claim] = block_claims(report_block(said))
    for raw in split_sentences(without_block(said)):
        sentence = raw.strip()[:SENTENCE_LIMIT]
        if not sentence:
            continue
        denial = _DENIAL.search(sentence) or _PASSIVE_DENIAL.search(sentence)
        if denial:
            tail = denial.group("en") or denial.group("es") or ""
            objects = paths_in(tail) or _words(tail)
            verb = denial.group(0)[: len(denial.group(0)) - len(tail)]
            out.append(Claim("denial", sentence, effect=_denied(verb), objects=objects))
            continue  # a denial is not also a success claim
        hedged = bool(_HEDGE.search(sentence))
        if _CHECKS_PASS.search(sentence) and not hedged:
            out.append(Claim("checks_pass", sentence))
        elif _DONE.search(sentence) and not hedged:
            out.append(Claim("done", sentence))
        for effect, pattern in _DID:
            match = pattern.search(sentence)
            # Negated only when the negation comes before the verb: "I ran the suite to make sure
            # nothing broke" still asserts a run (v2).
            before = sentence[: match.start()] if match else ""
            negated = re.search(r"\b(not|n't|no|never)\b", before, re.IGNORECASE)
            if match and not negated:
                out.append(Claim("did", sentence, effect=effect, objects=paths_in(sentence)))
                break
        cited = paths_in(sentence) + urls_in(sentence)
        if cited and _CITES.search(sentence):
            out.append(Claim("cited", sentence, objects=cited))
    return out


_CITES = re.compile(
    r"\baccording\s+to\b|\bper\s|\bas\s+(shown|stated|described|documented|noted)\s+in\b"
    r"|\bsources?\s*:|\bI(')?(ve|\s+have)?\s+(read|reviewed|checked|looked\s+at|went\s+through)\b"
    r"|\bbased\s+on\b|\bseg[uú]n\b|\bde\s+acuerdo\s+con\b|\bcomo\s+(dice|indica|muestra|recoge)\b"
    r"|\bfuentes?\s*:"
    r"|\b(he|hemos)\s+(le[ií]do|revisado|mirado)\b|\bbas[aá]ndo(me|nos)\s+en\b",
    re.IGNORECASE,
)
_DENIED_EFFECT: tuple[tuple[str, str], ...] = (
    ("delete", r"delet|remov|borr|elimin"),
    ("external", r"push|sen[dt]|subi|envi"),
    ("read", r"read|open|access|le[ií]|abri|abier|acced"),
)


def _denied(phrase: str) -> str:
    """The ledger effect a denial rules out: `write` covers touch, modify, change and edit."""
    for effect, pattern in _DENIED_EFFECT:
        if re.search(pattern, phrase, re.IGNORECASE):
            return effect
    return "write"


_STOP_WORDS = (
    "the a an any of to in on at and or it its this that these those file files anything "
    "el la los las un una de del en y o ni nada ningun ninguna ningún fichero ficheros archivo "
    "archivos"
)
_STOP = frozenset(_STOP_WORDS.split())


_UNIVERSAL = re.compile(
    r"^\s*(nada|nothing|anything|any\s+(other\s+)?files?|ning[uú]n\w*|todo|everything|else)\b",
    re.IGNORECASE,
)


def _words(tail: str) -> tuple[str, ...]:
    """The object of a denial: the words of its first clause, none for 'nothing'/'nada'."""
    tail = re.split(r"[,;]|\b(but|pero|solo|only|just)\b", tail, maxsplit=1)[0]
    if _UNIVERSAL.match(tail):
        return ()
    words = [w for w in re.findall(r"[\w.-]{3,}", tail.lower()) if w not in _STOP]
    return tuple(words[:4])
