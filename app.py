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
    allowed_routes = ['login', 'authorize', 'static', 'access_denied']
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

def load_settings():
    # Try fetching site-wide settings from Square Catalog
    obj = get_bige_settings_obj()
    if obj:
        desc = obj.get('custom_attribute_definition_data', {}).get('description')
        if desc:
            try:
                square_settings = json.loads(desc)
                if isinstance(square_settings, dict):
                    try:
                        with open(SETTINGS_FILE, 'w') as f:
                            json.dump(square_settings, f, indent=4)
                    except Exception:
                        pass
                    return square_settings
            except Exception as e:
                print(f"Error parsing Square settings JSON: {e}")

    # Fallback to local file if available
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading local settings file: {e}")
    return {}

def save_settings(settings):
    # 1. Update local file backup
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
    except Exception as e:
        print(f"Error saving settings locally: {e}")

    # 2. Update site-wide settings in Square Catalog
    try:
        obj = get_bige_settings_obj()
        obj_id = obj['id'] if obj else '#bige_settings'
        version = obj['version'] if obj else None

        attr_data: CatalogCustomAttributeDefinitionParams = {
            'key': 'bige_item_settings',
            'name': 'Big E Item Settings',
            'description': json.dumps(settings),
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

        res = client.catalog.object.upsert(
            idempotency_key=str(uuid.uuid4()),
            object=req_obj
        )
        return res.dict()
    except Exception as e:
        print(f"Error saving settings to Square Catalog: {e}")
        return None

@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    if request.method == 'POST':
        incoming = request.json or {}
        current = load_settings()
        # Keep _allowed_users intact if not present in incoming settings
        if '_allowed_users' not in incoming and '_allowed_users' in current:
            incoming['_allowed_users'] = current['_allowed_users']
        save_settings(incoming)
        return jsonify({"status": "success"})
    return jsonify(load_settings())

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
