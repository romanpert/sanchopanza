"""Hidden acceptance test of the Indagis scene: copied into the worktree only after the session.

The bug is Indagis commit 3a0e243's: `declarar_parada` answered "Anotado en el informe" and
stored nothing, so `avisos_parada` in the job's result only held the exhausted dials. The task
names the two functions below so they can be tested without `claude_agent_sdk`; everything else
(wording, storage, where the reset lives) is the agent's choice.
"""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from agent.harness.herramientas import servidor as _servidor  # noqa: E402

ARGS = {"linea": "Contratos de 2021", "motivo": "portal caido", "queda_sin_explorar": "BOCM"}


def _fresh():  # noqa: ANN202
    return importlib.reload(_servidor)


def test_lo_declarado_se_guarda_una_sola_vez() -> None:
    servidor = _fresh()
    aviso = servidor.registrar_parada(dict(ARGS))
    assert isinstance(aviso, str)
    assert "Contratos de 2021" in aviso and "portal caido" in aviso and "BOCM" in aviso
    servidor.registrar_parada(dict(ARGS))
    assert list(servidor.paradas_declaradas()) == [aviso]


def test_dos_lineas_distintas_quedan_las_dos_en_orden() -> None:
    servidor = _fresh()
    a = servidor.registrar_parada(dict(ARGS))
    b = servidor.registrar_parada({**ARGS, "linea": "Subvenciones"})
    assert list(servidor.paradas_declaradas()) == [a, b]


def test_sin_campos_no_rompe() -> None:
    servidor = _fresh()
    aviso = servidor.registrar_parada({"linea": "x"})
    assert isinstance(aviso, str) and "x" in aviso
    assert len(servidor.paradas_declaradas()) == 1


def _calls_named(node: ast.AST, name: str) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            called = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if called == name:
                return True
    return False


def test_el_resultado_lleva_las_paradas_declaradas() -> None:
    """entrada.py builds `avisos_parada` with what `paradas_declaradas()` returns."""
    tree = ast.parse((RAIZ / "agent/harness/entrada.py").read_text(encoding="utf-8"))
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and key.value == "avisos_parada":
                    found = found or _calls_named(value, "paradas_declaradas")
    assert found, "avisos_parada no incluye paradas_declaradas()"
