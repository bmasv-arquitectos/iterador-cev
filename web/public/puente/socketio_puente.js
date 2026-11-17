/*
 * Reemplazo de socket.io para NiceGUI en el navegador (herramientas/web/nicegui_web.py).
 *
 * Corre dentro del iframe con la pagina de NiceGUI (en lugar de static/socket.io.min.js). En vez
 * de un websocket con un servidor, usa el puente que deja la pagina que contiene el iframe
 * (window.parent.__puenteNiceGUI, en src/apps/iterador-nicegui/main.ts):
 *   emitir(evento, datos) -> promesa   lo que el navegador manda a Python
 *   escuchar(fn)                       fn(texto) por cada mensaje de Python: [evento, datos] en
 *                                      JSON; {"__bytes__": base64} vuelve como Uint8Array
 *   subir(cliente, elemento, archivos) los archivos de un ui.upload (en vez del POST)
 *
 * io() devuelve un objeto con lo que usa nicegui.js (on, emit, io.on, io.opts, io.engine) y, al
 * crearse, hace el saludo ("connect" con la consulta: client_id, tab_id...) y dispara connect.
 */
(function () {
  "use strict";
  var puente = window.parent && window.parent.__puenteNiceGUI;
  if (!puente) {
    console.error("socketio_puente: falta window.parent.__puenteNiceGUI");
    return;
  }

  function revivir(clave, v) {
    if (v && typeof v === "object" && !Array.isArray(v)) {
      var claves = Object.keys(v);
      if (claves.length === 1 && claves[0] === "__bytes__") {
        var s = atob(v.__bytes__);
        var b = new Uint8Array(s.length);
        for (var i = 0; i < s.length; i++) b[i] = s.charCodeAt(i);
        return b;
      }
    }
    return v;
  }

  window.io = function (url, opciones) {
    var oyentes = {};
    function disparar(evento, args) {
      (oyentes[evento] || []).slice().forEach(function (f) {
        try {
          f.apply(null, args);
        } catch (e) {
          console.error(e);
        }
      });
    }
    var socket = {
      id: "navegador",
      connected: false,
      io: {
        opts: opciones || {},
        engine: { transport: {} },
        on: function () {
          return socket.io;
        },
      },
      on: function (evento, f) {
        (oyentes[evento] = oyentes[evento] || []).push(f);
        return socket;
      },
      emit: function (evento, datos, ack) {
        puente.emitir(evento, datos).then(
          function (r) {
            if (typeof ack === "function") ack(r);
          },
          function (e) {
            console.error("Python:", e && e.message ? e.message : e, e && e.traza ? e.traza : "");
          },
        );
        return socket;
      },
      disconnect: function () {},
      close: function () {},
    };
    puente.escuchar(function (texto) {
      var m = JSON.parse(texto, revivir);
      disparar(m[0], [m[1]]);
    });
    var consulta = (opciones && opciones.query) || {};
    puente.emitir("connect", consulta).then(
      function (ok) {
        if (!ok) {
          console.error("socketio_puente: Python no acepto la conexion");
          return;
        }
        socket.connected = true;
        disparar("connect", []);
      },
      function (e) {
        console.error("socketio_puente: no se pudo conectar", e && e.message ? e.message : e);
        disparar("connect_error", [e]);
      },
    );
    return socket;
  };

  // ui.upload: QUploader manda los archivos por XHR a /_nicegui/client/<cliente>/upload/<elemento>;
  // aca van al puente y el XHR termina como si el servidor hubiera respondido.
  var XHR = window.XMLHttpRequest;
  var SUBIDA = /\/_nicegui\/client\/([^/]+)\/upload\/(\d+)/;
  function fijar(o, clave, valor) {
    Object.defineProperty(o, clave, { value: valor, configurable: true, writable: true });
  }
  class XHRPuente extends XHR {
    open(metodo, url) {
      this.__subida = SUBIDA.exec(String(url));
      if (!this.__subida) return super.open.apply(this, arguments);
    }
    setRequestHeader() {
      if (!this.__subida) return super.setRequestHeader.apply(this, arguments);
    }
    send(cuerpo) {
      if (!this.__subida) return super.send(cuerpo);
      var xhr = this;
      var m = this.__subida;
      var lecturas = [];
      if (cuerpo && typeof cuerpo.forEach === "function") {
        cuerpo.forEach(function (v) {
          if (v instanceof Blob) {
            lecturas.push(
              v.arrayBuffer().then(function (b) {
                return { nombre: v.name || "", tipo: v.type || "", datos: new Uint8Array(b) };
              }),
            );
          }
        });
      }
      function fin(estado, texto) {
        fijar(xhr, "readyState", 4);
        fijar(xhr, "status", estado);
        fijar(xhr, "statusText", estado === 200 ? "OK" : "Error");
        fijar(xhr, "responseText", texto);
        fijar(xhr, "response", texto);
        try {
          xhr.upload.dispatchEvent(new ProgressEvent("progress", { lengthComputable: true, loaded: 1, total: 1 }));
        } catch (e) {}
        xhr.dispatchEvent(new Event("readystatechange"));
        xhr.dispatchEvent(new ProgressEvent(estado === 200 ? "load" : "error"));
        xhr.dispatchEvent(new ProgressEvent("loadend"));
      }
      Promise.all(lecturas)
        .then(function (archivos) {
          return puente.subir(m[1], Number(m[2]), archivos);
        })
        .then(
          function () {
            fin(200, '{"upload":"success"}');
          },
          function (e) {
            console.error("socketio_puente: subida", e);
            fin(500, String(e && e.message ? e.message : e));
          },
        );
    }
  }
  window.XMLHttpRequest = XHRPuente;
})();
