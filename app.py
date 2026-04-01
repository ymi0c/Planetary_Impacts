import streamlit as st
import pandas as pd
from neo4j import GraphDatabase
from streamlit_agraph import agraph, Node, Edge, Config

# --- 1. PAGE CONFIGURATION & CUSTOM CSS ---
st.set_page_config(page_title="Planetary Impacts", layout="wide")

st.markdown("""
    <style>
    /* Force Apple System Fonts globally */
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
    }
    
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Tighten global top padding */
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 0rem !important;
    }
    
    /* Premium Metric Cards */
    div[data-testid="metric-container"] {
        background-color: #1C1C1E;
        border: 1px solid #2C2C2E;
        padding: 15px 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    </style>
    """, unsafe_allow_html=True)

# --- SECURITY & STATE INITIALIZATION ---
if "admin_authenticated" not in st.session_state:
    st.session_state.admin_authenticated = False
if "focused_nodes" not in st.session_state:
    st.session_state.focused_nodes = []

# --- 2. DATABASE CONNECTION (SECURED VIA SECRETS) ---
# --- 2. DATABASE CONNECTION (STRICT SECRETS) ---
# There are ZERO passwords in this code. It strictly reads from your private environment.
URI = st.secrets["NEO4J_URI"]
USERNAME = st.secrets["NEO4J_USERNAME"]
PASSWORD = st.secrets["NEO4J_PASSWORD"]
ADMIN_PW_SECRET = st.secrets["ADMIN_PASSWORD"]

@st.cache_resource
def init_connection():
    return GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))

driver = init_connection()

# --- THE HIGH-CONTRAST SEMANTIC COLOR PALETTE ---
color_map = {
    "EarthSystem": "#34C759",    # Emerald Green (Nature)
    "Activity": "#FF2D55",       # Neon Pink (Synthetic Human Energy / Industry)
    "Driver": "#FFD60A",         # Warning Yellow (Pressures)
    "Process": "#AF52DE",        # Scientific Purple (Mechanisms)
    "Impact": "#FF9F0A",         # Vibrant Orange (Consequences)
    "GlobalProblem": "#FF453A",  # Crisis Red (Macro Issues)
    "Response": "#007AFF",       # Deep Blue (Structured Solutions / Cooling)
    "Nodes": "#8E8E93"           # System Gray (Default/Uncategorized)
}

# --- 3. DATA FETCHING FUNCTIONS ---
def get_metrics():
    with driver.session() as session:
        # Resilient counters: Checks both native Neo4j labels and CSV-imported property labels
        sys = session.run("""
            MATCH (n) 
            WHERE (n.status IS NULL OR n.status = 'approved') 
              AND ('EarthSystem' IN labels(n) OR n.node_label = 'EarthSystem' OR n.node_label = 'Earth System') 
            RETURN count(n)
        """).single()[0]
        
        drv = session.run("""
            MATCH (n) 
            WHERE (n.status IS NULL OR n.status = 'approved') 
              AND ('Driver' IN labels(n) OR n.node_label = 'Driver') 
            RETURN count(n)
        """).single()[0]
        
        imp = session.run("""
            MATCH (n) 
            WHERE (n.status IS NULL OR n.status = 'approved') 
              AND ('Impact' IN labels(n) OR n.node_label = 'Impact') 
            RETURN count(n)
        """).single()[0]
        
        mit = session.run("""
            MATCH ()-[r]->() 
            WHERE (r.status IS NULL OR r.status = 'approved') 
              AND (type(r) = 'MITIGATES' OR type(r) = 'Mitigates' OR toUpper(r.edge_type) = 'MITIGATES') 
            RETURN count(r)
        """).single()[0]
        
        return sys, drv, imp, mit

@st.cache_data(ttl=300)
def get_available_domains():
    with driver.session() as session:
        result = session.run("MATCH (n) WHERE (n.status IS NULL OR n.status = 'approved') AND n.node_domain IS NOT NULL RETURN DISTINCT n.node_domain AS domain ORDER BY domain")
        return [record["domain"] for record in result if record["domain"]]

