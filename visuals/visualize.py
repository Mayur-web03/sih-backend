from pathlib import Path
import pandas as pd
import json
import math
import html as html_lib


class TransactionVisualizer:

    # ============================================================
    # INITIALIZATION
    # ============================================================

    def __init__(
        self,
        start_address,
        max_hops=5
    ):

        self.start_address = start_address.lower()
        self.max_hops = max_hops

        # --------------------------------------------------------
        # Find backend directory
        # --------------------------------------------------------

        self.backend_dir = (
            Path(__file__).resolve().parent.parent
        )

        # --------------------------------------------------------
        # HTML output directory
        # --------------------------------------------------------

        self.visuals_dir = (
            self.backend_dir / "visuals"
        )

        self.visuals_dir.mkdir(
            parents=True,
            exist_ok=True
        )

    # ============================================================
    # PREPARE DATA
    # ============================================================

    def _prepare_data(self, df):

        if df is None or df.empty:
            return pd.DataFrame()

        df = df.copy()

        # --------------------------------------------------------
        # Make sure important columns exist
        # --------------------------------------------------------

        for col in ["from", "to", "tx_hash", "hash"]:

            if col in df.columns:

                df[col] = (
                    df[col]
                    .fillna("")
                    .astype(str)
                )

        # --------------------------------------------------------
        # Support both:
        #
        # tx_hash
        #
        # and old:
        #
        # hash
        # --------------------------------------------------------

        if "tx_hash" in df.columns:

            df["tx_hash"] = (
                df["tx_hash"]
                .fillna("")
                .astype(str)
            )

        elif "hash" in df.columns:

            df["tx_hash"] = (
                df["hash"]
                .fillna("")
                .astype(str)
            )

        else:

            df["tx_hash"] = ""

        # --------------------------------------------------------
        # Normalize addresses
        # --------------------------------------------------------

        if "from" in df.columns:

            df["from"] = (
                df["from"]
                .fillna("")
                .astype(str)
                .str.lower()
            )

        if "to" in df.columns:

            df["to"] = (
                df["to"]
                .fillna("")
                .astype(str)
                .str.lower()
            )

        # --------------------------------------------------------
        # Make sure hop exists
        # --------------------------------------------------------

        if "hop" not in df.columns:

            df["hop"] = 0

        df["hop"] = pd.to_numeric(
            df["hop"],
            errors="coerce"
        ).fillna(0).astype(int)

        return df

    # ============================================================
    # GET VALID TRANSACTIONS
    # ============================================================

    def _get_valid_transactions(self, df):

        if df.empty:
            return df

        valid = df[
            df["from"].str.startswith("0x") &
            df["to"].str.startswith("0x") &
            (df["to"] != "")
        ].copy()

        return valid

    # ============================================================
    # CREATE NODES
    # ============================================================

    def _create_nodes(self, valid):

        addresses = sorted(
            set(valid["from"]) |
            set(valid["to"])
        )

        # --------------------------------------------------------
        # Number of transactions per address
        # --------------------------------------------------------

        out_degree = (
            valid
            .groupby("from")
            .size()
            .to_dict()
        )

        in_degree = (
            valid
            .groupby("to")
            .size()
            .to_dict()
        )

        nodes = []

        n = max(
            len(addresses),
            1
        )

        for i, addr in enumerate(addresses):

            angle = (
                2 * math.pi * i / n
            )

            radius = (
                300 + 50 * (i % 6)
            )

            degree = int(
                out_degree.get(addr, 0)
                +
                in_degree.get(addr, 0)
            )

            # ----------------------------------------------------
            # Starting wallet
            # ----------------------------------------------------

            is_seed = (
                addr == self.start_address
            )

            nodes.append({

                "id": addr,

                "label": (
                    "START"
                    if is_seed
                    else
                    f"{addr[:8]}...{addr[-6:]}"
                ),

                "title": (

                    f"<b>Address</b><br>"
                    f"{html_lib.escape(addr)}"
                    f"<br><br>"
                    f"<b>Outgoing:</b> "
                    f"{out_degree.get(addr, 0)}"
                    f"<br>"
                    f"<b>Incoming:</b> "
                    f"{in_degree.get(addr, 0)}"

                ),

                "x": (
                    radius * math.cos(angle)
                ),

                "y": (
                    radius * math.sin(angle)
                ),

                "size": (
                    36
                    if is_seed
                    else
                    max(
                        14,
                        min(
                            28,
                            14 + degree * 2
                        )
                    )
                ),

                "font": {
                    "size": (
                        13
                        if is_seed
                        else 10
                    )
                }

            })

        return nodes

    # ============================================================
    # CREATE EDGES
    # ============================================================

    def _create_edges(self, valid):

        edges = []

        for idx, row in valid.iterrows():

            # ----------------------------------------------------
            # Convert Wei → ETH
            # ----------------------------------------------------

            try:

                value_eth = (
                    int(
                        str(
                            row.get(
                                "value",
                                "0"
                            )
                        )
                    )
                    / 10**18
                )

            except Exception:

                value_eth = 0

            # ----------------------------------------------------
            # Transaction information
            # ----------------------------------------------------

            hop = int(
                row.get(
                    "hop",
                    0
                )
            )

            tx_hash = str(
                row.get(
                    "tx_hash",
                    ""
                )
            )

            block = str(
                row.get(
                    "block_number",
                    row.get(
                        "blockNumber",
                        ""
                    )
                )
            )

            gas_used = str(
                row.get(
                    "gas_used",
                    row.get(
                        "gasUsed",
                        ""
                    )
                )
            )

            gas_price = str(
                row.get(
                    "gas_price",
                    row.get(
                        "gasPrice",
                        ""
                    )
                )
            )

            # ----------------------------------------------------
            # Direction
            # ----------------------------------------------------

            direction = str(
                row.get(
                    "direction",
                    ""
                )
            )

            # ----------------------------------------------------
            # Tooltip
            # ----------------------------------------------------

            title = (

                f"<b>Transaction</b><br>"

                f"<b>Direction:</b> "
                f"{html_lib.escape(direction)}"
                f"<br>"

                f"<b>Hop:</b> "
                f"{hop}"
                f"<br>"

                f"<b>Hash:</b> "
                f"{html_lib.escape(tx_hash)}"
                f"<br>"

                f"<b>Block:</b> "
                f"{html_lib.escape(block)}"
                f"<br><br>"

                f"<b>From:</b> "
                f"{html_lib.escape(row['from'])}"
                f"<br>"

                f"<b>To:</b> "
                f"{html_lib.escape(row['to'])}"
                f"<br>"

                f"<b>Value:</b> "
                f"{value_eth:.18g} ETH"
                f"<br>"

                f"<b>Gas used:</b> "
                f"{html_lib.escape(gas_used)}"
                f"<br>"

                f"<b>Gas price:</b> "
                f"{html_lib.escape(gas_price)}"

            )

            edges.append({

                "id": f"e{idx}",

                "from": row["from"],

                "to": row["to"],

                "arrows": "to",

                "label": (
                    f"{value_eth:g} ETH"
                    if value_eth
                    else ""
                ),

                "title": title,

                "hop": hop

            })

        return edges

    # ============================================================
    # CREATE HTML
    # ============================================================

    def _create_html(
        self,
        df,
        output_path,
        title
    ):

        df = self._prepare_data(df)

        valid = self._get_valid_transactions(
            df
        )

        # --------------------------------------------------------
        # Nodes
        # --------------------------------------------------------

        nodes = self._create_nodes(
            valid
        )

        # --------------------------------------------------------
        # Edges
        # --------------------------------------------------------

        edges = self._create_edges(
            valid
        )

        # --------------------------------------------------------
        # Hop values
        # --------------------------------------------------------

        if not valid.empty:

            hop_values = sorted(
                valid["hop"]
                .unique()
                .tolist()
            )

        else:

            hop_values = []

        # --------------------------------------------------------
        # Statistics
        # --------------------------------------------------------

        unique_addresses = len(nodes)

        if "tx_hash" in df.columns:

            unique_txs = int(
                df["tx_hash"].nunique()
            )

        else:

            unique_txs = len(df)

        # --------------------------------------------------------
        # Data passed into JavaScript
        # --------------------------------------------------------

        data = {

            "nodes": nodes,

            "edges": edges,

            "seed": self.start_address,

            "total_rows": len(df),

            "valid_edges": len(valid),

            "unique_addresses": (
                unique_addresses
            ),

            "unique_txs": unique_txs,

            "hops": hop_values

        }

        data_json = (
            json.dumps(data)
            .replace(
                "</",
                "<\\/"
            )
        )

        # ========================================================
        # HTML
        # ========================================================

        html_doc = f"""<!doctype html>

<html lang="en">

<head>

<meta charset="utf-8">

<meta
name="viewport"
content="width=device-width, initial-scale=1"
>

<title>{html_lib.escape(title)}</title>

<script
src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js">
</script>

<style>

body{{
    margin:0;
    font-family:Arial,sans-serif;
    background:#0f172a;
    color:#e5e7eb
}}

#top{{
    padding:14px 18px;
    background:#111827;
    border-bottom:1px solid #334155
}}

h2{{
    margin:0 0 6px;
    font-size:20px
}}

#stats{{
    color:#94a3b8;
    font-size:13px
}}

#controls{{
    display:flex;
    gap:8px;
    flex-wrap:wrap;
    padding:10px 18px;
    background:#111827
}}

button,
input,
select{{
    border:1px solid #475569;
    border-radius:7px;
    padding:8px 10px;
    background:#1e293b;
    color:#e5e7eb
}}

button{{
    cursor:pointer
}}

button:hover{{
    background:#334155
}}

#search{{
    min-width:240px;
    flex:1;
    max-width:430px
}}

#network{{
    height:calc(100vh - 125px);
    min-height:520px;
    background:#f8fafc
}}

#info{{
    position:absolute;
    right:18px;
    top:125px;
    width:350px;
    max-width:calc(100vw - 36px);
    max-height:70%;
    overflow:auto;
    background:rgba(15,23,42,.97);
    border:1px solid #475569;
    border-radius:10px;
    padding:12px;
    display:none;
    z-index:10;
    word-break:break-word;
    line-height:1.45
}}

#info b{{
    color:#f8fafc
}}

.legend{{
    position:absolute;
    left:18px;
    bottom:18px;
    background:rgba(15,23,42,.94);
    border:1px solid #475569;
    border-radius:8px;
    padding:9px 11px;
    font-size:12px;
    z-index:5
}}

.dot{{
    display:inline-block;
    width:10px;
    height:10px;
    border-radius:50%;
    margin-right:5px;
    background:#f59e0b
}}

</style>

</head>

<body>

<div id="top">

<h2>{html_lib.escape(title)}</h2>

<div id="stats"></div>

</div>


<div id="controls">

<input
id="search"
placeholder="Search address or transaction hash"
>

<select id="hopFilter"></select>

<button id="fit" type="button">
Fit graph
</button>

<button id="focusSeed" type="button">
Focus START
</button>

<button id="reset" type="button">
Reset
</button>

<button id="physics" type="button">
Toggle physics
</button>

<button id="labels" type="button">
Toggle labels
</button>

</div>


<div id="network"></div>

<div class="legend">
<span class="dot"></span>
START = starting address
</div>

<div id="info"></div>


<script>

const DATA = {data_json};


const nodes = new vis.DataSet(
    DATA.nodes
);


const edges = new vis.DataSet(
    DATA.edges
);


const network = new vis.Network(

    document.getElementById(
        'network'
    ),

    {{
        nodes,
        edges
    }},

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

            stabilization:{{
                iterations:350
            }},

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

            font:{{
                size:10,
                color:'#111827'
            }},

            color:{{

                background:'#ffffff',

                border:'#334155',

                highlight:{{
                    background:'#dbeafe',
                    border:'#2563eb'
                }}

            }}

        }},

        edges:{{

            smooth:{{
                type:'dynamic'
            }},

            color:{{

                color:'#94a3b8',

                highlight:'#2563eb'

            }},

            font:{{

                size:9,

                color:'#334155',

                strokeWidth:3,

                strokeColor:'#f8fafc'

            }}

        }}

    }}

);


document.getElementById(
    'stats'
).textContent =

    `${{DATA.total_rows}} collected rows · ` +

    `${{DATA.unique_txs}} unique transactions · ` +

    `${{DATA.unique_addresses}} addresses · ` +

    `${{DATA.valid_edges}} transaction edges · ` +

    `${{DATA.hops.length}} hop levels`;


const hopFilter =
    document.getElementById(
        'hopFilter'
    );


const allOption =
    document.createElement(
        'option'
    );

allOption.value = 'all';

allOption.textContent =
    'All hops';

hopFilter.appendChild(
    allOption
);


// ------------------------------------------------------------
// Dynamic hop filters
// ------------------------------------------------------------

DATA.hops.forEach(hop => {{

    const option =
        document.createElement(
            'option'
        );

    option.value =
        String(hop);

    option.textContent =
        `Hop ${{hop}}`;

    hopFilter.appendChild(
        option
    );

}});


const info =
    document.getElementById(
        'info'
    );


// ------------------------------------------------------------
// NODE INFORMATION
// ------------------------------------------------------------

function showNodeInfo(id) {{

    const outgoing =
        DATA.edges.filter(
            e => e.from === id
        ).length;

    const incoming =
        DATA.edges.filter(
            e => e.to === id
        ).length;

    info.style.display =
        'block';

    info.innerHTML =

        `<b>Wallet / Contract</b><br>` +

        `${{id}}<br><br>` +

        `<span style="color:#94a3b8">` +

        `Outgoing transactions: ${{outgoing}}<br>` +

        `Incoming transactions: ${{incoming}}` +

        `</span>`;

}}


// ------------------------------------------------------------
// CLICK HANDLER
// ------------------------------------------------------------

network.on(
    'click',
    params => {{

        if (
            params.nodes.length
        ) {{

            showNodeInfo(
                params.nodes[0]
            );

        }}

        else if (
            params.edges.length
        ) {{

            const e =
                edges.get(
                    params.edges[0]
                );

            info.style.display =
                'block';

            info.innerHTML =
                e.title;

        }}

        else {{

            info.style.display =
                'none';

        }}

    }}
);


// ------------------------------------------------------------
// FIT
// ------------------------------------------------------------

document.getElementById(
    'fit'
).onclick = () =>

    network.fit({{
        animation:{{
            duration:500
        }}
    }});


// ------------------------------------------------------------
// FOCUS START
// ------------------------------------------------------------

document.getElementById(
    'focusSeed'
).onclick = () => {{

    network.selectNodes([
        DATA.seed
    ]);

    network.focus(
        DATA.seed,
        {{
            scale:1.5,
            animation:{{
                duration:500
            }}
        }}
    );

    showNodeInfo(
        DATA.seed
    );

}};


// ------------------------------------------------------------
// RESET
// ------------------------------------------------------------

document.getElementById(
    'reset'
).onclick = () => {{

    DATA.edges.forEach(
        e => edges.update({{
            id:e.id,
            hidden:false
        }})
    );

    hopFilter.value =
        'all';

    network.fit({{
        animation:{{
            duration:500
        }}
    }});

    info.style.display =
        'none';

}};


// ------------------------------------------------------------
// PHYSICS
// ------------------------------------------------------------

let physicsOn = true;

document.getElementById(
    'physics'
).onclick = () => {{

    physicsOn =
        !physicsOn;

    network.setOptions({{
        physics:{{
            enabled:physicsOn
        }}
    }});

}};


// ------------------------------------------------------------
// LABELS
// ------------------------------------------------------------

let labelsOn = true;

document.getElementById(
    'labels'
).onclick = () => {{

    labelsOn =
        !labelsOn;

    DATA.edges.forEach(
        e => edges.update({{

            id:e.id,

            label:
                labelsOn
                ? e.label
                : ''

        }})
    );

}};


// ------------------------------------------------------------
// HOP FILTER
// ------------------------------------------------------------

hopFilter.addEventListener(
    'change',
    e => {{

        const selected =
            e.target.value;

        DATA.edges.forEach(
            edge => {{

                edges.update({{

                    id:edge.id,

                    hidden:
                        selected !== 'all'
                        &&
                        String(edge.hop)
                        !== selected

                }});

            }}
        );

    }}
);


// ------------------------------------------------------------
// SEARCH
// ------------------------------------------------------------

document.getElementById(
    'search'
).addEventListener(
    'keydown',
    e => {{

        if (
            e.key !== 'Enter'
        )
            return;

        const q =
            e.target.value
            .trim()
            .toLowerCase();

        if (!q)
            return;


        // Search wallet
        const node =
            DATA.nodes.find(
                n =>
                    n.id
                    .toLowerCase()
                    .includes(q)
            );


        if (node) {{

            network.selectNodes([
                node.id
            ]);

            network.focus(
                node.id,
                {{
                    scale:1.5,
                    animation:{{
                        duration:500
                    }}
                }}
            );

            showNodeInfo(
                node.id
            );

            return;

        }}


        // Search transaction
        const edge =
            DATA.edges.find(
                x =>
                    x.title
                    .toLowerCase()
                    .includes(q)
            );


        if (edge) {{

            network.selectEdges([
                edge.id
            ]);

            network.focus(
                edge.from,
                {{
                    scale:1.3,
                    animation:{{
                        duration:500
                    }}
                }}
            );

            info.style.display =
                'block';

            info.innerHTML =
                edge.title;

            return;

        }}


        alert(
            'No matching address or transaction hash found.'
        );

    }}
);

</script>

</body>

</html>
"""

        output_path.write_text(
            html_doc,
            encoding="utf-8"
        )

        print(
            f"Created: {output_path}"
        )

        print(
            f"Rows: {len(df)}"
        )

        print(
            f"Unique transactions: "
            f"{unique_txs}"
        )

        print(
            f"Addresses: "
            f"{unique_addresses}"
        )

        print(
            f"Edges: "
            f"{len(valid)}"
        )

        print(
            f"Hops: "
            f"{hop_values}"
        )

    # ============================================================
    # 1. VISUALIZE INWARD
    # ============================================================

    def visualize_inward(
        self,
        inward_df
    ):

        output_path = (

            self.visuals_dir /

            f"{self.start_address}_"
            f"inward.html"

        )

        self._create_html(

            df=inward_df,

            output_path=output_path,

            title=(
                "Transaction A — "
                "N-Hop Inward Cash Flow"
            )

        )

        return output_path

    # ============================================================
    # 2. VISUALIZE OUTWARD
    # ============================================================

    def visualize_outward(
        self,
        outward_df
    ):

        output_path = (

            self.visuals_dir /

            f"{self.start_address}_"
            f"outward.html"

        )

        self._create_html(

            df=outward_df,

            output_path=output_path,

            title=(
                "Transaction A — "
                "N-Hop Outward Cash Flow"
            )

        )

        return output_path

    # ============================================================
    # 3. VISUALIZE INWARD + OUTWARD
    # ============================================================

    def visualize_inward_outward(

        self,
        inward_df,
        outward_df

    ):

        # --------------------------------------------------------
        # Combine both datasets
        # --------------------------------------------------------

        if (
            inward_df is None
            or inward_df.empty
        ):

            combined_df = (
                outward_df.copy()
                if outward_df is not None
                else pd.DataFrame()
            )

        elif (
            outward_df is None
            or outward_df.empty
        ):

            combined_df = (
                inward_df.copy()
            )

        else:

            combined_df = pd.concat(

                [
                    inward_df,
                    outward_df
                ],

                ignore_index=True

            )

        # --------------------------------------------------------
        # Remove duplicate transactions
        # --------------------------------------------------------

        if (
            not combined_df.empty
            and "tx_hash" in combined_df.columns
        ):

            combined_df = (
                combined_df
                .drop_duplicates(
                    subset=["tx_hash"]
                )
            )

        # --------------------------------------------------------
        # Output
        # --------------------------------------------------------

        output_path = (

            self.visuals_dir /

            f"{self.start_address}_"
            f"inward_outward.html"

        )

        self._create_html(

            df=combined_df,

            output_path=output_path,

            title=(
                "Transaction A — "
                "N-Hop Inward + Outward "
                "Cash Flow"
            )

        )

        return output_path