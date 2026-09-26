from typing import Dict, Any, Optional
import os
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from square.client import Square
from square.environment import SquareEnvironment
from square.requests.catalog_object import CatalogObject_CustomAttributeDefinitionParams
from square.requests.catalog_custom_attribute_definition import CatalogCustomAttributeDefinitionParams
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth
import datetime
import json
import uuid

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(days=365) # Long session lifetime

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID'),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

USERS_FILE = 'allowed_users.json'
ADMIN_EMAILS = [
    os.environ.get('ADMIN_EMAIL', 'ejbegin@gmail.com').strip().lower()
]

def get_allowed_users():
    settings = load_settings()
    users = settings.get('_allowed_users')

    # Fallback to local backup file if not present in settings
    if users is None and os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r') as f:
                data = json.load(f)
                users = data.get('allowed_users', [])
        except Exception as e:
            print(f"Error reading users file: {e}")

    if not isinstance(users, list):
        users = []

    clean = []
    # Always include primary admin(s)
    for a in ADMIN_EMAILS:
        if a and a not in clean:
            clean.append(a)
    for u in users:
        if isinstance(u, str):
            ue = u.strip().lower()
            if ue and ue not in clean:
                clean.append(ue)
    return clean

def save_allowed_users(user_list):
    clean = []
    for a in ADMIN_EMAILS:
        if a and a not in clean:
            clean.append(a)
    for u in user_list:
        if isinstance(u, str):
            ue = u.strip().lower()
            if ue and ue not in clean:
                clean.append(ue)

    # 1. Update settings dict (syncs with Square Catalog and item_settings.json)
    settings = load_settings()
    settings['_allowed_users'] = clean
    save_settings(settings)

    # 2. Local allowed_users.json backup
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump({"allowed_users": clean}, f, indent=4)
    except Exception as e:
        print(f"Error saving allowed_users.json: {e}")

    return clean

@app.before_request
def require_login():
    allowed_routes = ['login', 'authorize', 'static', 'access_denied', 'qr_redirect']
    if request.endpoint not in allowed_routes:
        if 'user' not in session:
            return redirect(url_for('login'))
        user_email = (session.get('user', {}).get('email') or '').strip().lower()
        allowed = get_allowed_users()
        if allowed and user_email not in allowed:
            session.pop('user', None)
            return redirect(url_for('access_denied', email=user_email))

@app.route('/login')
def login():
    redirect_uri = url_for('authorize', _external=True)
    return google.authorize_redirect(redirect_uri, prompt='select_account')

@app.route('/authorize')
def authorize():
    try:
        token = google.authorize_access_token()
        user = token.get('userinfo')
    except Exception as e:
        print(f"OAuth authorize error: {e}")
        return redirect(url_for('login'))

    if user:
        email = (user.get('email') or '').strip().lower()
        allowed = get_allowed_users()
        if email and email in allowed:
            session.permanent = True
            session['user'] = user
            return redirect('/')
        else:
            session.pop('user', None)
            return redirect(url_for('access_denied', email=email))
    return redirect('/')

@app.route('/access_denied')
def access_denied():
    email = request.args.get('email', '')
    admin_email = os.environ.get('ADMIN_EMAIL', 'ejbegin@gmail.com')
    return render_template('access_denied.html', email=email, admin_email=admin_email)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

# Initialize Square Client
client = Square(
    token=os.environ.get('SQUARE_ACCESS_TOKEN'),
    environment=SquareEnvironment.PRODUCTION
)

import uuid
import json
import datetime

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/warehouse_to_car')
def warehouse_to_car():
    return render_template('warehouse_to_car.html')

@app.route('/car_to_bige')
def car_to_bige():
    return render_template('car_to_bige.html')

@app.route('/car_to_warehouse')
def car_to_warehouse_redirect():
    return redirect(url_for('car_to_bige'))

@app.route('/settings')
def settings_page():
    return render_template('settings.html')

CATALOG_CACHE_FILE = 'catalog_cache.json'