# UPGRADE: Dynamic Filtering Engine (with Optional Match for isolated nodes)
def get_search_data(search_term, focused_nodes=None, filter_categories=None, filter_domains=None):
    nodes, edges, added_nodes = [], [], set()
    params = {}
    
    n_cond = ["(n.status IS NULL OR n.status = 'approved')"]
    m_cond = ["(m.status IS NULL OR m.status = 'approved')"]
    r_cond = ["(r.status IS NULL OR r.status = 'approved')"]
    
    if focused_nodes and len(focused_nodes) > 0:
        n_cond.append("elementId(n) IN $focused_nodes")
        params["focused_nodes"] = focused_nodes
        
    if search_term:
        n_cond.append("toLower(n.node_name) CONTAINS toLower($search_term)")
        params["search_term"] = search_term
        
    if filter_categories and len(filter_categories) > 0:
        n_cond.append("n.node_label IN $categories")
        m_cond.append("m.node_label IN $categories")
        params["categories"] = filter_categories
        
    if filter_domains and len(filter_domains) > 0:
        n_cond.append("n.node_domain IN $domains")
        m_cond.append("m.node_domain IN $domains")
        params["domains"] = filter_domains
        
    where_n = " AND ".join(n_cond)
    where_m = " AND ".join(m_cond)
    where_r = " AND ".join(r_cond)
    
    query = f"""
    MATCH (n) 
    WHERE {where_n}
    OPTIONAL MATCH (n)-[r]-(m) 
    WHERE {where_m} AND {where_r}
    RETURN n, r, m LIMIT 300
    """

    with driver.session() as session:
        result = session.run(query, params)
        added_edges = set()
        
        for record in result:
            n, m, r = record["n"], record["m"], record["r"]
            
            # Always render the primary node
            if n is not None:
                n_label = n.get("node_label", list(n.labels)[0] if n.labels else "Nodes")
                if n.element_id not in added_nodes:
                    nodes.append(Node(id=str(n.element_id), label=n.get("node_name", n_label), title=n.get("node_name", n_label), color=color_map.get(n_label, "#8E8E93")))
                    added_nodes.add(n.element_id)
                
            # Only attempt to render the target node if it passed the optional match filter
            if m is not None:
                m_label = m.get("node_label", list(m.labels)[0] if m.labels else "Nodes")
                if m.element_id not in added_nodes:
                    nodes.append(Node(id=str(m.element_id), label=m.get("node_name", m_label), title=m.get("node_name", m_label), color=color_map.get(m_label, "#8E8E93")))
                    added_nodes.add(m.element_id)
                
            # Only attempt to render the arrow if the relationship survived the filter
            if r is not None:
                if r.element_id not in added_edges:
                    edges.append(Edge(source=str(r.start_node.element_id), target=str(r.end_node.element_id), label=r.type))
                    added_edges.add(r.element_id)
                
    return nodes, edges

# --- 4. SIDEBAR & AUTHENTICATION ---
with st.sidebar:
    st.title("Navigation")
    search_query = st.text_input("Search Database", placeholder="e.g., Biosphere, Deforestation...")
    
    st.markdown("<p style='font-size: 12px; color: #86868B; font-weight: 600; text-transform: uppercase; margin-top: 15px; margin-bottom: 5px;'>Macro Filters</p>", unsafe_allow_html=True)
    filter_categories = st.multiselect("Filter by Category", options=[k for k in color_map.keys() if k != "Nodes"])
    filter_domains = st.multiselect("Filter by Domain", options=get_available_domains())
    
    if st.session_state.focused_nodes:
        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
        if st.button("Exit Focus Mode", use_container_width=True):
            st.session_state.focused_nodes = []
            st.rerun()
            
    st.divider()
    
    st.subheader("Node Details")
    info_panel = st.empty()
    with info_panel.container():
        st.markdown('<p style="color:#86868B; font-size:14px;">Select a node in the graph to view its pathways and literature sources.</p>', unsafe_allow_html=True)
        
    st.write("")
    st.write("")
    st.divider()
    if not st.session_state.admin_authenticated:
        admin_pw = st.text_input("Admin Portal", type="password", placeholder="Enter Master Password")
        if admin_pw == ADMIN_PW_SECRET:
            st.session_state.admin_authenticated = True
            st.rerun()
    else:
        st.markdown("<p style='color: #34C759; font-size: 13px; font-weight: 600;'>Admin Access Granted</p>", unsafe_allow_html=True)
        if st.button("Secure Logout"):
            st.session_state.admin_authenticated = False
            st.rerun()

