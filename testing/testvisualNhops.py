from pathlib import Path
import pandas as pd
import json, math, html as html_lib

csv_path = Path("../data/transactionA_3hop.csv")
out_path = Path("../visuals/transactionA_3hop.html")

df = pd.read_csv(csv_path)

for col in ["from", "to", "hash"]:
    if col in df.columns:
        df[col] = df[col].fillna("").astype(str)

df["from"] = df["from"].str.lower()
df["to"] = df["to"].str.lower()

seed = "Parent"

valid = df[
    df["from"].str.startswith("0x") &
    df["to"].str.startswith("0x") &
    (df["to"] != "")
].copy()

addresses = sorted(set(valid["from"]) | set(valid["to"]))

# Keep ALL hop values found in the dataset, rather than hardcoding 0/1/2.
hop_values = sorted(pd.to_numeric(valid["hop"], errors="coerce").dropna().astype(int).unique().tolist())

out_degree = valid.groupby("from").size().to_dict()
in_degree = valid.groupby("to").size().to_dict()

nodes = []
n = max(len(addresses), 1)

for i, addr in enumerate(addresses):
    angle = 2 * math.pi * i / n
    radius = 300 + 50 * (i % 6)
    degree = int(out_degree.get(addr, 0) + in_degree.get(addr, 0))

    nodes.append({
        "id": addr,
        "label": "A (seed)" if addr == seed else f"{addr[:8]}...{addr[-6:]}",
        "title": (
            f"<b>Address</b><br>{addr}<br><br>"
            f"Outgoing: {out_degree.get(addr, 0)}<br>"
            f"Incoming: {in_degree.get(addr, 0)}"
        ),
        "x": radius * math.cos(angle),
        "y": radius * math.sin(angle),
        "size": 32 if addr == seed else max(14, min(28, 14 + degree * 2)),
        "font": {"size": 12 if addr == seed else 10}
    })

edges = []

for idx, row in valid.iterrows():
    try:
        value_eth = int(str(row.get("value", "0"))) / 10**18
    except Exception:
        value_eth = 0

    hop = int(row["hop"])
    tx_hash = str(row.get("hash", ""))
    block = str(row.get("blockNumber", ""))

    title = (
        f"<b>Cash-flow transaction</b><br>"
        f"Hop: {hop}<br>"
        f"Hash: {html_lib.escape(tx_hash)}<br>"
        f"Block: {html_lib.escape(block)}<br>"
        f"From: {html_lib.escape(row['from'])}<br>"
        f"To: {html_lib.escape(row['to'])}<br>"
        f"Value: {value_eth:.18g} ETH<br>"
        f"Gas used: {html_lib.escape(str(row.get('gasUsed', '')))}<br>"
        f"Gas price: {html_lib.escape(str(row.get('gasPrice', '')))}"
    )

    edges.append({
        "id": f"e{idx}",
        "from": row["from"],
        "to": row["to"],
        "arrows": "to",
        "label": f"{value_eth:g} ETH" if value_eth else "",
        "title": title,
        "hop": hop
    })

data = {
    "nodes": nodes,
    "edges": edges,
    "seed": seed,
    "total_rows": len(df),
    "valid_edges": len(valid),
    "unique_addresses": len(addresses),
    "unique_txs": int(df["hash"].nunique()) if "hash" in df.columns else len(df),
    "hops": hop_values
}

data_json = json.dumps(data).replace("</", "<\\/")

