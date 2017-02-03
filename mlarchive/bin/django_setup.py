'''
Broilerplate for standalone Django scripts
'''
import os
import sys

def do_setup(settings='production'):
    path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # Virtualenv support
    virtualenv_activation = os.path.join(path, "bin", "activate_this.py")
    if os.path.exists(virtualenv_activation):
        execfile(virtualenv_activation, dict(__file__=virtualenv_activation))
    
    if not path in sys.path:
        sys.path.insert(0, path)

    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mlarchive.settings.' + settings)
    django.setup()

