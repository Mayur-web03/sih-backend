from pathlib import Path
import pandas as pd
import json
import html

csv_path = Path("../data/transactionA_outward.csv")
out_path = Path("../visuals/transactionA_outward.html")

df = pd.read_csv(csv_path)

# Normalize addresses and ignore contract-creation rows where "to" is missing.
df["from"] = df["from"].astype(str).str.lower()
df["to"] = df["to"].where(df["to"].notna(), None)
df["to"] = df["to"].apply(lambda x: str(x).lower() if x is not None else None)

valid = df[df["to"].notna() & (df["to"] != "nan")].copy()

# Build nodes
addresses = sorted(set(valid["from"]) | set(valid["to"]))
seed = "0x846943093f519a47734765bef9ee1136800beb9c"

# Simple deterministic initial layout; JavaScript physics can refine it.
import math
n = max(len(addresses), 1)
nodes = []
for i, addr in enumerate(addresses):
    angle = 2 * math.pi * i / n
    radius = 180 + 25 * (i % 7)
    nodes.append({
        "id": addr,
        "label": addr[:8] + "..." + addr[-6:],
        "title": f"<b>{addr}</b><br>Transactions involving this address: "
                 f"{int((df['from'] == addr).sum() + (df['to'] == addr).sum())}",
        "x": radius * math.cos(angle),
        "y": radius * math.sin(angle),
        "size": 28 if addr == seed else 18,
        "borderWidth": 3 if addr == seed else 1,
    })

edges = []
for idx, row in valid.iterrows():
    try:
        value_eth = int(str(row["value"])) / 10**18
    except Exception:
        value_eth = 0

    tx_hash = str(row["hash"])
    block = str(row["blockNumber"])

    edges.append({
        "id": f"e{idx}",
        "from": row["from"],
        "to": row["to"],
        "arrows": "to",
        "label": f"{value_eth:g} ETH" if value_eth else "",
        "title": (
            f"<b>Transaction</b><br>"
            f"Hash: {html.escape(tx_hash)}<br>"
            f"Block: {html.escape(block)}<br>"
            f"From: {html.escape(row['from'])}<br>"
            f"To: {html.escape(row['to'])}<br>"
            f"Value: {value_eth:.18g} ETH<br>"
            f"Gas used: {html.escape(str(row.get('gasUsed', '')))}<br>"
            f"Gas price: {html.escape(str(row.get('gasPrice', '')))}"
        )
    })

creation_count = int(df["to"].isna().sum())

data = {
    "nodes": nodes,
    "edges": edges,
    "seed": seed,
    "total_rows": len(df),
    "valid_edges": len(valid),
    "contract_creations": creation_count
}

# Self-contained HTML using vis-network from CDN.
# The CSV data itself is embedded, so opening the HTML does not need the CSV.
data_json = json.dumps(data).replace("</", "<\\/")

