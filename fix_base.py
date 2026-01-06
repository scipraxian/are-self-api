
import os
path = r'c:\talos\dashboard\templates\dashboard\base.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Target the specific mangled block
target = """            {
            % block extra_style %
        }

            {
            % endblock %
        }"""

if target in content:
    new_content = content.replace(target, "        {% block extra_style %}{% endblock %}")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("SUCCESS: Fixed base.html")
else:
    print("ERROR: Target block not found. Checking alternate whitespace...")
    # Try a more flexible regex-ish match if needed
    import re
    p = re.compile(r'\{\s+%\s+block\s+extra_style\s+%\s+\}.*?\{\s+%\s+endblock\s+%\s+\}', re.DOTALL)
    if p.search(content):
        new_content = p.sub('{% block extra_style %}{% endblock %}', content)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("SUCCESS: Fixed base.html via Regex")
    else:
        print("ERROR: Could not find mangled block at all.")
