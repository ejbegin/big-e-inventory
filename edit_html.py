import re

with open('templates/car_to_bige.html', 'r') as f:
    html = f.read()

# 1. Add CSS
css_to_add = """
        /* Car Grid Map Styles */
        .car-map-container {
            background: #e9ecef;
            border-radius: 12px;
            padding: 15px;
            margin-bottom: 20px;
            border: 2px solid #dee2e6;
        }
        .car-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
            max-width: 400px;
            margin: 0 auto;
        }
        .grid-cell {
            background: white;
            border: 2px solid #ccc;
            border-radius: 6px;
            aspect-ratio: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.85rem;
            font-weight: bold;
            text-align: center;
            cursor: pointer;
            transition: all 0.2s;
            user-select: none;
            color: #6c757d;
        }
        .grid-cell.active-item {
            background: #0d6efd;
            color: white;
            border-color: #0a58ca;
            transform: scale(1.05);
            box-shadow: 0 4px 8px rgba(13,110,253,0.3);
        }
        .grid-cell.empty {
            background: transparent;
            border: 2px dashed #ccc;
        }
        .par-level-badge {
            font-size: 0.75rem;
            background: #e9ecef;
            color: #495057;
            padding: 2px 6px;
            border-radius: 4px;
            margin-top: 4px;
            display: inline-block;
        }
        .item-row.highlighted {
            border: 2px solid #0d6efd;
        }
"""
html = html.replace('</style>', css_to_add + '\n    </style>')

# 2. Add Grid Container to HTML
grid_html = """
            <div class="car-map-container" id="carMapSection">
                <h6 class="text-center text-muted fw-bold mb-3"><i class="bi bi-grid-3x3 me-1"></i> Car Map (Rear View)</h6>
                <div class="car-grid" id="carGrid"></div>
            </div>
"""
html = html.replace('<div id="alert-container"></div>', '<div id="alert-container"></div>\n' + grid_html)

# 3. JS Modifications: variables
html = html.replace('let settings = {};', 'let settings = {};\n        let plannerSettings = { par_levels: {}, car_map: { grid_cols: 4, grid_rows: 7, locations: {} } };')

# 4. JS Modifications: init()
init_fetch = """
                const setRes = await fetch('/api/settings');
                settings = await setRes.json();
                
                try {
                    const planRes = await fetch('/api/planner_settings');
                    plannerSettings = await planRes.json();
                    if (!plannerSettings.car_map) plannerSettings.car_map = { grid_cols: 4, grid_rows: 7, locations: {} };
                    if (!plannerSettings.par_levels) plannerSettings.par_levels = {};
                } catch(e) { console.error(e); }
                
                renderCarMap();
"""
html = html.replace("const setRes = await fetch('/api/settings');\n                settings = await setRes.json();", init_fetch)

# 5. JS Modifications: renderCarMap & highlightGrid
map_js = """
        function renderCarMap() {
            const grid = document.getElementById('carGrid');
            if(!grid) return;
            grid.innerHTML = '';
            const mapData = plannerSettings.car_map;
            grid.style.gridTemplateColumns = `repeat(${mapData.grid_cols}, 1fr)`;
            
            const cells = Array(mapData.grid_rows).fill(null).map(() => Array(mapData.grid_cols).fill(null));
            for (const [key, val] of Object.entries(mapData.locations)) {
                if (val.row < mapData.grid_rows && val.col < mapData.grid_cols) {
                    cells[val.row][val.col] = { key: key, name: val.name };
                }
            }
            
            for (let r = 0; r < mapData.grid_rows; r++) {
                for (let c = 0; c < mapData.grid_cols; c++) {
                    const cellData = cells[r][c];
                    const div = document.createElement('div');
                    div.className = 'grid-cell';
                    if (cellData) {
                        div.innerText = cellData.key;
                        div.title = cellData.name;
                        div.id = `grid-cell-${cellData.key}`;
                    } else {
                        div.classList.add('empty');
                    }
                    grid.appendChild(div);
                }
            }
        }
        
        function highlightGrid(itemName) {
            document.querySelectorAll('.grid-cell').forEach(c => c.classList.remove('active-item'));
            const mapData = plannerSettings.car_map.locations;
            let foundKey = null;
            const lowerName = itemName.toLowerCase();
            for (const [key, val] of Object.entries(mapData)) {
                if (lowerName.includes(val.name.toLowerCase())) {
                    foundKey = key;
                    break;
                }
            }
            if (foundKey) {
                const el = document.getElementById(`grid-cell-${foundKey}`);
                if (el) el.classList.add('active-item');
            }
        }
"""
html = html.replace('function filterItems() {', map_js + '\n        function filterItems() {')

# 6. JS Modifications: renderItems
item_render_repl = """
                const parLevel = plannerSettings.par_levels[id] || 0;
                
                // Planner logic: Calculate suggested transfer
                let suggestedQty = 0;
                if (parLevel > 0 && inv[bigEId].total < parLevel) {
                    const needed = parLevel - inv[bigEId].total;
                    const neededCases = Math.ceil(needed / caseSize);
                    suggestedQty = Math.min(neededCases, carInv.cases + (carInv.remainder > 0 ? 1 : 0));
                }
                
                transferState[id] = { transfer_qty: suggestedQty, caseSize: caseSize, itemName: name };

                const parStr = parLevel > 0 ? `<div class="par-level-badge">Par: ${parLevel}</div>` : '';

                card.innerHTML = `
                    <div class="one-line-layout" onclick="highlightGrid('${name.replace(/'/g, "\\'")}')">
                        <div class="item-name-col" title="${name}">
                            ${name}
                            <br>${parStr}
                        </div>
"""
html = html.replace("transferState[id] = { transfer_qty: 0, caseSize: caseSize, itemName: name };\n\n                card.innerHTML = `\n                    <div class=\"one-line-layout\">\n                        <div class=\"item-name-col\" title=\"${name}\">${name}</div>", item_render_repl)

# Update tally display in renderItems so it shows the suggested qty initially
tally_repl = """
                            <!-- Transfer Indicator -->
                            <div class="tally-pill">
                                <span class="tally-count ${suggestedQty > 0 ? 'active' : ''}" id="tally-${id}">${suggestedQty}</span>
                                <div class="transfer-arrow-icon"><i class="bi bi-arrow-right"></i></div>
                            </div>
"""
html = html.replace("""
                            <!-- Transfer Indicator -->
                            <div class="tally-pill">
                                <span class="tally-count" id="tally-${id}">0</span>
                                <div class="transfer-arrow-icon"><i class="bi bi-arrow-right"></i></div>
                            </div>""", tally_repl)

with open('templates/car_to_bige.html', 'w') as f:
    f.write(html)
