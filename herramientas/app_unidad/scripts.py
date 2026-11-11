# -*- coding: utf-8 -*-
"""
JavaScript del navegador y utilidades sin estado del editor (app.py).
"""
from __future__ import annotations

# El boton de la rueda sobre el lienzo o el 3D no activa el autodesplazamiento del navegador
SIN_AUTOSCROLL = ("<script>document.addEventListener('mousedown', e => {"
                  "if (e.button === 1 && e.target.closest && e.target.closest('.lienzo-editor')) "
                  "e.preventDefault();});</script>")
# Un clic sobre el lienzo despues de arrastrar (orbitar el 3D) no llega a la escena
CLIC_SIN_ARRASTRE = ("<script>(function(){let x0=0,y0=0;"
                     "document.addEventListener('pointerdown',e=>{x0=e.clientX;y0=e.clientY;},true);"
                     "document.addEventListener('click',e=>{if(e.target.closest&&"
                     "e.target.closest('.lienzo-editor')&&Math.hypot(e.clientX-x0,e.clientY-y0)>%d)"
                     "{e.stopPropagation();}},true);})();</script>")
# Asigna los botones a los OrbitControls de la escena (reintenta hasta que la escena cargue)
BOTONES_3D = ("(function(){let n=0;const f=()=>{const el=getElement(%d);"
              "if(el&&el.controls){el.controls.mouseButtons={LEFT:%d,MIDDLE:%d,RIGHT:%d};}"
              "else if(n++<100){setTimeout(f,100);}};f();})()")
# Grilla del suelo (GridHelper de ui.scene): opacidad, sin escribir profundidad y, si se pide,
# dibujada antes que todo (renderOrder -1): asi una losa que coincide con ella la tapa entera.
# Argumentos: id de la escena, opacidad (0..1), detras (true | false). Reintenta hasta que cargue.
GRILLA_3D = ("(function(){let n=0;const f=()=>{const el=getElement(%d);"
             "const g=el&&el.scene?el.scene.children.filter(o=>o.type==='GridHelper'):[];"
             "if(g.length){g.forEach(o=>{(Array.isArray(o.material)?o.material:[o.material]).forEach(m=>{"
             "m.transparent=true;m.opacity=%s;m.depthWrite=false;m.needsUpdate=true;});"
             "if(%s){o.renderOrder=-1;}});}"
             "else if(n++<100){setTimeout(f,100);}};f();})()")
# Imagen del canvas 3D (JPEG): se dibuja (sin la grilla si se pide) y se lee en el mismo paso
CAPTURA_3D = ("(()=>{const el=getElement(%d);if(!el||!el.renderer||!el.scene||!el.camera)return null;"
              "const g=%s?el.scene.children.filter(o=>o.type==='GridHelper'&&o.visible):[];"
              "g.forEach(o=>o.visible=false);el.renderer.render(el.scene,el.camera);"
              "const d=el.renderer.domElement.toDataURL('image/jpeg',0.92);"
              "g.forEach(o=>o.visible=true);el.renderer.render(el.scene,el.camera);return d;})()")
VENTANA_JS = ("window.addEventListener('resize', () => "
              "emitEvent('ventana', {w: window.innerWidth, h: window.innerHeight}))")


def grilla_js(id_escena: int, e3: dict) -> str:
    """GRILLA_3D con la opacidad y el orden de config/editor.yaml (modelo3d.grilla_opacidad y
    modelo3d.grilla_detras)."""
    op = min(max(float(e3.get("grilla_opacidad", 1.0)), 0.0), 1.0)
    return GRILLA_3D % (id_escena, f"{op:.3f}", "true" if e3.get("grilla_detras", True) else "false")


def superficie_losa(nombre: str):
    """(destino, nivel) de una losa del 3D que es envolvente; None para la losa entre niveles
    y las obstrucciones. Nombres de modelo3d: piso|0|i, voladizo|k|i, techo|k|i, piso|k|i
    (entre niveles), obstaculo|k|t."""
    partes = (nombre or "").split("|")
    if len(partes) != 3 or not partes[1].isdigit():
        return None
    tipo, k = partes[0], int(partes[1])
    if tipo == "techo":
        return ("techo", k)
    if tipo == "voladizo":
        return ("piso", k)
    if tipo == "piso" and k == 0:
        return ("piso", 0)
    return None
