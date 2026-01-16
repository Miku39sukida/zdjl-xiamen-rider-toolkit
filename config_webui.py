import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flask import Flask, abort, redirect, render_template_string, request, url_for


APP_ROOT = Path(__file__).resolve().parent


def _default_config_path() -> Path:
    env = os.environ.get("ALIAS_CONFIG_PATH", "").strip()
    if env:
        p = Path(env)
        return p if p.is_absolute() else (APP_ROOT / p)

    # Prefer Android internal storage if present (mobile-friendly default)
    candidates = [
        Path("/sdcard/merchant_alias.json"),
        Path("/storage/emulated/0/merchant_alias.json"),
        Path("/sdcard/zdjl/merchant_alias.json"),
        Path("/storage/emulated/0/zdjl/merchant_alias.json"),
        APP_ROOT / "merchant_alias.json",
    ]
    for p in candidates:
        try:
            if p.exists():
                return p
        except Exception:  # noqa: BLE001
            continue
    return APP_ROOT / "merchant_alias.json"


def _resolve_config_path(raw: str | None) -> Path:
    """
    Allow selecting config file by query param `path=`:
    - empty -> default config
    - relative -> relative to repo root
    - absolute -> allowed if under allowed roots (mobile-friendly)
    """
    if not raw:
        return _default_config_path()
    p = Path(raw)
    if not p.is_absolute():
        return (APP_ROOT / p).resolve()

    pr = p.resolve()
    # Allow absolute paths under configured roots (default includes repo + Android internal storage)
    allowed = os.environ.get("ALLOWED_CONFIG_ROOTS", "").strip()
    if not allowed:
        allowed_roots = [APP_ROOT, Path("/sdcard"), Path("/storage/emulated/0")]
    else:
        allowed_roots = [Path(x) for x in allowed.split(":") if x.strip()]

    allowed_roots_resolved: list[Path] = []
    for r in allowed_roots:
        try:
            allowed_roots_resolved.append(r.resolve())
        except Exception:  # noqa: BLE001
            continue

    for root in allowed_roots_resolved:
        root_s = str(root)
        pr_s = str(pr)
        if pr_s == root_s or pr_s.startswith(root_s + os.sep):
            return pr

    raise ValueError(
        "Refusing to access path outside allowed roots. "
        "Set ALLOWED_CONFIG_ROOTS (colon-separated) to allow absolute paths, e.g. "
        "'/sdcard:/storage/emulated/0'."
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exact": {}, "regex": [], "timed": [], "address": {"exact": {}, "regex": [], "disambiguate": []}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Config JSON must be an object")
    extra = {k: v for k, v in data.items() if k not in ("exact", "regex", "timed", "address")}
    exact = data.get("exact", {})
    regex = data.get("regex", [])
    timed = data.get("timed", [])
    address = data.get("address", {"exact": {}, "regex": []})
    if not isinstance(exact, dict):
        raise ValueError("`exact` must be an object")
    if not isinstance(regex, list):
        raise ValueError("`regex` must be an array")
    if not isinstance(timed, list):
        raise ValueError("`timed` must be an array")
    if not isinstance(address, dict):
        raise ValueError("`address` must be an object")
    addr_extra = {k: v for k, v in address.items() if k not in ("exact", "regex", "disambiguate")}
    addr_exact = address.get("exact", {})
    addr_regex = address.get("regex", [])
    addr_disambiguate = address.get("disambiguate", [])
    if not isinstance(addr_exact, dict):
        raise ValueError("`address.exact` must be an object")
    if not isinstance(addr_regex, list):
        raise ValueError("`address.regex` must be an array")
    if addr_disambiguate is not None and not isinstance(addr_disambiguate, list):
        raise ValueError("`address.disambiguate` must be an array")
    # normalize regex entries
    norm_regex: list[dict[str, str]] = []
    for r in regex:
        if not isinstance(r, dict):
            continue
        pattern = str(r.get("pattern", "") or "")
        flags = str(r.get("flags", "") or "")
        replace = str(r.get("replace", "") or "")
        if not pattern:
            continue
        norm_regex.append({"pattern": pattern, "flags": flags, "replace": replace})

    # normalize timed entries
    norm_timed: list[dict[str, str]] = []
    for r in timed:
        if not isinstance(r, dict):
            continue
        mode = str(r.get("mode", "") or "exact").strip()
        if mode not in ("exact", "regex"):
            mode = "exact"
        match = str(r.get("match", "") or "")
        pattern = str(r.get("pattern", "") or "")
        flags = str(r.get("flags", "") or "")
        start = str(r.get("start", "") or "")
        end = str(r.get("end", "") or "")
        replace = str(r.get("replace", "") or "")
        if not replace or not start or not end:
            continue
        if mode == "exact" and not match:
            continue
        if mode == "regex" and not pattern:
            continue
        norm_timed.append(
            {
                "mode": mode,
                "match": match,
                "pattern": pattern,
                "flags": flags,
                "start": start,
                "end": end,
                "replace": replace,
            }
        )

    norm_addr_regex: list[dict[str, str]] = []
    for r in addr_regex:
        if not isinstance(r, dict):
            continue
        pattern = str(r.get("pattern", "") or "")
        flags = str(r.get("flags", "") or "")
        replace = str(r.get("replace", "") or "")
        if not pattern:
            continue
        norm_addr_regex.append({"pattern": pattern, "flags": flags, "replace": replace})

    norm_addr_disambiguate: list[dict[str, Any]] = []
    for r in (addr_disambiguate or []):
        if not isinstance(r, dict):
            continue
        rid = str(r.get("id", "") or "").strip()
        mode = str(r.get("mode", "") or "exact").strip()
        if mode not in ("exact", "regex"):
            mode = "exact"
        match = str(r.get("match", "") or "")
        pattern = str(r.get("pattern", "") or "")
        flags = str(r.get("flags", "") or "")
        title = str(r.get("title", "") or "")
        remember = bool(r.get("remember", False))
        options = r.get("options", [])
        if not isinstance(options, list):
            options = []
        norm_opts: list[dict[str, str]] = []
        for o in options:
            if not isinstance(o, dict):
                continue
            label = str(o.get("label", "") or "")
            replace = str(o.get("replace", "") or "")
            if not replace:
                continue
            norm_opts.append({"label": label, "replace": replace})
        if not norm_opts:
            continue
        if mode == "exact" and not match:
            continue
        if mode == "regex" and not pattern:
            continue
        norm_addr_disambiguate.append(
            {
                "id": rid,
                "mode": mode,
                "match": match,
                "pattern": pattern,
                "flags": flags,
                "title": title,
                "remember": remember,
                "options": norm_opts,
            }
        )

    cfg = {
        "exact": {str(k): str(v) for k, v in exact.items()},
        "regex": norm_regex,
        "timed": norm_timed,
        "address": {
            "exact": {str(k): str(v) for k, v in addr_exact.items()},
            "regex": norm_addr_regex,
            "disambiguate": norm_addr_disambiguate,
            **addr_extra,
        },
        **extra,
    }
    return cfg


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_suffix(path.suffix + f".bak-{time.strftime('%Y%m%d_%H%M%S')}")
        shutil.copy2(path, backup)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