def get_cached_catalog(force_refresh=False):
    if not force_refresh and os.path.exists(CATALOG_CACHE_FILE):
        try:
            with open(CATALOG_CACHE_FILE, 'r') as f:
                cache = json.load(f)
                if cache.get("objects"):
                    return {"objects": list(cache["objects"].values())}
        except Exception as e:
            print(f"Error reading catalog cache: {e}")

    cache: Dict[str, Any] = {"last_updated_at": None, "objects": {}}
    try:
        categories = [o.dict() for o in client.catalog.list(types='CATEGORY')]
        items = [o.dict() for o in client.catalog.list(types='ITEM')]
        all_objects = categories + items
        cache["last_updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cache["objects"] = {o['id']: o for o in all_objects if o.get('id')}
        with open(CATALOG_CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2)
        return {"objects": all_objects}
    except Exception as e:
        print(f"Error fetching catalog from Square: {e}")
        if os.path.exists(CATALOG_CACHE_FILE):
            try:
                with open(CATALOG_CACHE_FILE, 'r') as f:
                    old_cache = json.load(f)
                    return {"objects": list(old_cache.get("objects", {}).values())}
            except Exception:
                pass
        return {"objects": []}

SETTINGS_FILE = 'item_settings.json'

def get_bige_settings_obj():
    try:
        res = client.catalog.list(types='CUSTOM_ATTRIBUTE_DEFINITION')
        for o in res:
            obj = o.dict()
            if obj.get('custom_attribute_definition_data', {}).get('key') == 'bige_item_settings':
                return obj
    except Exception as e:
        print(f"Error fetching catalog custom attribute definition: {e}")
    return None

def serialize_item_settings(item_obj, all_settings):
    """
    Given a Square Catalog ITEM object and a dict of all variation settings
    {variation_id: {'case_size': int, 'visible': bool}},
    return a compact JSON string (< 240 chars) to store in bige_item_settings.
    """
    variations = item_obj.get('item_data', {}).get('variations', [])
    if not variations:
        return None

    if len(variations) == 1:
        v_id = variations[0]['id']
        s = all_settings.get(v_id)
        if s is not None:
            return json.dumps({
                'case_size': int(s.get('case_size', 12)),
                'visible': bool(s.get('visible', False))
            })
        return None

    # Multiple variations:
    payload = {}
    for v in variations:
        v_id = v['id']
        s = all_settings.get(v_id)
        if s is not None:
            payload[v_id] = [int(s.get('case_size', 12)), 1 if s.get('visible') else 0]

    encoded = json.dumps(payload)
    if len(encoded) <= 240:
        return encoded

    # If too long, use index mapping: {"vars": {"0": [12, 1], ...}}
    idx_payload = {"vars": {}}
    for idx, v in enumerate(variations):
        v_id = v['id']
        s = all_settings.get(v_id)
        if s is not None:
            idx_payload["vars"][str(idx)] = [int(s.get('case_size', 12)), 1 if s.get('visible') else 0]
    return json.dumps(idx_payload)

def deserialize_item_settings(item_obj, string_value):
    """
    Parse string_value from bige_item_settings and return dict of {variation_id: {'case_size': int, 'visible': bool}}
    """
    res = {}
    variations = item_obj.get('item_data', {}).get('variations', [])
    if not variations or not string_value:
        return res

    try:
        data = json.loads(string_value)
    except Exception:
        return res

    # Single variation item format: {"case_size": 12, "visible": true}
    if 'case_size' in data or 'visible' in data:
        v_id = variations[0]['id']
        res[v_id] = {
            'case_size': int(data.get('case_size', 12)),
            'visible': bool(data.get('visible', False))
        }
        return res

    # Index format: {"vars": {"0": [12, 1], ...}}
    if 'vars' in data and isinstance(data['vars'], dict):
        for idx_str, val in data['vars'].items():
            try:
                idx = int(idx_str)
                if idx < len(variations):
                    v_id = variations[idx]['id']
                    if isinstance(val, list) and len(val) >= 2:
                        res[v_id] = {
                            'case_size': int(val[0]),
                            'visible': bool(val[1])
                        }
            except Exception:
                pass
        return res

    # Variation ID format: {var_id: [12, 1]} or {var_id: {"case_size": 12, "visible": true}}
    if isinstance(data, dict):
        for v_id, val in data.items():
            if isinstance(val, list) and len(val) >= 2:
                res[v_id] = {
                    'case_size': int(val[0]),
                    'visible': bool(val[1])
                }
            elif isinstance(val, dict):
                res[v_id] = {
                    'case_size': int(val.get('case_size', 12)),
                    'visible': bool(val.get('visible', False))
                }
    return res

def load_settings():
    settings = {}

    # 1. Fallback / local file
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    settings.update(loaded)
        except Exception as e:
            print(f"Error reading local settings file: {e}")

    # 2. Extract settings from Square Catalog items (from cached catalog)
    try:
        catalog = get_cached_catalog()
        for obj in catalog.get('objects', []):
            if obj.get('type') == 'ITEM':
                custom_vals = obj.get('custom_attribute_values') or {}
                attr_val = custom_vals.get('bige_item_settings', {}).get('string_value')
                if attr_val:
                    item_settings = deserialize_item_settings(obj, attr_val)
                    settings.update(item_settings)
    except Exception as e:
        print(f"Error extracting settings from catalog items: {e}")

    # 3. Load _allowed_users from Square definition description or allowed_users.json
    try:
        obj = get_bige_settings_obj()
        if obj:
            desc = obj.get('custom_attribute_definition_data', {}).get('description')
            if desc:
                desc_data = json.loads(desc)
                if isinstance(desc_data, dict) and '_allowed_users' in desc_data:
                    settings['_allowed_users'] = desc_data['_allowed_users']
    except Exception as e:
        print(f"Error loading _allowed_users from Square: {e}")

    if '_allowed_users' not in settings and os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r') as f:
                settings['_allowed_users'] = json.load(f).get('allowed_users', [])
        except Exception:
            pass

    # Save merged settings back to local cache file
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
    except Exception:
        pass

    return settings

def save_settings(settings):
    # 1. Update local file backup
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
    except Exception as e:
        print(f"Error saving settings locally: {e}")

    # 2. Update site-wide _allowed_users in Square Custom Attribute Definition
    try:
        allowed_users = settings.get('_allowed_users')
        if allowed_users is not None:
            obj = get_bige_settings_obj()
            obj_id = obj['id'] if obj else '#bige_settings'
            version = obj['version'] if obj else None

            desc_payload = json.dumps({'_allowed_users': allowed_users})
            if len(desc_payload) <= 250:
                attr_data: CatalogCustomAttributeDefinitionParams = {
                    'key': 'bige_item_settings',
                    'name': 'Big E Item Settings',
                    'description': desc_payload,
                    'type': 'STRING',
                    'allowed_object_types': ['ITEM'],
                    'seller_visibility': 'SELLER_VISIBILITY_READ_WRITE_VALUES',
                    'app_visibility': 'APP_VISIBILITY_READ_WRITE_VALUES'
                }
                req_obj: CatalogObject_CustomAttributeDefinitionParams = {
                    'type': 'CUSTOM_ATTRIBUTE_DEFINITION',
                    'id': obj_id,
                    'custom_attribute_definition_data': attr_data
                }
                if version:
                    req_obj['version'] = version

                client.catalog.object.upsert(
                    idempotency_key=str(uuid.uuid4()),
                    object=req_obj
                )
    except Exception as e:
        print(f"Error saving _allowed_users to Square Catalog: {e}")

    # 3. Update individual ITEM custom attribute values in Square Catalog
    try:
        catalog = get_cached_catalog()
        cached_objects = {o['id']: o for o in catalog.get('objects', []) if o.get('id')}
        items_to_update = []

        for obj_id, obj in cached_objects.items():
            if obj.get('type') == 'ITEM':
                new_str = serialize_item_settings(obj, settings)
                if new_str is None:
                    continue

                curr_str = (obj.get('custom_attribute_values') or {}).get('bige_item_settings', {}).get('string_value')
                if curr_str != new_str:
                    items_to_update.append((obj, new_str))

        if items_to_update:
            batch_objects = []
            for item_obj, new_str in items_to_update:
                custom_vals = item_obj.get('custom_attribute_values') or {}
                custom_vals['bige_item_settings'] = {
                    'string_value': new_str
                }
                batch_objects.append({
                    'type': 'ITEM',
                    'id': item_obj['id'],
                    'version': item_obj['version'],
                    'item_data': item_obj['item_data'],
                    'custom_attribute_values': custom_vals
                })

            for i in range(0, len(batch_objects), 100):
                chunk = batch_objects[i:i+100]
                try:
                    res = client.catalog.batch_upsert(
                        idempotency_key=str(uuid.uuid4()),
                        batches=[{'objects': chunk}]
                    )
                    res_dict = res.dict()
                    if res_dict.get('objects'):
                        for updated_obj in res_dict['objects']:
                            cached_objects[updated_obj['id']] = updated_obj
                except Exception as batch_err:
                    print(f"Batch upsert failed ({batch_err}), fetching latest item versions from Square and retrying...")
                    refreshed_chunk = []
                    for itm in chunk:
                        try:
                            fresh = client.catalog.object.get(object_id=itm['id']).dict()['object']
                            itm['version'] = fresh['version']
                            itm['item_data'] = fresh['item_data']
                            refreshed_chunk.append(itm)
                        except Exception:
                            pass
                    if refreshed_chunk:
                        res2 = client.catalog.batch_upsert(
                            idempotency_key=str(uuid.uuid4()),
                            batches=[{'objects': refreshed_chunk}]
                        )
                        res2_dict = res2.dict()
                        if res2_dict.get('objects'):
                            for updated_obj in res2_dict['objects']:
                                cached_objects[updated_obj['id']] = updated_obj

            # Save updated catalog cache to file
            try:
                with open(CATALOG_CACHE_FILE, 'w') as f:
                    json.dump({
                        "last_updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "objects": cached_objects
                    }, f, indent=2)
            except Exception as e:
                print(f"Error updating catalog cache: {e}")

    except Exception as e:
        print(f"Error saving item custom attributes to Square: {e}")
        return False

    return True

@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    if request.method == 'POST':
        incoming = request.json or {}
        current = load_settings()
        # Keep _allowed_users intact if not present in incoming settings
        if '_allowed_users' not in incoming and '_allowed_users' in current:
            incoming['_allowed_users'] = current['_allowed_users']
        success = save_settings(incoming)
        if success:
            return jsonify({"status": "success"})
        else:
            return jsonify({"status": "error", "message": "Failed to save settings to Square"}), 500
    res = jsonify(load_settings())
    res.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return res

@app.route('/api/users', methods=['GET', 'POST'])
def api_users():
    if request.method == 'POST':
        data = request.json or {}
        action = data.get('action')
        users = get_allowed_users()

        if action == 'add':
            emails = data.get('emails') or ([data.get('email')] if data.get('email') else [])
            added = []
            for e in emails:
                if isinstance(e, str) and '@' in e:
                    clean_e = e.strip().lower()
                    if clean_e not in users:
                        users.append(clean_e)
                        added.append(clean_e)
            if not added:
                return jsonify({"status": "error", "message": "No new valid email addresses to add."}), 400
            saved = save_allowed_users(users)
            return jsonify({"status": "success", "users": saved, "added": added})

        elif action == 'remove':
            email = (data.get('email') or '').strip().lower()
            if email in ADMIN_EMAILS:
                return jsonify({"status": "error", "message": "Cannot remove the primary administrator."}), 400
            if email in users:
                users.remove(email)
                saved = save_allowed_users(users)
                return jsonify({"status": "success", "users": saved})
            return jsonify({"status": "error", "message": "User not found in authorized list."}), 404

        elif 'users' in data:
            saved = save_allowed_users(data.get('users', []))
            return jsonify({"status": "success", "users": saved})

        return jsonify({"status": "error", "message": "Invalid action."}), 400

    users = get_allowed_users()
    current_email = session.get('user', {}).get('email', '').strip().lower()
    return jsonify({
        "status": "success",
        "users": users,
        "admin_emails": ADMIN_EMAILS,
        "current_user_email": current_email
    })




@app.route('/api/locations')
def get_locations():
    try:
        res = client.locations.list()
        return jsonify(res.dict())
    except Exception as e:
        return jsonify({'error': str(e)}), 500



@app.route('/api/catalog')
def get_catalog():
    try:
        force = request.args.get('refresh', '').lower() == 'true'
        catalog_data = get_cached_catalog(force_refresh=force)
        res = jsonify(catalog_data)
        res.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return res
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/inventory/counts')
def get_inventory_counts():
    try:
        res = client.inventory.deprecated_batch_get_counts(
            states=['IN_STOCK']
        )
        resp = jsonify(res.dict())
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp
    except Exception as e:
        return jsonify({'error': str(e)}), 500


HISTORY_FILE = 'transfer_history.json'

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading history: {e}")
    return []

def save_history(history):
    try:
        with open(HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        print(f"Error saving history: {e}")

@app.route('/api/history', methods=['GET'])
def get_history():
    try:
        history = load_history()
        history_sorted = sorted(history, key=lambda x: x.get('timestamp', ''), reverse=True)
        return jsonify({"history": history_sorted})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/history/undo', methods=['POST'])
def undo_last_history():
    try:
        history = load_history()
        
        active_entries = [e for e in history if e.get('status') == 'completed']
        if not active_entries:
            return jsonify({'error': 'No completed transfers available to undo'}), 400

        target_batch_id = active_entries[-1].get('batch_id')
        if target_batch_id:
            entries_to_undo = [e for e in active_entries if e.get('batch_id') == target_batch_id]
        else:
            entries_to_undo = [active_entries[-1]]

        now_str = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        undone_summaries = []

        for entry in reversed(entries_to_undo):
            rev_from = entry['to_location_id']
            rev_to = entry['from_location_id']
            cat_obj_id = entry['catalog_object_id']
            qty = str(entry['quantity'])

            res = client.inventory.batch_create_changes(
                idempotency_key=str(uuid.uuid4()),
                changes=[
                    {
                        "type": "ADJUSTMENT",
                        "adjustment": {
                            "from_state": "IN_STOCK",
                            "to_state": "NONE",
                            "from_location_id": rev_from,
                            "to_location_id": rev_from,
                            "catalog_object_id": cat_obj_id,
                            "quantity": qty,
                            "occurred_at": now_str
                        }
                    },
                    {
                        "type": "ADJUSTMENT",
                        "adjustment": {
                            "from_state": "NONE",
                            "to_state": "IN_STOCK",
                            "from_location_id": rev_to,
                            "to_location_id": rev_to,
                            "catalog_object_id": cat_obj_id,
                            "quantity": qty,
                            "occurred_at": now_str
                        }
                    }
                ]
            )
            res_dict = res.dict()
            if res_dict.get('errors'):
                return jsonify({'error': f"Failed to undo transfer for {entry.get('item_name', '')}: {res_dict['errors']}"}), 400

            entry['status'] = 'reverted'
            entry['reverted_at'] = now_str
            undone_summaries.append(entry.get('summary', ''))

        save_history(history)
        count_str = f"{len(entries_to_undo)} transfer{'s' if len(entries_to_undo) > 1 else ''}"
        return jsonify({
            "status": "success",
            "message": f"Successfully undone {count_str}.",
            "undone": undone_summaries
        })
    except Exception as e:
        error_msg = str(e)
        if hasattr(e, 'body') and isinstance(e.body, dict) and 'errors' in e.body:
            error_msg = e.body['errors']
        return jsonify({'error': str(error_msg)}), 500

@app.route('/api/inventory/transfer', methods=['POST'])
def transfer_inventory():
    data = request.json
    from_location = data.get('from_location_id')
    to_location = data.get('to_location_id')
    catalog_object_id = data.get('catalog_object_id')
    quantity = data.get('quantity')
    
    if not all([from_location, to_location, catalog_object_id, quantity]):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        qty_int = int(quantity)
        if qty_int <= 0:
            return jsonify({'error': 'Quantity must be greater than 0'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid quantity'}), 400

    # Ensure source location has enough inventory to prevent negative stock
    try:
        counts_res = client.inventory.deprecated_batch_get_counts(
            catalog_object_ids=[catalog_object_id],
            location_ids=[from_location],
            states=['IN_STOCK']
        )
        counts_list = counts_res.dict().get('counts', [])
        current_stock = 0
        if counts_list:
            current_stock = int(counts_list[0].get('quantity', 0))
        if current_stock < qty_int:
            return jsonify({'error': f'Insufficient inventory: requested {qty_int}, available {current_stock}'}), 400
    except Exception as e:
        print(f"Error checking inventory balance: {e}")

    now_str = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    try:
        res = client.inventory.batch_create_changes(
            idempotency_key=str(uuid.uuid4()),
            changes=[
                {
                    "type": "ADJUSTMENT",
                    "adjustment": {
                        "from_state": "IN_STOCK",
                        "to_state": "NONE",
                        "from_location_id": from_location,
                        "to_location_id": from_location,
                        "catalog_object_id": catalog_object_id,
                        "quantity": str(quantity),
                        "occurred_at": now_str
                    }
                },
                {
                    "type": "ADJUSTMENT",
                    "adjustment": {
                        "from_state": "NONE",
                        "to_state": "IN_STOCK",
                        "from_location_id": to_location,
                        "to_location_id": to_location,
                        "catalog_object_id": catalog_object_id,
                        "quantity": str(quantity),
                        "occurred_at": now_str
                    }
                }
            ]
        )
        res_dict = res.dict()
        if res_dict.get('errors'):
            return jsonify({'error': res_dict['errors']}), 400

        # Record to history
        batch_id = data.get('batch_id') or str(uuid.uuid4())
        item_name = data.get('item_name') or catalog_object_id
        from_loc_name = data.get('from_location_name') or 'Location'
        to_loc_name = data.get('to_location_name') or 'Location'
        summary_text = data.get('summary') or f"Transferred {qty_int} units of {item_name} from {from_loc_name} to {to_loc_name}"

        history_entry = {
            "id": str(uuid.uuid4()),
            "batch_id": batch_id,
            "timestamp": now_str,
            "from_location_id": from_location,
            "to_location_id": to_location,
            "from_location_name": from_loc_name,
            "to_location_name": to_loc_name,
            "catalog_object_id": catalog_object_id,
            "item_name": item_name,
            "quantity": qty_int,
            "summary": summary_text,
            "status": "completed",
            "reverted_at": None
        }

        history = load_history()
        history.append(history_entry)
        save_history(history)

        return jsonify(res_dict)
    except Exception as e:
        error_msg = str(e)
        if hasattr(e, 'body') and isinstance(e.body, dict) and 'errors' in e.body:
            error_msg = e.body['errors']
        return jsonify({'error': error_msg}), 500

REDIRECTS_FILE = 'redirects.json'

def load_redirects():
    if os.path.exists(REDIRECTS_FILE):
        try:
            with open(REDIRECTS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading redirects: {e}")
    return {}

def save_redirects(data):
    try:
        with open(REDIRECTS_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving redirects: {e}")

@app.route('/qr_manager')
def qr_manager():
    return render_template('qr_manager.html')

@app.route('/api/qr', methods=['GET', 'POST', 'DELETE'])
def api_qr():
    redirects = load_redirects()
    if request.method == 'GET':
        return jsonify(redirects)
    elif request.method == 'POST':
        data = request.json
        qr_id = data.get('id')
        if not qr_id:
            return jsonify({'error': 'Missing ID'}), 400
        redirects[qr_id] = {
            'name': data.get('name', ''),
            'destination': data.get('destination', ''),
            'created_at': data.get('created_at', datetime.datetime.now(datetime.timezone.utc).isoformat())
        }
        save_redirects(redirects)
        return jsonify({'status': 'success', 'data': redirects[qr_id]})
    elif request.method == 'DELETE':
        data = request.json
        qr_id = data.get('id')
        if qr_id in redirects:
            del redirects[qr_id]
            save_redirects(redirects)
            return jsonify({'status': 'success'})
        return jsonify({'error': 'Not found'}), 404

@app.route('/qr/<qr_id>')
def qr_redirect(qr_id):
    redirects = load_redirects()
    qr_data = redirects.get(qr_id)
    if not qr_data:
        # Redirect to homepage if QR ID is not found
        return redirect('/') 
    
    destination = qr_data.get('destination', '')
    app_uri = "instagram://camera" 
    
    if 'instagram.com/p/' in destination:
        parts = destination.split('instagram.com/p/')
        if len(parts) > 1:
            post_id = parts[1].split('/')[0]
            app_uri = f"instagram://media?id={post_id}"
    elif 'instagram.com/' in destination:
        parts = destination.split('instagram.com/')
        if len(parts) > 1:
            username = parts[1].split('/')[0]
            app_uri = f"instagram://user?username={username}"

    return render_template('qr_redirect.html', destination=destination, app_uri=app_uri)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
