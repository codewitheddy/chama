"""One-time cleanup script to remove loan application references."""
import re

# ── 1. loans/forms.py — remove LoanApplicationForm and LoanApplicationReviewForm
content = open('loans/forms.py', encoding='utf-8').read()
start = content.find('\nclass LoanApplicationForm')
end   = content.find('\nclass LoanProductForm')
if start != -1 and end != -1:
    content = content[:start] + '\n' + content[end:]
    print(f'forms.py: removed application form classes')
open('loans/forms.py', 'w', encoding='utf-8').write(content)

# ── 2. audit/signals.py — remove loanapplication from TRACKED_MODELS
content = open('audit/signals.py', encoding='utf-8').read()
content = re.sub(r"\s*\('loans',\s*'loanapplication'\),?", '', content)
open('audit/signals.py', 'w', encoding='utf-8').write(content)
print('audit/signals.py: removed loanapplication tracking')

# ── 3. dashboard/views.py — remove LoanApplication import and usage
content = open('dashboard/views.py', encoding='utf-8').read()
# Remove the import line
content = re.sub(r'[ \t]*from loans\.models import LoanApplication\n', '', content)
# Remove the pending_applications query (find and remove the block)
content = re.sub(
    r'[ \t]*pending_applications\s*=\s*\(?\s*LoanApplication\.objects[^)]+\)\s*\n',
    '',
    content
)
content = re.sub(
    r"[ \t]*'pending_applications':\s*pending_applications,?\s*\n",
    '',
    content
)
open('dashboard/views.py', 'w', encoding='utf-8').write(content)
print('dashboard/views.py: cleaned')

# ── 4. notifications.html — remove pending_applications section
path = 'templates/dashboard/notifications.html'
content = open(path, encoding='utf-8').read()
# Remove any block referencing loans:applications
content = re.sub(
    r'[ \t]*\{%[^%]*applications[^%]*%\}[^\n]*\n',
    '',
    content
)
content = re.sub(
    r'[ \t]*<[^>]*application[^>]*>[^<]*</[^>]*>\s*\n',
    '',
    content
)
open(path, 'w', encoding='utf-8').write(content)
print('notifications.html: cleaned')

# ── 5. loans/loan_list.html — remove applications badge/link
path = 'templates/loans/loan_list.html'
content = open(path, encoding='utf-8').read()
content = re.sub(r'[^\n]*application[^\n]*\n', '', content, flags=re.IGNORECASE)
open(path, 'w', encoding='utf-8').write(content)
print('loan_list.html: cleaned')

print('\nAll done.')
