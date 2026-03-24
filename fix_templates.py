import re

files = ['c:/ExecSlate/app.py', 'c:/ExecSlate/routes/auth.py', 'c:/ExecSlate/routes/admin.py']
for path in files:
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace templates.TemplateResponse("file", context)
    # With templates.TemplateResponse(request=request, name="file", context=context)
    content = re.sub(
        r'templates\.TemplateResponse\(\s*(["\'][a-zA-Z0-9_\./]+\.html["\'])\s*,',
        r'templates.TemplateResponse(request=request, name=\1, context=',
        content
    )
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

print('Replaced templates.TemplateResponse calls!')