@dataclass
class PageState:
    config_path: str
    config: dict[str, Any]
    error: str | None = None
    info: str | None = None


TEMPLATE = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>merchant_alias.json 配置管理</title>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, "PingFang SC", "Microsoft YaHei", sans-serif; margin: 18px; color: #111; }
    .row { display: flex; gap: 14px; flex-wrap: wrap; align-items: flex-end; }
    .card { border: 1px solid #ddd; border-radius: 10px; padding: 14px; margin-top: 14px; }
    h2 { margin: 0 0 10px; font-size: 18px; }
    label { display: block; font-size: 12px; color: #333; margin-bottom: 6px; }
    input[type=text] { width: 520px; max-width: 100%; padding: 10px 12px; border: 1px solid #ccc; border-radius: 10px; font-size: 14px; }
    button { padding: 10px 14px; border-radius: 10px; border: 1px solid #bbb; background: #f8f8f8; cursor: pointer; font-size: 14px; }
    button.primary { background: #1a73e8; color: #fff; border-color: #1a73e8; }
    button.danger { background: #b00020; color: #fff; border-color: #b00020; }
    .tablewrap { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; }
    table { width: 100%; border-collapse: collapse; min-width: 720px; }
    th, td { text-align: left; padding: 8px; border-bottom: 1px solid #eee; vertical-align: top; }
    th { font-size: 12px; color: #444; }
    code { background: #f3f3f3; padding: 2px 6px; border-radius: 6px; }
    .msg { margin-top: 10px; padding: 10px 12px; border-radius: 10px; }
    .err { background: #ffecec; border: 1px solid #ffb3b3; }
    .ok  { background: #ecfff1; border: 1px solid #b3ffd0; }
    .small { font-size: 12px; color: #555; }

    @media (max-width: 560px) {
      body { margin: 12px; }
      input[type=text] { width: 100%; }
      button { width: 100%; }
      table { min-width: 640px; }
    }
  </style>
</head>
<body>
  <h1 style="margin:0 0 6px;font-size:22px;">配置文件增删改查 Web UI</h1>
  <div class="small">当前文件：<code>{{ state.config_path }}</code></div>

  {% if state.error %}
    <div class="msg err"><b>错误</b>：{{ state.error }}</div>
  {% endif %}
  {% if state.info %}
    <div class="msg ok"><b>已保存</b>：{{ state.info }}</div>
  {% endif %}

  <div class="card">
    <h2>切换/创建配置文件</h2>
    <form method="get" action="{{ url_for('index') }}">
      <div class="row">
        <div>
          <label>path（相对路径或 /sdcard 绝对路径）</label>
          <input type="text" name="path" placeholder="/sdcard/merchant_alias.json" value="{{ state.config_path }}"/>
        </div>
        <button class="primary" type="submit">打开</button>
      </div>
      <div class="small" style="margin-top:8px;">
        也可用环境变量 <code>ALIAS_CONFIG_PATH</code> 指定默认文件路径；如需允许其它绝对路径，可设置 <code>ALLOWED_CONFIG_ROOTS</code>（冒号分隔）。
      </div>
    </form>
  </div>

  <div class="card">
    <h2>Exact 映射（精确替换）</h2>
    <form method="post" action="{{ url_for('exact_upsert') }}">
      <input type="hidden" name="path" value="{{ state.config_path }}"/>
      <div class="row">
        <div>
          <label>原名称（key）</label>
          <input type="text" name="key" required placeholder="京东便利店(厦门总店)"/>
        </div>
        <div>
          <label>替换为（value）</label>
          <input type="text" name="value" required placeholder="京东便利店(双浦路店)"/>
        </div>
        <button class="primary" type="submit">新增/更新</button>
      </div>
    </form>

    <div class="tablewrap">
      <table style="margin-top:10px;">
        <thead><tr><th style="width:45%;">key</th><th style="width:45%;">value</th><th style="width:10%;">操作</th></tr></thead>
        <tbody>
        {% for k, v in state.config.exact.items() %}
          <tr>
            <td><code>{{ k }}</code></td>
            <td><code>{{ v }}</code></td>
            <td>
              <form method="post" action="{{ url_for('exact_delete') }}" style="display:inline;">
                <input type="hidden" name="path" value="{{ state.config_path }}"/>
                <input type="hidden" name="key" value="{{ k }}"/>
                <button class="danger" type="submit">删除</button>
              </form>
            </td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
  </div>

  <div class="card">
    <h2>Regex 规则（正则替换）</h2>
    <form method="post" action="{{ url_for('regex_add') }}">
      <input type="hidden" name="path" value="{{ state.config_path }}"/>
      <div class="row">
        <div>
          <label>pattern（正则）</label>
          <input type="text" name="pattern" required placeholder="^雪梨星光(?:[一二三四五六七八九十百千零]+|\\d+)期"/>
        </div>
        <div>
          <label>flags（如 i,m,s）</label>
          <input type="text" name="flags" placeholder=""/>
        </div>
        <div>
          <label>replace（替换为）</label>
          <input type="text" name="replace" required placeholder="园山北里"/>
        </div>
        <button class="primary" type="submit">新增</button>
      </div>
    </form>

    <div class="tablewrap">
      <table style="margin-top:10px;">
        <thead><tr><th>pattern</th><th>flags</th><th>replace</th><th>操作</th></tr></thead>
        <tbody>
        {% for idx, r in state.config.regex %}
          <tr>
            <td><code>{{ r.pattern }}</code></td>
            <td><code>{{ r.flags }}</code></td>
            <td><code>{{ r.replace }}</code></td>
            <td style="white-space:nowrap;">
              <form method="post" action="{{ url_for('regex_delete') }}" style="display:inline;">
                <input type="hidden" name="path" value="{{ state.config_path }}"/>
                <input type="hidden" name="index" value="{{ idx }}"/>
                <button class="danger" type="submit">删除</button>
              </form>
            </td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>

    <div class="small" style="margin-top:10px;">
      提示：regex 顺序很重要，越靠前越先匹配。
    </div>
  </div>

  <div class="card">
    <h2>Timed 规则（定时替换，支持跨午夜）</h2>
    <form method="post" action="{{ url_for('timed_add') }}">
      <input type="hidden" name="path" value="{{ state.config_path }}"/>
      <div class="row">
        <div>
          <label>mode</label>
          <select name="mode" style="padding:10px 12px;border:1px solid #ccc;border-radius:10px;font-size:14px;">
            <option value="exact">exact</option>
            <option value="regex">regex</option>
          </select>
        </div>
        <div>
          <label>match（exact 用）</label>
          <input type="text" name="match" placeholder="华莱士(五缘湾店)"/>
        </div>
        <div>
          <label>pattern（regex 用）</label>
          <input type="text" name="pattern" placeholder="^华莱士\\(五缘湾店\\)$"/>
        </div>
        <div>
          <label>flags</label>
          <input type="text" name="flags" placeholder=""/>
        </div>
        <div>
          <label>start（HH:MM）</label>
          <input type="text" name="start" required placeholder="22:00"/>
        </div>
        <div>
          <label>end（HH:MM）</label>
          <input type="text" name="end" required placeholder="10:00"/>
        </div>
        <div>
          <label>replace</label>
          <input type="text" name="replace" required placeholder="五缘湾天虹停车场-出入口"/>
        </div>
        <button class="primary" type="submit">新增</button>
      </div>
      <div class="small" style="margin-top:8px;">规则命中后会覆盖普通别名（exact/regex）。若 start &gt; end 表示跨午夜。</div>
    </form>

    <div class="tablewrap">
      <table style="margin-top:10px;">
        <thead><tr><th>mode</th><th>match/pattern</th><th>flags</th><th>start</th><th>end</th><th>replace</th><th>操作</th></tr></thead>
        <tbody>
        {% for idx, r in state.config.timed %}
          <tr>
            <td><code>{{ r.mode }}</code></td>
            <td><code>{% if r.mode == 'exact' %}{{ r.match }}{% else %}{{ r.pattern }}{% endif %}</code></td>
            <td><code>{{ r.flags }}</code></td>
            <td><code>{{ r.start }}</code></td>
            <td><code>{{ r.end }}</code></td>
            <td><code>{{ r.replace }}</code></td>
            <td style="white-space:nowrap;">
              <form method="post" action="{{ url_for('timed_delete') }}" style="display:inline;">
                <input type="hidden" name="path" value="{{ state.config_path }}"/>
                <input type="hidden" name="index" value="{{ idx }}"/>
                <button class="danger" type="submit">删除</button>
              </form>
            </td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
  </div>

  <div class="card">
    <h2>顾客地址别名（用于导航 POI 映射）</h2>

    <h3 style="margin: 6px 0 10px; font-size: 16px;">Exact</h3>
    <form method="post" action="{{ url_for('addr_exact_upsert') }}">
      <input type="hidden" name="path" value="{{ state.config_path }}"/>
      <div class="row">
        <div>
          <label>原地址（key）</label>
          <input type="text" name="key" required placeholder="湖边湾璟A区3号楼"/>
        </div>
        <div>
          <label>替换为（value）</label>
          <input type="text" name="value" required placeholder="下湖社3号楼"/>
        </div>
        <button class="primary" type="submit">新增/更新</button>
      </div>
    </form>

    <div class="tablewrap">
      <table style="margin-top:10px;">
        <thead><tr><th style="width:45%;">key</th><th style="width:45%;">value</th><th style="width:10%;">操作</th></tr></thead>
        <tbody>
        {% for k, v in state.config.address.exact.items() %}
          <tr>
            <td><code>{{ k }}</code></td>
            <td><code>{{ v }}</code></td>
            <td>
              <form method="post" action="{{ url_for('addr_exact_delete') }}" style="display:inline;">
                <input type="hidden" name="path" value="{{ state.config_path }}"/>
                <input type="hidden" name="key" value="{{ k }}"/>
                <button class="danger" type="submit">删除</button>
              </form>
            </td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>

    <h3 style="margin: 14px 0 10px; font-size: 16px;">Regex</h3>
    <form method="post" action="{{ url_for('addr_regex_add') }}">
      <input type="hidden" name="path" value="{{ state.config_path }}"/>
      <div class="row">
        <div>
          <label>pattern</label>
          <input type="text" name="pattern" required placeholder="^湖边湾璟A区"/>
        </div>
        <div>
          <label>flags</label>
          <input type="text" name="flags" placeholder=""/>
        </div>
        <div>
          <label>replace</label>
          <input type="text" name="replace" required placeholder="下湖社"/>
        </div>
        <button class="primary" type="submit">新增</button>
      </div>
    </form>

    <div class="tablewrap">
      <table style="margin-top:10px;">
        <thead><tr><th>pattern</th><th>flags</th><th>replace</th><th>操作</th></tr></thead>
        <tbody>
        {% for idx, r in state.config.address.regex %}
          <tr>
            <td><code>{{ r.pattern }}</code></td>
            <td><code>{{ r.flags }}</code></td>
            <td><code>{{ r.replace }}</code></td>
            <td style="white-space:nowrap;">
              <form method="post" action="{{ url_for('addr_regex_delete') }}" style="display:inline;">
                <input type="hidden" name="path" value="{{ state.config_path }}"/>
                <input type="hidden" name="index" value="{{ idx }}"/>
                <button class="danger" type="submit">删除</button>
              </form>
            </td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>

    <h3 style="margin: 14px 0 10px; font-size: 16px;">歧义选择（命中后弹窗选择）</h3>
    <div class="small" style="margin: 0 0 10px;">
      用于处理“同名城中村/同名小区”等歧义场景（例如 <code>后埔社</code>）。命中后脚本会弹出选项，按选择替换地址中的匹配片段。
    </div>
    <form method="post" action="{{ url_for('addr_disamb_add') }}">
      <input type="hidden" name="path" value="{{ state.config_path }}"/>
      <div class="row">
        <div>
          <label>id（可选，建议唯一）</label>
          <input type="text" name="id" placeholder="xiamen_houpu_she"/>
        </div>
        <div>
          <label>mode</label>
          <input type="text" name="mode" placeholder="exact 或 regex" value="exact"/>
        </div>
        <div>
          <label>match（exact 用）</label>
          <input type="text" name="match" placeholder="后埔社"/>
        </div>
        <div>
          <label>pattern（regex 用）</label>
          <input type="text" name="pattern" placeholder="^(后埔社)"/>
        </div>
        <div>
          <label>flags</label>
          <input type="text" name="flags" placeholder="i"/>
        </div>
        <div>
          <label>title（弹窗标题，可选）</label>
          <input type="text" name="title" placeholder="检测到“后埔社”存在歧义，请选择："/>
        </div>
        <div>
          <label>remember（记住选择）</label>
          <input type="text" name="remember" placeholder="true/false" value="true"/>
        </div>
      </div>
      <div class="row" style="margin-top:10px;">
        <div>
          <label>选项1 label</label>
          <input type="text" name="opt1_label" placeholder="马垅后埔社"/>
        </div>
        <div>
          <label>选项1 replace</label>
          <input type="text" name="opt1_replace" placeholder="马垅后埔社"/>
        </div>
        <div>
          <label>选项2 label</label>
          <input type="text" name="opt2_label" placeholder="江头后埔社"/>
        </div>
        <div>
          <label>选项2 replace</label>
          <input type="text" name="opt2_replace" placeholder="江头后埔社"/>
        </div>
        <button class="primary" type="submit">新增</button>
      </div>
    </form>

    <div class="tablewrap">
      <table style="margin-top:10px;">
        <thead><tr><th>id</th><th>mode</th><th>match/pattern</th><th>remember</th><th>options</th><th>操作</th></tr></thead>
        <tbody>
        {% for idx, r in state.config.address.disambiguate %}
          <tr>
            <td><code>{{ r.id }}</code></td>
            <td><code>{{ r.mode }}</code></td>
            <td><code>{% if r.mode == 'exact' %}{{ r.match }}{% else %}{{ r.pattern }}{% endif %}</code></td>
            <td><code>{{ r.remember }}</code></td>
            <td>
              {% for o in r.options %}
                <div><code>{{ o.label or o.replace }}</code> → <code>{{ o.replace }}</code></div>
              {% endfor %}
            </td>
            <td style="white-space:nowrap;">
              <form method="post" action="{{ url_for('addr_disamb_delete') }}" style="display:inline;">
                <input type="hidden" name="path" value="{{ state.config_path }}"/>
                <input type="hidden" name="index" value="{{ idx }}"/>
                <button class="danger" type="submit">删除</button>
              </form>
            </td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>
"""


app = Flask(__name__)


def _load_state() -> PageState:
    raw_path = request.args.get("path") if request.method == "GET" else request.values.get("path")
    try:
        cfg_path = _resolve_config_path(raw_path)
        cfg = _read_json(cfg_path)
        cfg["exact"] = dict(sorted(cfg["exact"].items(), key=lambda kv: kv[0]))
        cfg["regex"] = list(enumerate(cfg["regex"]))
        cfg["timed"] = list(enumerate(cfg.get("timed", [])))
        cfg["address"]["exact"] = dict(sorted(cfg["address"]["exact"].items(), key=lambda kv: kv[0]))
        cfg["address"]["regex"] = list(enumerate(cfg["address"]["regex"]))
        cfg["address"]["disambiguate"] = list(enumerate(cfg["address"].get("disambiguate", [])))
        return PageState(config_path=str(cfg_path.relative_to(APP_ROOT)) if str(cfg_path).startswith(str(APP_ROOT)) else str(cfg_path), config=cfg)
    except Exception as e:  # noqa: BLE001
        return PageState(
            config_path=raw_path or str(_default_config_path()),
            config={"exact": {}, "regex": [], "timed": [], "address": {"exact": {}, "regex": [], "disambiguate": []}},
            error=str(e),
        )


def _save_config(config_path_raw: str, config_obj: dict[str, Any]) -> None:
    cfg_path = _resolve_config_path(config_path_raw)
    _atomic_write_json(cfg_path, config_obj)


@app.get("/")
def index():
    state = _load_state()
    info = request.args.get("info")
    if info:
        state.info = info
    return render_template_string(TEMPLATE, state=state)


@app.post("/exact/upsert")
def exact_upsert():
    path = request.values.get("path") or ""
    key = (request.form.get("key") or "").strip()
    value = (request.form.get("value") or "").strip()
    if not key:
        abort(400, "key required")
    cfg_path = _resolve_config_path(path)
    cfg = _read_json(cfg_path)
    cfg["exact"][key] = value
    _save_config(path, cfg)
    return redirect(url_for("index", path=path, info="已更新 exact 映射"))


@app.post("/exact/delete")
def exact_delete():
    path = request.values.get("path") or ""
    key = (request.form.get("key") or "").strip()
    cfg_path = _resolve_config_path(path)
    cfg = _read_json(cfg_path)
    cfg["exact"].pop(key, None)
    _save_config(path, cfg)
    return redirect(url_for("index", path=path, info="已删除 exact 映射"))


@app.post("/regex/add")
def regex_add():
    path = request.values.get("path") or ""
    pattern = (request.form.get("pattern") or "").strip()
    flags = (request.form.get("flags") or "").strip()
    replace = (request.form.get("replace") or "").strip()
    if not pattern:
        abort(400, "pattern required")
    # basic regex validation
    import re

    try:
        re.compile(pattern, flags=_parse_re_flags(flags))
    except re.error as e:
        state = _load_state()
        state.error = f"Regex 无效：{e}"
        return render_template_string(TEMPLATE, state=state), 400

    cfg_path = _resolve_config_path(path)
    cfg = _read_json(cfg_path)
    cfg["regex"].append({"pattern": pattern, "flags": flags, "replace": replace})
    _save_config(path, cfg)
    return redirect(url_for("index", path=path, info="已新增 regex 规则"))


@app.post("/regex/delete")
def regex_delete():
    path = request.values.get("path") or ""
    index_raw = request.form.get("index") or ""
    try:
        idx = int(index_raw)
    except ValueError:
        abort(400, "invalid index")

    cfg_path = _resolve_config_path(path)
    cfg = _read_json(cfg_path)
    if 0 <= idx < len(cfg["regex"]):
        cfg["regex"].pop(idx)
    _save_config(path, cfg)
    return redirect(url_for("index", path=path, info="已删除 regex 规则"))


def _is_hhmm(s: str) -> bool:
    import re

    m = re.match(r"^(\d{1,2}):(\d{2})$", (s or "").strip())
    if not m:
        return False
    hh = int(m.group(1))
    mm = int(m.group(2))
    return 0 <= hh <= 23 and 0 <= mm <= 59


@app.post("/timed/add")
def timed_add():
    path = request.values.get("path") or ""
    mode = (request.form.get("mode") or "exact").strip()
    match = (request.form.get("match") or "").strip()
    pattern = (request.form.get("pattern") or "").strip()
    flags = (request.form.get("flags") or "").strip()
    start = (request.form.get("start") or "").strip()
    end = (request.form.get("end") or "").strip()
    replace = (request.form.get("replace") or "").strip()

    if mode not in ("exact", "regex"):
        mode = "exact"
    if not replace:
        abort(400, "replace required")
    if not _is_hhmm(start) or not _is_hhmm(end):
        state = _load_state()
        state.error = "时间格式必须为 HH:MM（例如 22:00）"
        return render_template_string(TEMPLATE, state=state), 400

    import re

    if mode == "exact":
        if not match:
            abort(400, "match required for exact")
    else:
        if not pattern:
            abort(400, "pattern required for regex")
        try:
            re.compile(pattern, flags=_parse_re_flags(flags))
        except re.error as e:
            state = _load_state()
            state.error = f"Regex 无效：{e}"
            return render_template_string(TEMPLATE, state=state), 400

    cfg_path = _resolve_config_path(path)
    cfg = _read_json(cfg_path)
    cfg.setdefault("timed", [])
    cfg["timed"].append(
        {
            "mode": mode,
            "match": match,
            "pattern": pattern,
            "flags": flags,
            "start": start,
            "end": end,
            "replace": replace,
        }
    )
    _save_config(path, cfg)
    return redirect(url_for("index", path=path, info="已新增 timed 规则"))


@app.post("/timed/delete")
def timed_delete():
    path = request.values.get("path") or ""
    index_raw = request.form.get("index") or ""
    try:
        idx = int(index_raw)
    except ValueError:
        abort(400, "invalid index")

    cfg_path = _resolve_config_path(path)
    cfg = _read_json(cfg_path)
    timed = cfg.get("timed", [])
    if isinstance(timed, list) and 0 <= idx < len(timed):
        timed.pop(idx)
        cfg["timed"] = timed
    _save_config(path, cfg)
    return redirect(url_for("index", path=path, info="已删除 timed 规则"))


@app.post("/addr/exact/upsert")
def addr_exact_upsert():
    path = request.values.get("path") or ""
    key = (request.form.get("key") or "").strip()
    value = (request.form.get("value") or "").strip()
    if not key:
        abort(400, "key required")
    cfg_path = _resolve_config_path(path)
    cfg = _read_json(cfg_path)
    cfg.setdefault("address", {"exact": {}, "regex": []})
    cfg["address"].setdefault("exact", {})
    cfg["address"]["exact"][key] = value
    _save_config(path, cfg)
    return redirect(url_for("index", path=path, info="已更新 顾客地址 exact"))


@app.post("/addr/exact/delete")
def addr_exact_delete():
    path = request.values.get("path") or ""
    key = (request.form.get("key") or "").strip()
    cfg_path = _resolve_config_path(path)
    cfg = _read_json(cfg_path)
    cfg.setdefault("address", {"exact": {}, "regex": []})
    cfg["address"].setdefault("exact", {})
    cfg["address"]["exact"].pop(key, None)
    _save_config(path, cfg)
    return redirect(url_for("index", path=path, info="已删除 顾客地址 exact"))


@app.post("/addr/regex/add")
def addr_regex_add():
    path = request.values.get("path") or ""
    pattern = (request.form.get("pattern") or "").strip()
    flags = (request.form.get("flags") or "").strip()
    replace = (request.form.get("replace") or "").strip()
    if not pattern:
        abort(400, "pattern required")
    import re

    try:
        re.compile(pattern, flags=_parse_re_flags(flags))
    except re.error as e:
        state = _load_state()
        state.error = f"Regex 无效：{e}"
        return render_template_string(TEMPLATE, state=state), 400

    cfg_path = _resolve_config_path(path)
    cfg = _read_json(cfg_path)
    cfg.setdefault("address", {"exact": {}, "regex": []})
    cfg["address"].setdefault("regex", [])
    cfg["address"]["regex"].append({"pattern": pattern, "flags": flags, "replace": replace})
    _save_config(path, cfg)
    return redirect(url_for("index", path=path, info="已新增 顾客地址 regex"))


@app.post("/addr/regex/delete")
def addr_regex_delete():
    path = request.values.get("path") or ""
    index_raw = request.form.get("index") or ""
    try:
        idx = int(index_raw)
    except ValueError:
        abort(400, "invalid index")
    cfg_path = _resolve_config_path(path)
    cfg = _read_json(cfg_path)
    cfg.setdefault("address", {"exact": {}, "regex": []})
    arr = cfg["address"].get("regex", [])
    if isinstance(arr, list) and 0 <= idx < len(arr):
        arr.pop(idx)
        cfg["address"]["regex"] = arr
    _save_config(path, cfg)
    return redirect(url_for("index", path=path, info="已删除 顾客地址 regex"))


@app.post("/addr/disamb/add")
def addr_disamb_add():
    path = request.values.get("path") or ""
    rid = (request.form.get("id") or "").strip()
    mode = (request.form.get("mode") or "exact").strip()
    match = (request.form.get("match") or "").strip()
    pattern = (request.form.get("pattern") or "").strip()
    flags = (request.form.get("flags") or "").strip()
    title = (request.form.get("title") or "").strip()
    remember_raw = (request.form.get("remember") or "true").strip().lower()
    remember = remember_raw in ("1", "true", "yes", "y", "on")

    opt1_label = (request.form.get("opt1_label") or "").strip()
    opt1_replace = (request.form.get("opt1_replace") or "").strip()
    opt2_label = (request.form.get("opt2_label") or "").strip()
    opt2_replace = (request.form.get("opt2_replace") or "").strip()

    if mode not in ("exact", "regex"):
        mode = "exact"
    if mode == "exact" and not match:
        abort(400, "match required for exact")
    if mode == "regex" and not pattern:
        abort(400, "pattern required for regex")

    options: list[dict[str, str]] = []
    if opt1_replace:
        options.append({"label": opt1_label, "replace": opt1_replace})
    if opt2_replace:
        options.append({"label": opt2_label, "replace": opt2_replace})
    if not options:
        abort(400, "at least one option replace required")

    # basic regex validation
    if mode == "regex":
        import re

        try:
            re.compile(pattern, flags=_parse_re_flags(flags))
        except re.error as e:
            state = _load_state()
            state.error = f"Regex 无效：{e}"
            return render_template_string(TEMPLATE, state=state), 400

    cfg_path = _resolve_config_path(path)
    cfg = _read_json(cfg_path)
    cfg.setdefault("address", {"exact": {}, "regex": [], "disambiguate": []})
    cfg["address"].setdefault("disambiguate", [])
    cfg["address"]["disambiguate"].append(
        {
            "id": rid,
            "mode": mode,
            "match": match,
            "pattern": pattern,
            "flags": flags,
            "title": title,
            "remember": remember,
            "options": options,
        }
    )
    _save_config(path, cfg)
    return redirect(url_for("index", path=path, info="已新增 顾客地址 歧义选择规则"))


@app.post("/addr/disamb/delete")
def addr_disamb_delete():
    path = request.values.get("path") or ""
    index_raw = request.form.get("index") or ""
    try:
        idx = int(index_raw)
    except ValueError:
        abort(400, "invalid index")
    cfg_path = _resolve_config_path(path)
    cfg = _read_json(cfg_path)
    cfg.setdefault("address", {"exact": {}, "regex": [], "disambiguate": []})
    arr = cfg["address"].get("disambiguate", [])
    if isinstance(arr, list) and 0 <= idx < len(arr):
        arr.pop(idx)
        cfg["address"]["disambiguate"] = arr
    _save_config(path, cfg)
    return redirect(url_for("index", path=path, info="已删除 顾客地址 歧义选择规则"))


def _parse_re_flags(flags: str) -> int:
    import re

    m = 0
    for ch in flags:
        if ch == "i":
            m |= re.IGNORECASE
        elif ch == "m":
            m |= re.MULTILINE
        elif ch == "s":
            m |= re.DOTALL
        # ignore unknown
    return m


if __name__ == "__main__":
    # dev server
    host = os.environ.get("HOST", "0.0.0.0")
    app.run(host=host, port=int(os.environ.get("PORT", "5000")), debug=True)
