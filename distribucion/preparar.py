# -*- coding: utf-8 -*-
"""
Antes de armar el ejecutable y el instalador: genera en distribucion/generado/
  iterador_cev.ico        icono del .exe y del instalador (comun/icono_app.py)
  iterador_cev.svg        el mismo icono en SVG (para la web u otros usos)
  aviso_instalador.txt    lo que el instalador muestra antes de instalar (aviso legal,
                          autores, licencia y nota de la plantilla; de distribucion.yaml)
y escribe en una linea (JSON) los datos que usa armar_instalador.ps1.
"""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from herramientas.comun import app_config as ac  # noqa: E402
from herramientas.comun import icono_app  # noqa: E402

GENERADO = RAIZ / "distribucion" / "generado"


def main() -> None:
    GENERADO.mkdir(parents=True, exist_ok=True)
    ico = icono_app.ico(GENERADO / "iterador_cev.ico")
    (GENERADO / "iterador_cev.svg").write_text(icono_app.svg(), encoding="utf-8")
    c = ac.creditos()
    aviso = GENERADO / "aviso_instalador.txt"
    aviso.write_text("\n\n".join([
        f"{ac.nombre()} {ac.version()}",
        ac.texto_aviso(),
        c.get("autores") or "",
        c.get("licencia") or "",
        " ".join(str(c.get("plantilla") or "").split()),
    ]) + "\n", encoding="utf-8-sig")                     # con BOM: Inno Setup lo lee como UTF-8
    print(json.dumps({
        "nombre": ac.nombre(),
        "version": ac.version(),
        "version_numero": ac.version_numero(),
        "editor": c.get("editor") or c.get("autores") or "",
        "url": c.get("url") or "",
        "archivo": f"IteradorCEV-{ac.version()}-instalador".replace(" ", "-"),
        "icono": str(ico),
        "aviso": str(aviso),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