html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Transaction A — Interactive Graph</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
body {{ margin:0; font-family:Arial,sans-serif; background:#0f172a; color:#e5e7eb; }}
#top {{ padding:14px 18px; background:#111827; border-bottom:1px solid #334155; }}
h2 {{ margin:0 0 6px; font-size:20px; }}
#stats {{ color:#94a3b8; font-size:13px; }}
#controls {{ display:flex; gap:8px; flex-wrap:wrap; padding:10px 18px; background:#111827; }}
button, input {{ border:1px solid #475569; border-radius:7px; padding:8px 10px; background:#1e293b; color:#e5e7eb; }}
button {{ cursor:pointer; }}
button:hover {{ background:#334155; }}
#search {{ min-width:280px; flex:1; max-width:520px; }}
#network {{ height:calc(100vh - 125px); min-height:520px; background:#f8fafc; }}
#info {{
  position:absolute; right:18px; top:125px; width:330px; max-width:calc(100vw - 36px);
  background:rgba(15,23,42,.96); border:1px solid #475569; border-radius:10px;
  padding:12px; display:none; z-index:10; word-break:break-word;
}}
#info b {{ color:#f8fafc; }}
.small {{ color:#94a3b8; font-size:12px; }}
</style>
</head>
<body>
<div id="top">
  <h2>Transaction A — Interactive Ethereum Graph</h2>
  <div id="stats"></div>
</div>
<div id="controls">
  <input id="search" placeholder="Search wallet address or transaction hash">
  <button id="fit">Fit graph</button>
  <button id="reset">Reset</button>
  <button id="physics">Toggle physics</button>
  <button id="labels">Toggle edge labels</button>
</div>
<div id="network"></div>
<div id="info"></div>

<script>
const DATA = {data_json};

const nodes = new vis.DataSet(DATA.nodes);
const edges = new vis.DataSet(DATA.edges);

const container = document.getElementById('network');
const options = {{
  autoResize: true,
  interaction: {{
    hover: true,
    navigationButtons: true,
    keyboard: true,
    multiselect: false
  }},
  physics: {{
    enabled: true,
    stabilization: {{ iterations: 250 }},
    barnesHut: {{
      gravitationalConstant: -5000,
      centralGravity: 0.15,
      springLength: 150,
      springConstant: 0.035,
      damping: 0.8
    }}
  }},
  nodes: {{
    shape: 'dot',
    font: {{ size: 12, color: '#111827' }},
    color: {{
      background: '#ffffff',
      border: '#334155',
      highlight: {{ background: '#dbeafe', border: '#2563eb' }}
    }}
  }},
  edges: {{
    smooth: {{ type: 'dynamic' }},
    color: {{ color:'#94a3b8', highlight:'#2563eb' }},
    font: {{ size: 10, color:'#334155', strokeWidth:3, strokeColor:'#f8fafc' }}
  }}
}};

const network = new vis.Network(container, {{nodes, edges}}, options);

document.getElementById('stats').textContent =
  `${{DATA.total_rows}} transactions loaded · ${{DATA.valid_edges}} address-to-address edges · ` +
  `${{DATA.contract_creations}} contract-creation transactions (shown as missing "to")`;

const info = document.getElementById('info');

network.on('click', function(params) {{
  if (params.nodes.length) {{
    const id = params.nodes[0];
    const outgoing = edges.get({{filter:e => e.from === id}}).length;
    const incoming = edges.get({{filter:e => e.to === id}}).length;
    info.style.display = 'block';
    info.innerHTML =
      `<b>Address</b><br>${{id}}<br><br>` +
      `<span class="small">Outgoing transactions: ${{outgoing}}<br>` +
      `Incoming transactions: ${{incoming}}</span>`;
  }} else if (params.edges.length) {{
    const e = edges.get(params.edges[0]);
    info.style.display = 'block';
    info.innerHTML = e.title;
  }} else {{
    info.style.display = 'none';
  }}
}});

document.getElementById('fit').onclick = () =>
  network.fit({{animation: {{duration: 500}}}});

document.getElementById('reset').onclick = () => {{
  network.setOptions(options);
  network.fit({{animation: {{duration: 500}}}});
  info.style.display = 'none';
}};

let physicsOn = true;
document.getElementById('physics').onclick = () => {{
  physicsOn = !physicsOn;
  network.setOptions({{physics: {{enabled: physicsOn}}}});
}};

let labelsOn = true;
document.getElementById('labels').onclick = () => {{
  labelsOn = !labelsOn;
  edges.forEach(e => edges.update({{id:e.id, label: labelsOn ? e.label : ''}}));
}};

document.getElementById('search').addEventListener('keydown', e => {{
  if (e.key !== 'Enter') return;
  const q = e.target.value.trim().toLowerCase();
  if (!q) return;

  const node = DATA.nodes.find(n => n.id.toLowerCase() === q || n.id.toLowerCase().includes(q));
  if (node) {{
    network.selectNodes([node.id]);
    network.focus(node.id, {{scale:1.4, animation:{{duration:500}}}});
    return;
  }}

  const edge = DATA.edges.find(x => x.title.toLowerCase().includes(q));
  if (edge) {{
    network.selectEdges([edge.id]);
    network.focus(edge.from, {{scale:1.3, animation:{{duration:500}}}});
    return;
  }}

  alert('No matching address or transaction hash found.');
}});
</script>
</body>
</html>
"""

out_path.write_text(html_doc, encoding="utf-8")

print(f"Created interactive graph: {out_path}")
print(f"Rows in CSV: {len(df)}")
print(f"Address-to-address transactions visualized: {len(valid)}")
print(f"Contract-creation rows with missing 'to': {creation_count}")