# --- 5. MAIN DASHBOARD AREA ---
st.title("Planetary Impacts Explorer")
st.markdown('<p style="color:#86868B; font-size:16px; margin-top:-15px;">A crowdsourced systems mapping of global environmental drivers and impacts.</p>', unsafe_allow_html=True)
st.write("")

sys_count, drv_count, imp_count, mit_count = get_metrics()
col1, col2, col3, col4 = st.columns(4)
col1.metric("Earth Systems", sys_count)
col2.metric("Identified Drivers", drv_count)
col3.metric("Documented Impacts", imp_count)
col4.metric("Active Mitigations", mit_count)

st.divider()

# --- SECURE DYNAMIC TAB GENERATION ---
if st.session_state.admin_authenticated:
    tab1, tab2, tab3, tab4 = st.tabs(["Graph Explorer", "Contribute Data", "Raw Database (Premium)", "Admin Dashboard"])
else:
    tab1, tab2 = st.tabs(["Graph Explorer", "Contribute Data"])

def render_graph_legend():
    legend_items = [
        ("Earth System", color_map["EarthSystem"]),
        ("Activity", color_map["Activity"]),
        ("Driver", color_map["Driver"]),
        ("Process", color_map["Process"]),
        ("Impact", color_map["Impact"]),
        ("Global Problem", color_map["GlobalProblem"]),
        ("Response", color_map["Response"])
    ]
    
    legend_html = "<div style='display: flex; flex-wrap: wrap; gap: 15px; margin-bottom: 20px; justify-content: center; background-color: #1C1C1E; padding: 12px; border-radius: 10px; border: 1px solid #2C2C2E;'>"
    for label, color in legend_items:
        legend_html += f"<div style='display: flex; align-items: center; gap: 6px;'><div style='width: 12px; height: 12px; background-color: {color}; border-radius: 50%;'></div><span style='color: #86868B; font-size: 12px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px;'>{label}</span></div>"
    legend_html += "</div>"
    st.markdown(legend_html, unsafe_allow_html=True)

