import re

with open('app.py', 'r') as f:
    code = f.read()

# 1. Update single variation JSON dump
code = code.replace(
"""            return json.dumps({
                'case_size': int(s.get('case_size', 12)),
                'visible': bool(s.get('visible', False))
            })""",
"""            return json.dumps({
                'case_size': int(s.get('case_size', 12)),
                'visible': bool(s.get('visible', False)),
                'par_level': int(s.get('par_level', 0))
            })"""
)

# 2. Update multiple variations dict format
code = code.replace(
"""        if s is not None:
            payload[v_id] = [int(s.get('case_size', 12)), 1 if s.get('visible') else 0]""",
"""        if s is not None:
            payload[v_id] = [int(s.get('case_size', 12)), 1 if s.get('visible') else 0, int(s.get('par_level', 0))]"""
)

# 3. Update index mapping format
code = code.replace(
"""        if s is not None:
            idx_payload["vars"][str(idx)] = [int(s.get('case_size', 12)), 1 if s.get('visible') else 0]""",
"""        if s is not None:
            idx_payload["vars"][str(idx)] = [int(s.get('case_size', 12)), 1 if s.get('visible') else 0, int(s.get('par_level', 0))]"""
)

# 4. Update deserialize single variation format
code = code.replace(
"""        res[v_id] = {
            'case_size': int(data.get('case_size', 12)),
            'visible': bool(data.get('visible', False))
        }""",
"""        res[v_id] = {
            'case_size': int(data.get('case_size', 12)),
            'visible': bool(data.get('visible', False)),
            'par_level': int(data.get('par_level', 0))
        }"""
)

# 5. Update deserialize index format (list)
code = code.replace(
"""                        res[v_id] = {
                            'case_size': int(val[0]),
                            'visible': bool(val[1])
                        }""",
"""                        res[v_id] = {
                            'case_size': int(val[0]),
                            'visible': bool(val[1]),
                            'par_level': int(val[2]) if len(val) >= 3 else 0
                        }"""
)

# 6. Update deserialize var_id format (list)
code = code.replace(
"""                res[v_id] = {
                    'case_size': int(val[0]),
                    'visible': bool(val[1])
                }""",
"""                res[v_id] = {
                    'case_size': int(val[0]),
                    'visible': bool(val[1]),
                    'par_level': int(val[2]) if len(val) >= 3 else 0
                }"""
)

# 7. Update deserialize dict
code = code.replace(
"""                res[v_id] = {
                    'case_size': int(val.get('case_size', 12)),
                    'visible': bool(val.get('visible', False))
                }""",
"""                res[v_id] = {
                    'case_size': int(val.get('case_size', 12)),
                    'visible': bool(val.get('visible', False)),
                    'par_level': int(val.get('par_level', 0))
                }"""
)

with open('app.py', 'w') as f:
    f.write(code)
print("Updated app.py serialization logic.")
