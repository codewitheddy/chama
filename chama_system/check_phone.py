import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'chama_system.settings')
django.setup()

from members.models import Member

# Find by partial match
matches = list(Member.objects.filter(phone__icontains='717147').values('id', 'name', 'phone'))
print("icontains matches:", matches)

# Also dump all phones to see format
all_phones = list(Member.objects.values_list('phone', flat=True))
print("Total members:", len(all_phones))
print("All phones:", all_phones[:30])