# --- TAB 1: GRAPH EXPLORER ---
with tab1:
    render_graph_legend()
    
    nodes, edges = get_search_data(search_query, st.session_state.focused_nodes, filter_categories, filter_domains)

    if nodes:
        config = Config(
            width="100%", 
            height=700, 
            directed=True, 
            hierarchical=False, 
            nodeHighlightBehavior=True,
            highlightColor="#F5F5F7",
            nodes={
                "shape": "box",
                "margin": {"top": 12, "bottom": 12, "left": 18, "right": 18},
                "shapeProperties": {"borderRadius": 20},
                "font": {"color": "#F5F5F7", "size": 14, "face": "-apple-system, sans-serif"},
                "borderWidth": 0,
                "shadow": {"enabled": True, "color": "rgba(0,0,0,0.3)", "size": 5, "x": 0, "y": 2}
            },
            edges={
                "color": "#48484A",
                "smooth": {"type": "continuous"},
                "font": {"color": "#A1A1A6", "size": 11, "strokeWidth": 4, "strokeColor": "#1C1C1E", "align": "top"}
            },
            physics={
                "solver": "forceAtlas2Based",
                "forceAtlas2Based": {
                    "gravitationalConstant": -150,
                    "centralGravity": 0.01,
                    "springLength": 300,
                    "springConstant": 0.05,
                    "avoidOverlap": 1
                },
                "stabilization": {"iterations": 200} 
            },
            interaction={
                "hover": True,
                "tooltipDelay": 200,
                "hideEdgesOnDrag": True,
                "zoomSpeed": 0.3
            }
        )

        selected_node_id = agraph(nodes=nodes, edges=edges, config=config)
        
        if selected_node_id:
            with driver.session() as session:
                detail_query = "MATCH (n) WHERE elementId(n) = $node_id RETURN n"
                record = session.run(detail_query, node_id=selected_node_id).single()
                
                in_query = """
                MATCH (m)-[r]->(n) WHERE elementId(n) = $node_id 
                  AND (m.status IS NULL OR m.status = 'approved')
                  AND (r.status IS NULL OR r.status = 'approved')
                RETURN m.node_name AS source_name, type(r) AS rel_type, r.edge_quantification AS quant, r.edge_literature_source AS lit, r.edge_notes AS notes
                """
                in_records = session.run(in_query, node_id=selected_node_id).data()
                
                out_query = """
                MATCH (n)-[r]->(m) WHERE elementId(n) = $node_id 
                  AND (m.status IS NULL OR m.status = 'approved')
                  AND (r.status IS NULL OR r.status = 'approved')
                RETURN m.node_name AS target_name, type(r) AS rel_type, r.edge_quantification AS quant, r.edge_literature_source AS lit, r.edge_notes AS notes
                """
                out_records = session.run(out_query, node_id=selected_node_id).data()
                
                if record:
                    node_data = record["n"]
                    name = node_data.get("node_name", "Unnamed Node")
                    category = node_data.get("node_label", list(node_data.labels)[0] if node_data.labels else "Unknown")
                    domain = node_data.get("node_domain", "")
                    subdomain = node_data.get("node_subdomain", "")
                    spatial = node_data.get("spacial_scale", "")
                    description = node_data.get("node_description", "")
                    
                    with info_panel.container():
                        st.markdown(f"<h2 style='margin-bottom: 8px; color: #F5F5F7; font-size: 26px; font-weight: 600; line-height: 1.2; letter-spacing: -0.5px;'>{name}</h2>", unsafe_allow_html=True)
                        
                        if not st.session_state.focused_nodes:
                            if st.button("Isolate Pathway", key=f"focus_{selected_node_id}", use_container_width=True, type="primary"):
                                st.session_state.focused_nodes = [selected_node_id]
                                st.rerun()
                        else:
                            if selected_node_id not in st.session_state.focused_nodes:
                                col1, col2 = st.columns(2)
                                with col1:
                                    if st.button("Expand Focus", key=f"expand_{selected_node_id}", use_container_width=True, type="primary"):
                                        st.session_state.focused_nodes = st.session_state.focused_nodes + [selected_node_id]
                                        st.rerun()
                                with col2:
                                    if st.button("Restart Here", key=f"restart_{selected_node_id}", use_container_width=True):
                                        st.session_state.focused_nodes = [selected_node_id]
                                        st.rerun()
                            else:
                                st.markdown("<div style='text-align: center; color: #86868B; font-size: 13px; border: 1px solid #3A3A3C; padding: 6px; border-radius: 6px; margin-bottom: 8px;'>Node currently in focus</div>", unsafe_allow_html=True)
                        
                        st.markdown("<hr style='border: none; border-top: 1px solid #2C2C2E; margin: 16px 0 20px 0;'>", unsafe_allow_html=True)
                        
                        if description:
                            st.markdown(f"<p style='color: #A1A1A6; font-size: 15px; line-height: 1.6; margin-bottom: 24px;'>{description}</p>", unsafe_allow_html=True)
                        
                        pills_html = "<div style='display: flex; flex-direction: column; gap: 10px; margin-bottom: 24px;'>"
                        if domain or subdomain:
                            pills_html += "<div style='display: flex; gap: 8px; flex-wrap: wrap;'>"
                            if domain: pills_html += f"<span style='background-color: #3A3A3C; color: #EBEBF5; border: 1px solid #48484A; padding: 4px 12px; border-radius: 16px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;'>{domain}</span>"
                            if subdomain: pills_html += f"<span style='background-color: #2C2C2E; color: #D1D1D6; border: 1px solid #3A3A3C; padding: 4px 12px; border-radius: 16px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;'>{subdomain}</span>"
                            pills_html += "</div>"
                            
                        badge_color = color_map.get(category, "#8E8E93")
                        pills_html += f"<div style='display: flex;'><span style='background-color: {badge_color}20; color: {badge_color}; border: 1px solid {badge_color}40; padding: 4px 12px; border-radius: 16px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;'>{category}</span></div>"
                        
                        if spatial:
                            pills_html += f"<div style='display: flex;'><span style='background-color: #1C1C1E; color: #86868B; border: 1px solid #3A3A3C; padding: 4px 12px; border-radius: 16px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;'>{spatial}</span></div>"
                        pills_html += "</div>"
                        st.markdown(pills_html, unsafe_allow_html=True)

                        def build_edge_card(source, target, rel_type, lit, quant, notes):
                            card = "<div style='background-color: #1C1C1E; border: 1px solid #2C2C2E; border-radius: 8px; padding: 12px; margin-bottom: 8px;'>"
                            card += f"<p style='font-size: 13px; color: #EBEBF5; font-weight: 600; margin-bottom: 8px;'>{source} <span style='color: #FF9F0A; font-size: 11px;'>➔ {rel_type} ➔</span> {target}</p>"
                            if lit and lit != "-": card += f"<p style='font-size: 12px; color: #5E5CE6; margin-bottom: 4px; font-weight: 500;'>Literature: {lit}</p>"
                            if quant and quant != "-": card += f"<p style='font-size: 12px; color: #A1A1A6; margin-bottom: 4px;'><strong>Quantification:</strong> {quant}</p>"
                            if notes and notes != "-": card += f"<p style='font-size: 12px; color: #86868B; margin-bottom: 0; font-style: italic;'>\"{notes}\"</p>"
                            card += "</div>"
                            return card
                        
                        if in_records:
                            st.markdown("<p style='font-size: 12px; color: #86868B; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; margin-top: 20px; margin-bottom: 8px;'>Incoming Drivers</p>", unsafe_allow_html=True)
                            for edge in in_records: 
                                st.markdown(build_edge_card(edge["source_name"], name, edge["rel_type"], edge["lit"], edge["quant"], edge["notes"]), unsafe_allow_html=True)

                        if out_records:
                            st.markdown("<p style='font-size: 12px; color: #86868B; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; margin-top: 20px; margin-bottom: 8px;'>Outgoing Impacts</p>", unsafe_allow_html=True)
                            for edge in out_records: 
                                st.markdown(build_edge_card(name, edge["target_name"], edge["rel_type"], edge["lit"], edge["quant"], edge["notes"]), unsafe_allow_html=True)
                                
    else:
        st.markdown("""
        <div style='display: flex; flex-direction: column; align-items: center; justify-content: center; height: 400px; text-align: center;'>
            <h3 style='color: #48484A; margin-bottom: 8px; font-weight: 500;'>No Results Found</h3>
            <p style='color: #86868B; font-size: 14px;'>Try adjusting your search terms or selecting a different domain.</p>
        </div>
        """, unsafe_allow_html=True)