html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Transaction A — N-Hop Interactive Cash Flow</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
body{{margin:0;font-family:Arial,sans-serif;background:#0f172a;color:#e5e7eb}}
#top{{padding:14px 18px;background:#111827;border-bottom:1px solid #334155}}
h2{{margin:0 0 6px;font-size:20px}}
#stats{{color:#94a3b8;font-size:13px}}
#controls{{display:flex;gap:8px;flex-wrap:wrap;padding:10px 18px;background:#111827}}
button,input,select{{border:1px solid #475569;border-radius:7px;padding:8px 10px;background:#1e293b;color:#e5e7eb}}
button{{cursor:pointer}} button:hover{{background:#334155}}
#search{{min-width:240px;flex:1;max-width:430px}}
#network{{height:calc(100vh - 125px);min-height:520px;background:#f8fafc}}
#info{{position:absolute;right:18px;top:125px;width:350px;max-width:calc(100vw - 36px);max-height:70%;overflow:auto;background:rgba(15,23,42,.97);border:1px solid #475569;border-radius:10px;padding:12px;display:none;z-index:10;word-break:break-word;line-height:1.45}}
#info b{{color:#f8fafc}}
.legend{{position:absolute;left:18px;bottom:18px;background:rgba(15,23,42,.94);border:1px solid #475569;border-radius:8px;padding:9px 11px;font-size:12px;z-index:5}}
.dot{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;background:#f59e0b}}
</style>
</head>
<body>
<div id="top">
<h2>Transaction A — N-Hop Cash-Flow Graph</h2>
<div id="stats"></div>
</div>

<div id="controls">
<input id="search" placeholder="Search address or transaction hash">
<select id="hopFilter"></select>
<button id="fit" type="button">Fit graph</button>
<button id="focusSeed" type="button">Focus A</button>
<button id="reset" type="button">Reset</button>
<button id="physics" type="button">Toggle physics</button>
<button id="labels" type="button">Toggle labels</button>
</div>

<div id="network"></div>
<div class="legend"><span class="dot"></span>A = starting address</div>
<div id="info"></div>

<script>
const DATA = {data_json};

const nodes = new vis.DataSet(DATA.nodes);
const edges = new vis.DataSet(DATA.edges);

const network = new vis.Network(
    document.getElementById('network'),
    {{nodes, edges}},
    {{
        autoResize:true,
        interaction:{{
            hover:true,
            navigationButtons:true,
            keyboard:true,
            multiselect:false
        }},
        physics:{{
            enabled:true,
            stabilization:{{iterations:350}},
            barnesHut:{{
                gravitationalConstant:-7000,
                centralGravity:0.12,
                springLength:170,
                springConstant:0.035,
                damping:0.82
            }}
        }},
        nodes:{{
            shape:'dot',
            font:{{size:10,color:'#111827'}},
            color:{{
                background:'#ffffff',
                border:'#334155',
                highlight:{{background:'#dbeafe',border:'#2563eb'}}
            }}
        }},
        edges:{{
            smooth:{{type:'dynamic'}},
            color:{{color:'#94a3b8',highlight:'#2563eb'}},
            font:{{size:9,color:'#334155',strokeWidth:3,strokeColor:'#f8fafc'}}
        }}
    }}
);

document.getElementById('stats').textContent =
    `${{DATA.total_rows}} collected rows · ${{DATA.unique_txs}} unique transactions · ` +
    `${{DATA.unique_addresses}} addresses · ${{DATA.valid_edges}} cash-flow edges · ` +
    `${{DATA.hops.length}} hop levels`;

const hopFilter = document.getElementById('hopFilter');

const allOption = document.createElement('option');
allOption.value = 'all';
allOption.textContent = 'All hops';
hopFilter.appendChild(allOption);

// Dynamically create however many hop filters exist in the CSV.
DATA.hops.forEach(hop => {{
    const option = document.createElement('option');
    option.value = String(hop);
    option.textContent = `Hop ${{hop}}`;
    hopFilter.appendChild(option);
}});

const info = document.getElementById('info');

function showNodeInfo(id) {{
    const outgoing = DATA.edges.filter(e => e.from === id).length;
    const incoming = DATA.edges.filter(e => e.to === id).length;

    info.style.display = 'block';
    info.innerHTML =
        `<b>Wallet / Contract</b><br>${{id}}<br><br>` +
        `<span style="color:#94a3b8">Outgoing transactions: ${{outgoing}}<br>` +
        `Incoming transactions: ${{incoming}}</span>`;
}}

network.on('click', params => {{
    if(params.nodes.length) {{
        showNodeInfo(params.nodes[0]);
    }} else if(params.edges.length) {{
        const e = edges.get(params.edges[0]);
        info.style.display='block';
        info.innerHTML=e.title;
    }} else {{
        info.style.display='none';
    }}
}});

document.getElementById('fit').onclick = () =>
    network.fit({{animation:{{duration:500}}}});

document.getElementById('focusSeed').onclick = () => {{
    network.selectNodes([DATA.seed]);
    network.focus(DATA.seed, {{scale:1.5,animation:{{duration:500}}}});
    showNodeInfo(DATA.seed);
}};

document.getElementById('reset').onclick = () => {{
    DATA.edges.forEach(e => edges.update({{id:e.id, hidden:false}}));
    hopFilter.value='all';
    network.fit({{animation:{{duration:500}}}});
    info.style.display='none';
}};

let physicsOn=true;
document.getElementById('physics').onclick=()=>{{
    physicsOn=!physicsOn;
    network.setOptions({{physics:{{enabled:physicsOn}}}});
}};

let labelsOn=true;
document.getElementById('labels').onclick=()=>{{
    labelsOn=!labelsOn;
    DATA.edges.forEach(e=>edges.update({{id:e.id,label:labelsOn?e.label:''}}));
}};

hopFilter.addEventListener('change', e => {{
    const selected=e.target.value;

    DATA.edges.forEach(edge => {{
        edges.update({{
            id:edge.id,
            hidden:selected!=='all' && String(edge.hop)!==selected
        }});
    }});
}});

document.getElementById('search').addEventListener('keydown', e => {{
    if(e.key!=='Enter') return;

    const q=e.target.value.trim().toLowerCase();
    if(!q) return;

    const node=DATA.nodes.find(n=>n.id.toLowerCase().includes(q));

    if(node) {{
        network.selectNodes([node.id]);
        network.focus(node.id,{{scale:1.5,animation:{{duration:500}}}});
        showNodeInfo(node.id);
        return;
    }}

    const edge=DATA.edges.find(x=>x.title.toLowerCase().includes(q));

    if(edge) {{
        network.selectEdges([edge.id]);
        network.focus(edge.from,{{scale:1.3,animation:{{duration:500}}}});
        info.style.display='block';
        info.innerHTML=edge.title;
        return;
    }}

    alert('No matching address or transaction hash found.');
}});
</script>
</body>
</html>
"""

out_path.write_text(html_doc, encoding="utf-8")

print(f"Created: {out_path}")
print(f"Rows: {len(df)}")
print(f"Unique transactions: {data['unique_txs']}")
print(f"Addresses: {len(addresses)}")
print(f"Cash-flow edges: {len(valid)}")
print(f"Hop levels found: {hop_values}")
