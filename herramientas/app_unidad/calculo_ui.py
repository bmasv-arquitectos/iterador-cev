# -*- coding: utf-8 -*-
"""
Calculo en el panel Resultados (a la derecha), en el orden de una etiqueta de
eficiencia energetica: arriba la etiqueta (escala y datos de consumo) y, si cfg trae
aviso_legal (distribucion_ui.preparar), el aviso de uso referencial; debajo
Calcular / Cancelar con la barra de progreso, el motor de calculo y las
descargas (resultados .zip, etiqueta .png y las acciones extra que entregue la
interfaz, como el reporte PDF), y al final el detalle (avisos, tiempo, carpeta
y nota).

Es generico: no sabe de CEV. Usa una "calculadora", un modulo con
calcular / vista / detalle / paquete y, si los ofrece, motores e imagen (ver
herramientas/unidad/calculo_cev.py), que se elige en config/editor.yaml
(calculo.modulo). Otra herramienta de la caja puede entregar su propia
calculadora y reutilizar este panel.
El calculo corre en un hilo (comun/tarea.py); un ui.timer lee el progreso.
"""
from __future__ import annotations

import importlib

from nicegui import ui

from herramientas.comun.tarea import Tarea

from .piezas import html


class PanelCalculo:
    """
    cfg: seccion calculo de config/editor.yaml.
    obtener(): lo que se calcula (la unidad actual).
    problema(): texto si todavia no se puede calcular, o None.
    P: piezas.Piezas; descargar(bytes, nombre).
    extras: [(texto, funcion)] botones que se muestran junto a las descargas (siempre,
    aunque no haya calculo; la funcion puede ser async).
    """

    def __init__(self, cfg: dict, obtener, problema, P, descargar, extras=()):
        self.cfg, self.tx = cfg, cfg["textos"]
        self.calc = importlib.import_module(cfg["modulo"])
        self.obtener, self.problema, self.P, self.descargar = obtener, problema, P, descargar
        self.extras = list(extras)
        f = getattr(self.calc, "motores", None)
        self.motores = f(cfg) if f is not None else {}
        self.motor = next(iter(self.motores), None)
        self.tarea = Tarea()
        self.res = self.error = self.objeto = self.calculado = None
        self.barra = self.texto = self.aviso = None
        self.timer = ui.timer(cfg.get("sondeo_s", 0.25), self._sondear, active=False)
        self.cuerpo = ui.refreshable(self._cuerpo)
        self.cuerpo()

    # ------------------------------------------------------------ acciones
    def calcular(self):
        if self.tarea.estado == "corriendo":
            return
        msg = self.problema()
        if msg:
            ui.notify(msg, type="warning")
            return
        self.objeto, self.error = self.obtener(), None
        kw = {"cfg": self.cfg}
        if self.motor is not None:
            kw["motor"] = self.motor
        self.tarea.iniciar(self.calc.calcular, self.objeto, **kw)
        self.cuerpo.refresh()
        self.timer.activate()

    def cancelar(self):
        self.tarea.cancelar()

    def elegir_motor(self, v):
        if v and v != self.motor:
            self.motor = v

    def _bajar(self, funcion):
        try:
            datos, nombre = funcion()
        except Exception as ex:
            ui.notify(f"No se pudo armar la descarga: {ex}", type="negative")
            return
        self.descargar(datos, nombre)

    def bajar(self):
        self._bajar(lambda: self.calc.paquete(self.res))

    def bajar_imagen(self):
        self._bajar(lambda: self.calc.imagen(self.res, self.cfg))

    def _sondear(self):
        t = self.tarea
        if t.estado == "corriendo":
            if self.barra is not None:
                self.barra.set_value(t.progreso)
                self.texto.set_text(t.mensaje)
            return
        self.timer.deactivate()
        if t.estado == "terminada":
            self.res, self.calculado = t.resultado, self.objeto
        elif t.estado == "error":
            self.error = f"{self.tx['error']}: {t.error}"
        elif t.estado == "cancelada":
            ui.notify(self.tx["cancelado"])
        self.cuerpo.refresh()

    def revisar(self, actual) -> None:
        """Avisa si lo que se ve ya no es lo que se calculo."""
        if self.aviso is not None:
            self.aviso.set_visibility(self.res is not None and actual != self.calculado)

    # ------------------------------------------------------------ interfaz
    def _cuerpo(self):
        corriendo = self.tarea.estado == "corriendo"
        svg = self.calc.vista(self.res, self.cfg)
        if svg:
            html(svg, "etiqueta-calculo")
        if self.cfg.get("aviso_legal"):
            ui.label(self.cfg["aviso_legal"]).classes("aviso-legal-texto")
        self.aviso = ui.label(self.tx["desactualizado"]).classes("aviso-calculo")
        self.aviso.set_visibility(self.res is not None and self.obtener() != self.calculado)
        with ui.element("div").classes("calcular"):
            if corriendo:
                self.P.accion(self.tx["cancelar"], self.cancelar, peligro=True).classes("ancho")
            else:
                self.P.accion(self.tx["calcular"], self.calcular, principal=True).classes("ancho")
        if len(self.motores) > 1:
            s = (ui.select(self.motores, value=self.motor, label=self.tx["motor"],
                           on_change=lambda e: self.elegir_motor(e.value))
                 .props("dense options-dense").classes("w-full motor"))
            if corriendo:
                s.disable()
        elif self.motores:
            ui.label(next(iter(self.motores.values()))).classes("texto-suave motor")
        self.barra = self.texto = None
        if corriendo:
            self.barra = ui.linear_progress(value=self.tarea.progreso, show_value=False).classes("progreso")
            self.texto = ui.label(self.tarea.mensaje).classes("progreso-texto")
        if self.error:
            ui.label(self.error).classes("errores")
        if not corriendo and (self.res or self.extras):
            with ui.element("div").classes("acciones"):
                if self.res:
                    self.P.accion(self.tx["descargar"], self.bajar)
                    if hasattr(self.calc, "imagen"):
                        self.P.accion(self.tx.get("descargar_imagen", "Imagen"), self.bajar_imagen)
                for texto, funcion in self.extras:
                    self.P.accion(texto, funcion)
        lineas = self.calc.detalle(self.res, self.cfg) if self.res else [self.tx["sin_resultado"]]
        if lineas:
            ui.markdown("\n\n".join(lineas)).classes("detalle-calculo")