# --- TAB 2: CONTRIBUTE DATA (Publicly Available) ---
with tab2:
    st.markdown("<h3 style='color: #F5F5F7; margin-bottom: 4px; font-weight: 600;'>Contribute Data</h3>", unsafe_allow_html=True)
    st.markdown("<p style='color: #A1A1A6; font-size: 14px; margin-bottom: 24px;'>Expand the planetary database by submitting new concepts or peer-reviewed pathways.</p>", unsafe_allow_html=True)
    
    form_tab1, form_tab2 = st.tabs(["Register Concept", "Establish Pathway"])
    
    with form_tab1:
        st.markdown("<p style='color: #EBEBF5; font-size: 14px; font-weight: 500; margin-top: 10px;'>Concept Parameters</p>", unsafe_allow_html=True)
        with st.form("add_node_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                new_name = st.text_input("Concept Name", placeholder="e.g., Ocean Acidification")
                available_categories = [k for k in color_map.keys() if k != "Nodes"]
                new_category = st.selectbox("Category", options=available_categories)
                new_scale = st.text_input("Spatial Scale", placeholder="e.g., Global, Regional, Local")
            with col2:
                new_domain = st.text_input("Domain", placeholder="e.g., Biosphere")
                new_subdomain = st.text_input("Subdomain", placeholder="e.g., Marine Ecology")
            
            new_desc = st.text_area("Definition", placeholder="Provide a clear, academic definition...")
            submit_node = st.form_submit_button("Submit Concept")
            
            if submit_node:
                if new_name and new_category:
                    with driver.session() as session:
                        node_query = f"""
                        CREATE (n:{new_category})
                        SET n.node_name = $name, n.node_label = $category, n.node_domain = $domain, n.node_subdomain = $subdomain, n.spacial_scale = $scale, n.node_description = $desc, n.status = 'pending'
                        """
                        session.run(node_query, name=new_name, category=new_category, domain=new_domain, subdomain=new_subdomain, scale=new_scale, desc=new_desc)
                    st.markdown("<div style='background-color: #1C2B23; border: 1px solid #285C3B; color: #34C759; padding: 12px; border-radius: 8px; font-size: 13px; font-weight: 500;'>Concept successfully registered to the database for review.</div>", unsafe_allow_html=True)
                else:
                    st.markdown("<div style='background-color: #3B1C1C; border: 1px solid #6B2828; color: #FF453A; padding: 12px; border-radius: 8px; font-size: 13px; font-weight: 500;'>Error: Concept Name and Category are required fields.</div>", unsafe_allow_html=True)

    with form_tab2:
        st.markdown("<p style='color: #EBEBF5; font-size: 14px; font-weight: 500; margin-top: 10px;'>Pathway Parameters</p>", unsafe_allow_html=True)
        with driver.session() as session:
            node_list_query = "MATCH (n) WHERE n.status IS NULL OR n.status = 'approved' RETURN n.node_name AS name ORDER BY name"
            node_list = [record["name"] for record in session.run(node_list_query)]
            
        with st.form("add_edge_form", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            with col1: source_node = st.selectbox("Source Concept", options=node_list)
            with col2: rel_type = st.selectbox("Relationship", options=["CAUSES", "MITIGATES", "EXACERBATES", "REDUCES"])
            with col3: target_node = st.selectbox("Target Concept", options=node_list)
                
            new_lit = st.text_input("Literature Source", placeholder="e.g., Smith et al., 2024")
            new_quant = st.text_input("Quantification (Optional)", placeholder="e.g., 0.43% annual loss")
            new_notes = st.text_area("Analyst Notes", placeholder="Explain the exact mechanism of this pathway...")
            submit_edge = st.form_submit_button("Establish Pathway")
            
            if submit_edge:
                if source_node and target_node and source_node != target_node:
                    with driver.session() as session:
                        edge_query = f"""
                        MATCH (a), (b) WHERE a.node_name = $source AND b.node_name = $target
                        MERGE (a)-[r:{rel_type}]->(b)
                        SET r.edge_literature_source = $lit, r.edge_quantification = $quant, r.edge_notes = $notes, r.status = 'pending'
                        """
                        session.run(edge_query, source=source_node, target=target_node, lit=new_lit, quant=new_quant, notes=new_notes)
                    st.markdown("<div style='background-color: #1C2B23; border: 1px solid #285C3B; color: #34C759; padding: 12px; border-radius: 8px; font-size: 13px; font-weight: 500;'>Pathway successfully established for review.</div>", unsafe_allow_html=True)
                else:
                    st.markdown("<div style='background-color: #3B1C1C; border: 1px solid #6B2828; color: #FF453A; padding: 12px; border-radius: 8px; font-size: 13px; font-weight: 500;'>Error: You must select distinct Source and Target concepts.</div>", unsafe_allow_html=True)

# --- SECURE ADMIN / PREMIUM TIER TABS ---
if st.session_state.admin_authenticated:
    
    # --- TAB 3: SECURE DATABASE DIRECTORY WITH EXPORT ---
    with tab3:
        st.markdown("<h3 style='color: #F5F5F7; margin-bottom: 4px; font-weight: 600;'>Premium Database Directory</h3>", unsafe_allow_html=True)
        st.markdown("<p style='color: #A1A1A6; font-size: 14px; margin-bottom: 24px;'>Explore and export raw pathway data and literature citations for offline analysis.</p>", unsafe_allow_html=True)
        
        dir_tab1, dir_tab2 = st.tabs(["Literature & Pathways", "Concept Directory"])
        
        with dir_tab1:
            with driver.session() as session:
                lit_query = """
                MATCH (n)-[r]->(m)
                WHERE r.edge_literature_source IS NOT NULL AND r.edge_literature_source <> '-'
                  AND (n.status IS NULL OR n.status = 'approved')
                  AND (m.status IS NULL OR m.status = 'approved')
                  AND (r.status IS NULL OR r.status = 'approved')
                RETURN r.edge_literature_source AS Literature, n.node_name AS Source_Node, type(r) AS Relationship, m.node_name AS Target_Node, r.edge_quantification AS Quantification, r.edge_notes AS Notes
                """
                lit_data = session.run(lit_query).data()
                
            if lit_data:
                df_lit = pd.DataFrame(lit_data)
                st.dataframe(df_lit, use_container_width=True, hide_index=True)
                
                csv_lit = df_lit.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Download Pathways CSV",
                    data=csv_lit,
                    file_name="planetary_pathways.csv",
                    mime="text/csv",
                    type="primary"
                )
            else:
                st.info("No literature data found in the database.")
                
        with dir_tab2:
            with driver.session() as session:
                node_query = "MATCH (n) WHERE n.status IS NULL OR n.status = 'approved' RETURN n.node_name AS Name, n.node_label AS Category, n.node_domain AS Domain, n.spacial_scale AS Scale, n.node_description AS Description"
                node_data = session.run(node_query).data()
                
            if node_data:
                df_nodes = pd.DataFrame(node_data)
                st.dataframe(df_nodes, use_container_width=True, hide_index=True)
                
                csv_nodes = df_nodes.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Download Concepts CSV",
                    data=csv_nodes,
                    file_name="planetary_concepts.csv",
                    mime="text/csv",
                    type="primary"
                )
            else:
                st.info("No concept data found in the database.")

    # --- TAB 4: ADMIN DASHBOARD ---
    with tab4:
        st.markdown("<h3 style='color: #F5F5F7; margin-bottom: 4px; font-weight: 600;'>Admin Control Panel</h3>", unsafe_allow_html=True)
        st.markdown("<p style='color: #A1A1A6; font-size: 14px; margin-bottom: 24px;'>Review, approve, or permanently delete crowdsourced database contributions.</p>", unsafe_allow_html=True)
        
        admin_tab1, admin_tab2, admin_tab3 = st.tabs(["Pending Concepts", "Pending Pathways", "Manage Live Data"])
        
        with admin_tab1:
            with driver.session() as session:
                pending_nodes = session.run("""
                MATCH (n) 
                WHERE n.status = 'pending' 
                RETURN elementId(n) AS id, properties(n) AS props, labels(n)[0] AS label
                """).data()
            
            if not pending_nodes:
                st.info("No pending concepts to review.")
            else:
                for item in pending_nodes:
                    node_id = item["id"]
                    n_props = item["props"]
                    n_label = item["label"] if item["label"] else "Unknown"
                    
                    st.markdown(f"""
                    <div style='background-color: #1C1C1E; border: 1px solid #2C2C2E; border-radius: 8px; padding: 16px; margin-bottom: 12px;'>
                        <h4 style='color: #F5F5F7; margin: 0 0 8px 0; font-size: 16px;'>{n_props.get("node_name", "Unknown")} <span style='color: #86868B; font-size: 12px; font-weight: 400;'>({n_label})</span></h4>
                        <p style='color: #A1A1A6; font-size: 14px; margin: 0 0 12px 0;'>{n_props.get("node_description", "No description provided.")}</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    colA, colB, _ = st.columns([1, 1, 6])
                    if colA.button("Approve", key=f"app_n_{node_id}", type="primary"):
                        with driver.session() as session:
                            session.run("MATCH (n) WHERE elementId(n) = $id SET n.status = 'approved'", id=node_id)
                        st.rerun()
                    if colB.button("Reject", key=f"rej_n_{node_id}"):
                        with driver.session() as session:
                            session.run("MATCH (n) WHERE elementId(n) = $id DETACH DELETE n", id=node_id)
                        st.rerun()
                    st.write("---")
                    
        with admin_tab2:
            with driver.session() as session:
                pending_edges = session.run("""
                MATCH (a)-[r]->(b) 
                WHERE r.status = 'pending' 
                RETURN elementId(r) AS id, a.node_name AS source, type(r) AS rel_type, b.node_name AS target, properties(r) AS props
                """).data()
                
            if not pending_edges:
                st.info("No pending pathways to review.")
            else:
                for item in pending_edges:
                    edge_id = item["id"]
                    r_props = item["props"]
                    
                    st.markdown(f"""
                    <div style='background-color: #1C1C1E; border: 1px solid #2C2C2E; border-radius: 8px; padding: 16px; margin-bottom: 12px;'>
                        <p style='color: #EBEBF5; font-size: 14px; font-weight: 600; margin: 0 0 8px 0;'>{item["source"]} <span style='color: #FF9F0A;'>➔ {item["rel_type"]} ➔</span> {item["target"]}</p>
                        <p style='color: #5E5CE6; font-size: 13px; margin: 0 0 4px 0;'>Literature: {r_props.get("edge_literature_source", "None")}</p>
                        <p style='color: #A1A1A6; font-size: 13px; margin: 0;'>Notes: {r_props.get("edge_notes", "None")}</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    colA, colB, _ = st.columns([1, 1, 6])
                    if colA.button("Approve", key=f"app_e_{edge_id}", type="primary"):
                        with driver.session() as session:
                            session.run("MATCH ()-[r]->() WHERE elementId(r) = $id SET r.status = 'approved'", id=edge_id)
                        st.rerun()
                    if colB.button("Reject", key=f"rej_e_{edge_id}"):
                        with driver.session() as session:
                            session.run("MATCH ()-[r]->() WHERE elementId(r) = $id DELETE r", id=edge_id)
                        st.rerun()
                    st.write("---")

        # --- TAB 3: MANAGE LIVE DATA (UPGRADED WITH FILTER) ---
        with admin_tab3:
            st.markdown("<p style='color: #EBEBF5; font-size: 14px; font-weight: 500; margin-top: 10px;'>Search and Remove Approved Concepts</p>", unsafe_allow_html=True)
            
            # --- NEW: ORIGIN FILTER ---
            origin_filter = st.radio(
                "Filter by Data Origin:", 
                options=["All", "Initial CSV", "Crowdsourced"],
                horizontal=True
            )
            st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
            
            with driver.session() as session:
                live_nodes_query = """
                MATCH (n) 
                WHERE n.status IS NULL OR n.status = 'approved' 
                RETURN elementId(n) AS id, n.node_name AS name, n.node_label AS prop_label, labels(n) AS all_labels, n.status AS status 
                ORDER BY toLower(n.node_name)
                """
                live_nodes = session.run(live_nodes_query).data()
                
            if not live_nodes:
                st.info("The live database is currently empty.")
            else:
                node_options = {}
                for item in live_nodes:
                    # Determine Origin
                    is_crowdsourced = item['status'] == 'approved'
                    
                    # Apply Filter Logic
                    if origin_filter == "Initial CSV" and is_crowdsourced:
                        continue
                    if origin_filter == "Crowdsourced" and not is_crowdsourced:
                        continue
                        
                    # Resolve Name
                    name = item['name'] if item['name'] else "Unnamed Concept"
                    
                    # Resolve the correct category label
                    best_label = "Unknown"
                    if item['prop_label'] and item['prop_label'] != "Nodes":
                        best_label = item['prop_label']
                    elif item['all_labels']:
                        valid_labels = [l for l in item['all_labels'] if l != "Nodes"]
                        if valid_labels:
                            best_label = valid_labels[0]
                            
                    # Clean display name WITHOUT the brackets
                    display_name = f"{name} ({best_label})"
                    
                    # Handle edge case: If two nodes have the exact same name/category, append ID so it doesn't overwrite
                    if display_name in node_options:
                        display_name = f"{display_name} [{item['id'][-4:]}]"
                        
                    node_options[display_name] = item['id']
                
                # Check if the filter resulted in an empty list
                if not node_options:
                    st.info(f"No concepts found matching the '{origin_filter}' filter.")
                else:
                    selected_node_display = st.selectbox("Select Concept to Delete", options=list(node_options.keys()))
                    selected_node_id = node_options[selected_node_display]
                    
                    st.markdown("<div style='background-color: #3B1C1C; border: 1px solid #6B2828; padding: 12px; border-radius: 8px; margin-bottom: 16px;'><p style='color: #FF453A; font-size: 13px; font-weight: 500; margin: 0;'> Warning: Deleting a concept will automatically permanently delete all incoming and outgoing pathways connected to it.</p></div>", unsafe_allow_html=True)
                    
                    if st.button("Permanently Delete Concept", type="primary", use_container_width=True):
                        with driver.session() as session:
                            session.run("MATCH (n) WHERE elementId(n) = $id DETACH DELETE n", id=selected_node_id)
                        
                        clean_name = selected_node_display.split(' (')[0]
                        st.success(f"Successfully deleted {clean_name} from the live database.")
                        st.rerun()
